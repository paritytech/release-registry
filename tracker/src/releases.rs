use anyhow::{Context, Result};
use regex::Regex;
use serde::Deserialize;
use serde_json::Value;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::sync::LazyLock;

use crate::github::GitHubClient;
use crate::state::{CrateRelease, Release, State};

/// GitHub owner for polkadot-sdk.
pub const SDK_OWNER: &str = "paritytech";
/// GitHub repo name.
pub const SDK_REPO: &str = "polkadot-sdk";

/// A published tag from releases-v1.json with its publish date.
#[derive(Debug, Clone)]
struct PublishedTag {
    /// Git tag (e.g. "polkadot-stable2506-9").
    tag: String,
    /// Release name (e.g. "stable2506-9").
    name: String,
    /// Publish date (ISO 8601).
    date: String,
}

/// Discover new releases from releases-v1.json and resolve PRs.
pub async fn discover_and_resolve(
    state: &mut State,
    gh: &GitHubClient,
    releases_json: &Value,
    dry_run: bool,
) -> Result<()> {
    let tags = collect_published_tags(releases_json)?;

    let cutoff = state.last_processed_tags_date.as_deref();
    let new_tags: Vec<_> = tags
        .iter()
        .filter(|t| match cutoff {
            Some(date) => t.date.as_str() > date,
            None => true,
        })
        .collect();

    if new_tags.is_empty() {
        eprintln!("No new tags to process");
        return Ok(());
    }

    eprintln!("Found {} new tag(s) to process", new_tags.len());

    // Build prdoc index from master tree (once for all tags)
    eprintln!("  Building prdoc index from master...");
    let prdoc_index = build_prdoc_index(gh).await?;
    eprintln!("  Indexed {} prdoc files", prdoc_index.len());

    let known_tags: HashSet<String> = state.releases.iter().map(|r| r.tag.clone()).collect();

    for published in &new_tags {
        if known_tags.contains(&published.tag) {
            eprintln!("  Skipping {} (already processed)", published.tag);
            continue;
        }

        let prev_tag = match find_prev_tag(&published.name, &tags) {
            Ok(t) => t,
            Err(e) => {
                eprintln!("  Skipping {} ({})", published.tag, e);
                continue;
            }
        };
        eprintln!(
            "  Processing {} (prev: {})",
            published.tag, prev_tag
        );

        let release = process_tag(gh, &published.tag, &prev_tag, &published.date, &prdoc_index).await?;
        eprintln!(
            "    Found {} crate(s) with version bumps, {} total PR(s)",
            release.crates.len(),
            release.crates.iter().flat_map(|c| &c.prs).collect::<HashSet<_>>().len()
        );

        if !dry_run {
            state.releases.push(release);
        }
    }

    if !dry_run {
        if let Some(latest) = new_tags.iter().map(|t| t.date.as_str()).max() {
            state.last_processed_tags_date = Some(latest.to_string());
        }
    }

    Ok(())
}

/// Collect all published (released) tags from releases-v1.json, sorted by date.
fn collect_published_tags(releases_json: &Value) -> Result<Vec<PublishedTag>> {
    let sdk = releases_json
        .get("Polkadot SDK")
        .context("no 'Polkadot SDK' in releases-v1.json")?;
    let releases = sdk["releases"]
        .as_array()
        .context("no releases array")?;

    let mut tags = Vec::new();

    for release in releases {
        if !is_released(release) {
            continue;
        }

        // Main release tag
        if let Some(tag_info) = extract_tag_info(release, &release["publish"]) {
            tags.push(tag_info);
        }

        // Patch tags
        if let Some(patches) = release["patches"].as_array() {
            for patch in patches {
                if !is_released(patch) {
                    continue;
                }
                if let Some(tag_info) = extract_tag_info(patch, &patch["publish"]) {
                    tags.push(tag_info);
                }
            }
        }
    }

    tags.sort_by(|a, b| a.date.cmp(&b.date));
    Ok(tags)
}

/// Check if a release entry has state "released" or "deprecated".
fn is_released(entry: &Value) -> bool {
    match &entry["state"] {
        Value::String(s) => s == "released",
        // Deprecated releases were previously released and have valid tags
        Value::Object(m) => m.contains_key("deprecated"),
        _ => false,
    }
}

/// Extract tag, name, and date from a release JSON entry.
fn extract_tag_info(entry: &Value, publish: &Value) -> Option<PublishedTag> {
    let tag = publish.get("tag")?.as_str()?;
    let date = publish.get("when")?.as_str()?;
    let name = entry.get("name")?.as_str()?;
    Some(PublishedTag {
        tag: tag.to_string(),
        name: name.to_string(),
        date: date.to_string(),
    })
}

/// Find the previous tag for a given release/patch name.
fn find_prev_tag(name: &str, all_tags: &[PublishedTag]) -> Result<String> {
    let (base, patch) = parse_release_name(name);

    if patch > 0 {
        // Find previous patch on same branch (skip gaps from skipped patches)
        if let Some(prev) = all_tags
            .iter()
            .rev()
            .find(|t| {
                let (b, p) = parse_release_name(&t.name);
                b == base && p < patch
            })
        {
            return Ok(prev.tag.clone());
        }
    }

    // First patch or main release: find latest tag from previous branch
    let sorted_bases: BTreeSet<String> = all_tags
        .iter()
        .map(|t| parse_release_name(&t.name).0.to_string())
        .collect();

    let base_owned = base.to_string();
    if let Some(prev_base) = sorted_bases.range(..base_owned).next_back() {
        if let Some(p) = all_tags
            .iter()
            .rev()
            .find(|t| parse_release_name(&t.name).0 == prev_base.as_str())
        {
            return Ok(p.tag.clone());
        }
    }

    anyhow::bail!("cannot determine prev_tag for {name}")
}

/// Parse "stable2506-9" into ("stable2506", 9). Returns patch 0 if no suffix.
fn parse_release_name(name: &str) -> (&str, u32) {
    if let Some(pos) = name.rfind('-') {
        if let Ok(n) = name[pos + 1..].parse::<u32>() {
            return (&name[..pos], n);
        }
    }
    (name, 0)
}

/// Process a single tag: diff crates and resolve PRs.
async fn process_tag(
    gh: &GitHubClient,
    tag: &str,
    prev_tag: &str,
    publish_date: &str,
    prdoc_index: &HashMap<u64, String>,
) -> Result<Release> {
    let compare = gh.compare_tags(SDK_OWNER, SDK_REPO, prev_tag, tag).await?;

    // Find changed Cargo.toml files from the diff
    let changed_tomls = find_changed_cargo_tomls(&compare);

    // Collect crate version bumps
    let mut crate_versions: HashMap<String, (String, String)> = HashMap::new(); // name -> (old, new)

    for toml_path in &changed_tomls {
        let old_version = get_crate_version(gh, toml_path, prev_tag).await;
        let new_version = get_crate_version(gh, toml_path, tag).await;

        if let (Ok(Some((name_old, ver_old))), Ok(Some((name_new, ver_new)))) =
            (old_version, new_version)
        {
            if name_old == name_new && ver_old != ver_new {
                crate_versions.insert(name_new, (ver_old, ver_new));
            }
        }
    }

    // Extract PR numbers from commits
    let pr_numbers = extract_pr_numbers(&compare);
    eprintln!("    {} PRs from commits, {} changed Cargo.toml files", pr_numbers.len(), changed_tomls.len());

    // Resolve PRs to crates via prdocs
    let mut crate_prs: HashMap<String, Vec<u64>> = HashMap::new();
    for &pr_num in &pr_numbers {
        let prdoc_crates = fetch_prdoc_crates(gh, pr_num, prdoc_index).await;
        if let Ok(crates) = prdoc_crates {
            for crate_name in crates {
                if crate_versions.contains_key(&crate_name) {
                    crate_prs.entry(crate_name).or_default().push(pr_num);
                }
            }
        }
    }

    // Build release entry
    let crates: Vec<CrateRelease> = crate_versions
        .into_iter()
        .map(|(name, (_, version))| {
            let prs = crate_prs.get(&name).cloned().unwrap_or_default();
            CrateRelease {
                name,
                version,
                published: publish_date.to_string(),
                prs,
            }
        })
        .collect();

    Ok(Release {
        tag: tag.to_string(),
        prev_tag: prev_tag.to_string(),
        crates,
    })
}

/// Extract paths of changed Cargo.toml files from a compare response.
fn find_changed_cargo_tomls(compare: &Value) -> Vec<String> {
    compare["files"]
        .as_array()
        .map(|files| {
            files
                .iter()
                .filter_map(|f| f["filename"].as_str())
                .filter(|f| f.ends_with("/Cargo.toml") && !f.starts_with('.'))
                .map(String::from)
                .collect()
        })
        .unwrap_or_default()
}

/// Minimal Cargo.toml for extracting package name and version.
#[derive(Deserialize)]
struct CargoToml {
    /// Package metadata.
    package: Option<CargoPackage>,
}

/// Package name and version from Cargo.toml.
#[derive(Deserialize)]
struct CargoPackage {
    /// Crate name.
    name: String,
    /// Crate version.
    version: String,
}

/// Fetch a Cargo.toml at a given ref and return `(name, version)`.
async fn get_crate_version(
    gh: &GitHubClient,
    toml_path: &str,
    git_ref: &str,
) -> Result<Option<(String, String)>> {
    let content = match gh.get_file_content(SDK_OWNER, SDK_REPO, toml_path, git_ref).await {
        Ok(c) => c,
        Err(_) => return Ok(None),
    };

    let parsed: CargoToml = toml::from_str(&content)?;
    Ok(parsed.package.map(|p| (p.name, p.version)))
}

/// Regex for backport commit messages like `[stable2506] Backport #1234`.
static BACKPORT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[stable\d{4}\] Backport #(\d+)").unwrap());
/// Regex for merge commit messages like `Fix thing (#1234)`.
static MERGE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\(#(\d+)\)\s*$").unwrap());

/// Extract PR numbers from commit messages in a compare response.
fn extract_pr_numbers(compare: &Value) -> Vec<u64> {
    let mut prs = HashSet::new();

    if let Some(commits) = compare["commits"].as_array() {
        for commit in commits {
            let msg = commit["commit"]["message"]
                .as_str()
                .unwrap_or_default();
            let first_line = msg.lines().next().unwrap_or_default();

            if let Some(caps) = BACKPORT_RE.captures(first_line) {
                if let Ok(n) = caps[1].parse::<u64>() {
                    prs.insert(n);
                }
            } else if let Some(caps) = MERGE_RE.captures(first_line) {
                if let Ok(n) = caps[1].parse::<u64>() {
                    prs.insert(n);
                }
            }
        }
    }

    let mut sorted: Vec<_> = prs.into_iter().collect();
    sorted.sort();
    sorted
}

/// Build an index of PR number -> prdoc path from the master tree.
async fn build_prdoc_index(gh: &GitHubClient) -> Result<HashMap<u64, String>> {
    let re = Regex::new(r"prdoc/.*/pr_(\d+)\.prdoc$|prdoc/pr_(\d+)\.prdoc$").unwrap();
    let url = format!(
        "https://api.github.com/repos/{SDK_OWNER}/{SDK_REPO}/git/trees/master?recursive=1"
    );
    let tree: Value = gh.get_json(&url).await?;

    let mut index = HashMap::new();
    if let Some(entries) = tree["tree"].as_array() {
        for entry in entries {
            if let Some(path) = entry["path"].as_str() {
                if let Some(caps) = re.captures(path) {
                    let num_str = caps.get(1).or(caps.get(2)).unwrap().as_str();
                    if let Ok(n) = num_str.parse::<u64>() {
                        index.insert(n, path.to_string());
                    }
                }
            }
        }
    }

    Ok(index)
}

/// Fetch and parse the prdoc file for a PR, returning affected crate names.
async fn fetch_prdoc_crates(
    gh: &GitHubClient,
    pr_number: u64,
    prdoc_index: &HashMap<u64, String>,
) -> Result<Vec<String>> {
    let path = match prdoc_index.get(&pr_number) {
        Some(p) => p.clone(),
        None => anyhow::bail!("no prdoc found for PR #{pr_number}"),
    };

    let content = gh
        .get_file_content(SDK_OWNER, SDK_REPO, &path, "master")
        .await?;
    parse_prdoc_crates(&content)
}

/// Minimal prdoc structure for extracting crate names.
#[derive(Deserialize)]
struct Prdoc {
    /// Affected crates.
    #[serde(default)]
    crates: Vec<PrdocCrate>,
}

/// A crate entry in a prdoc file.
#[derive(Deserialize)]
struct PrdocCrate {
    /// Crate name.
    name: String,
}

/// Parse crate names from a prdoc YAML file.
fn parse_prdoc_crates(yaml_content: &str) -> Result<Vec<String>> {
    let doc: Prdoc = serde_yaml::from_str(yaml_content)?;
    Ok(doc.crates.into_iter().map(|c| c.name).collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parse_release_name_with_patch() {
        assert_eq!(parse_release_name("stable2506-9"), ("stable2506", 9));
    }

    #[test]
    fn parse_release_name_without_patch() {
        assert_eq!(parse_release_name("stable2506"), ("stable2506", 0));
    }

    #[test]
    fn parse_release_name_non_numeric_suffix() {
        assert_eq!(parse_release_name("stable2506-rc1"), ("stable2506-rc1", 0));
    }

    #[test]
    fn is_released_string() {
        assert!(is_released(&json!({"state": "released"})));
    }

    #[test]
    fn is_released_deprecated() {
        assert!(is_released(&json!({"state": {"deprecated": {"since": "2025-01-01"}}})));
    }

    #[test]
    fn is_released_planned() {
        assert!(!is_released(&json!({"state": "planned"})));
    }

    #[test]
    fn is_released_missing_state() {
        assert!(!is_released(&json!({})));
    }

    #[test]
    fn extract_tag_info_valid() {
        let entry = json!({"name": "stable2506-1"});
        let publish = json!({"tag": "polkadot-stable2506-1", "when": "2025-06-15"});
        let info = extract_tag_info(&entry, &publish).unwrap();
        assert_eq!(info.tag, "polkadot-stable2506-1");
        assert_eq!(info.name, "stable2506-1");
        assert_eq!(info.date, "2025-06-15");
    }

    #[test]
    fn extract_tag_info_missing_fields() {
        assert!(extract_tag_info(&json!({}), &json!({"tag": "t", "when": "d"})).is_none());
        assert!(extract_tag_info(&json!({"name": "n"}), &json!({})).is_none());
    }

    #[test]
    fn extract_pr_numbers_merge_commit() {
        let compare = json!({
            "commits": [{"commit": {"message": "Fix thing (#42)"}}]
        });
        assert_eq!(extract_pr_numbers(&compare), vec![42]);
    }

    #[test]
    fn extract_pr_numbers_backport() {
        let compare = json!({
            "commits": [{"commit": {"message": "[stable2506] Backport #99"}}]
        });
        assert_eq!(extract_pr_numbers(&compare), vec![99]);
    }

    #[test]
    fn extract_pr_numbers_no_match() {
        let compare = json!({
            "commits": [{"commit": {"message": "No PR ref here"}}]
        });
        assert!(extract_pr_numbers(&compare).is_empty());
    }

    #[test]
    fn extract_pr_numbers_dedup() {
        let compare = json!({
            "commits": [
                {"commit": {"message": "A (#10)"}},
                {"commit": {"message": "B (#10)"}}
            ]
        });
        assert_eq!(extract_pr_numbers(&compare), vec![10]);
    }

    #[test]
    fn find_changed_cargo_tomls_filters() {
        let compare = json!({
            "files": [
                {"filename": "substrate/frame/balances/Cargo.toml"},
                {"filename": ".hidden/Cargo.toml"},
                {"filename": "polkadot/runtime/src/lib.rs"},
                {"filename": "cumulus/pallets/collator/Cargo.toml"}
            ]
        });
        let result = find_changed_cargo_tomls(&compare);
        assert_eq!(result, vec![
            "substrate/frame/balances/Cargo.toml",
            "cumulus/pallets/collator/Cargo.toml",
        ]);
    }

    #[test]
    fn parse_prdoc_crates_valid() {
        let yaml = r#"
title: test
crates:
  - name: pallet-balances
    bump: patch
  - name: frame-system
    bump: minor
"#;
        assert_eq!(
            parse_prdoc_crates(yaml).unwrap(),
            vec!["pallet-balances", "frame-system"]
        );
    }

    #[test]
    fn parse_prdoc_crates_no_key() {
        assert!(parse_prdoc_crates("title: test\ndoc: []\n").unwrap().is_empty());
    }

    #[test]
    fn collect_published_tags_from_fixture() {
        let fixture = include_str!("../tests/fixtures/releases-v1-sample.json");
        let json: Value = serde_json::from_str(fixture).unwrap();
        let tags = collect_published_tags(&json).unwrap();

        let names: Vec<&str> = tags.iter().map(|t| t.name.as_str()).collect();
        // stable2407 + stable2407-1 (deprecated = released) + stable2506 + stable2506-1 + stable2506-2
        // stable2506-3 is "planned", excluded. Sorted by date.
        assert_eq!(names, vec![
            "stable2407",
            "stable2407-1",
            "stable2506",
            "stable2506-1",
            "stable2506-2",
        ]);
    }

    #[test]
    fn find_prev_tag_same_branch() {
        let tags = vec![
            PublishedTag { tag: "polkadot-stable2506".into(), name: "stable2506".into(), date: "2025-06-01".into() },
            PublishedTag { tag: "polkadot-stable2506-1".into(), name: "stable2506-1".into(), date: "2025-06-15".into() },
            PublishedTag { tag: "polkadot-stable2506-2".into(), name: "stable2506-2".into(), date: "2025-07-01".into() },
        ];
        assert_eq!(find_prev_tag("stable2506-2", &tags).unwrap(), "polkadot-stable2506-1");
    }

    #[test]
    fn find_prev_tag_cross_branch() {
        let tags = vec![
            PublishedTag { tag: "polkadot-stable2407".into(), name: "stable2407".into(), date: "2024-04-29".into() },
            PublishedTag { tag: "polkadot-stable2407-1".into(), name: "stable2407-1".into(), date: "2024-08-15".into() },
            PublishedTag { tag: "polkadot-stable2506".into(), name: "stable2506".into(), date: "2025-06-01".into() },
        ];
        assert_eq!(find_prev_tag("stable2506", &tags).unwrap(), "polkadot-stable2407-1");
    }

    #[test]
    fn find_prev_tag_no_previous() {
        let tags = vec![
            PublishedTag { tag: "polkadot-stable2407".into(), name: "stable2407".into(), date: "2024-04-29".into() },
        ];
        assert!(find_prev_tag("stable2407", &tags).is_err());
    }
}
