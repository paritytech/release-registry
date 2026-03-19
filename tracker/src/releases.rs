use anyhow::{Context, Result};
use regex::Regex;
use serde::Deserialize;
use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;
use std::sync::LazyLock;

use crate::state::{CrateRelease, Release, State};

/// Top-level releases-v1.json structure.
#[derive(Deserialize)]
pub struct ReleasesJson {
    #[serde(rename = "Polkadot SDK")]
    pub polkadot_sdk: ProjectInfo,
}

#[derive(Deserialize)]
pub struct ProjectInfo {
    pub releases: Vec<ReleaseInfo>,
}

#[derive(Deserialize)]
pub struct ReleaseInfo {
    pub name: String,
    pub publish: DateAndTag,
    pub state: MaintainedState,
    #[serde(default)]
    pub patches: Vec<PatchInfo>,
}

#[derive(Deserialize)]
pub struct PatchInfo {
    pub name: String,
    pub publish: DateAndTag,
    pub state: MaintainedState,
}

#[derive(Deserialize)]
#[serde(untagged)]
pub enum DateAndTag {
    Published { when: String, tag: String },
    Estimated {},
}

#[derive(Deserialize)]
#[serde(untagged)]
pub enum MaintainedState {
    Simple(SimpleState),
    Deprecated { #[serde(rename = "deprecated")] _deprecated: serde_json::Value },
}

#[derive(Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SimpleState {
    Planned,
    Staging,
    Released,
    Skipped,
}

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

/// Discover new releases from releases-v1.json and resolve PRs via local git.
pub fn discover_and_resolve(
    state: &mut State,
    releases_json: &ReleasesJson,
    sdk_repo: &Path,
) -> Result<()> {
    log::info!("Discover releases & resolve PRs");
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
        log::info!("No new tags to process");
        return Ok(());
    }

    log::info!("Found {} new tag(s) to process", new_tags.len());

    log::debug!("Building prdoc index from local repo...");
    let prdoc_crates = build_local_prdoc_index(sdk_repo)?;
    log::debug!("Indexed {} prdoc files", prdoc_crates.len());

    let known_tags: HashSet<String> = state.releases.iter().map(|r| r.tag.clone()).collect();

    for published in &new_tags {
        if known_tags.contains(&published.tag) {
            log::debug!("Skipping {} (already processed)", published.tag);
            continue;
        }

        let prev_tag = match find_prev_tag(&published.name, &tags) {
            Ok(t) => t,
            Err(e) => {
                log::debug!("Skipping {} ({})", published.tag, e);
                continue;
            }
        };
        log::info!("Processing {} (prev: {})", published.tag, prev_tag);

        let release = process_tag(sdk_repo, &published.tag, &prev_tag, &published.date, &prdoc_crates)?;
        log::info!(
            "  Found {} crate(s) with version bumps, {} total PR(s)",
            release.crates.len(),
            release.crates.iter().flat_map(|c| &c.prs).collect::<HashSet<_>>().len()
        );

        state.releases.push(release);
    }

    if let Some(latest) = new_tags.iter().map(|t| t.date.as_str()).max() {
        state.last_processed_tags_date = Some(latest.to_string());
    }

    Ok(())
}

/// Collect all published (released) tags from releases-v1.json, sorted by date.
fn collect_published_tags(releases_json: &ReleasesJson) -> Result<Vec<PublishedTag>> {
    let mut tags = Vec::new();

    for release in &releases_json.polkadot_sdk.releases {
        if !release.state.is_released() {
            continue;
        }

        if let Some(tag_info) = PublishedTag::from_entry(&release.name, &release.publish) {
            tags.push(tag_info);
        }

        for patch in &release.patches {
            if !patch.state.is_released() {
                continue;
            }
            if let Some(tag_info) = PublishedTag::from_entry(&patch.name, &patch.publish) {
                tags.push(tag_info);
            }
        }
    }

    tags.sort_by(|a, b| a.date.cmp(&b.date));
    Ok(tags)
}

impl MaintainedState {
    /// Returns true if the state is "released" or deprecated (which implies previously released).
    fn is_released(&self) -> bool {
        matches!(self, Self::Simple(SimpleState::Released) | Self::Deprecated { .. })
    }
}

impl PublishedTag {
    /// Build from a releases-v1.json entry. Returns None for estimated (unpublished) dates.
    fn from_entry(name: &str, publish: &DateAndTag) -> Option<Self> {
        match publish {
            DateAndTag::Published { when, tag } => Some(PublishedTag {
                tag: tag.clone(),
                name: name.to_string(),
                date: when.clone(),
            }),
            DateAndTag::Estimated { .. } => None,
        }
    }
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

// ---------------------------------------------------------------------------
// Local git operations
// ---------------------------------------------------------------------------

/// Run a git command in the SDK repo, returning stdout.
fn git(sdk_repo: &Path, args: &[&str]) -> Result<String> {
    let output = std::process::Command::new("git")
        .arg("-C")
        .arg(sdk_repo)
        .args(args)
        .output()
        .context("failed to run git")?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("git {} failed: {}", args.join(" "), stderr.trim());
    }
    Ok(String::from_utf8(output.stdout)?)
}

/// Process a single tag: diff crates and resolve PRs using local git.
fn process_tag(
    sdk_repo: &Path,
    tag: &str,
    prev_tag: &str,
    publish_date: &str,
    prdoc_crates: &HashMap<u64, Vec<String>>,
) -> Result<Release> {
    let changed_tomls = git_changed_cargo_tomls(sdk_repo, prev_tag, tag)?;

    // Collect crate version bumps
    let mut crate_versions: HashMap<String, (String, String)> = HashMap::new();

    for toml_path in &changed_tomls {
        let old_version = git_crate_version(sdk_repo, prev_tag, toml_path);
        let new_version = git_crate_version(sdk_repo, tag, toml_path);

        if let (Ok(Some((name_old, ver_old))), Ok(Some((name_new, ver_new)))) =
            (old_version, new_version)
        {
            if name_old == name_new && ver_old != ver_new {
                crate_versions.insert(name_new, (ver_old, ver_new));
            }
        }
    }

    // Extract PR numbers from commit messages
    let pr_numbers = git_extract_pr_numbers(sdk_repo, prev_tag, tag)?;
    log::debug!("{} PRs from commits, {} changed Cargo.toml files", pr_numbers.len(), changed_tomls.len());

    // Resolve PRs to crates via prdocs
    let mut crate_prs: HashMap<String, Vec<u64>> = HashMap::new();
    for &pr_num in &pr_numbers {
        if let Some(crates) = prdoc_crates.get(&pr_num) {
            for crate_name in crates {
                if crate_versions.contains_key(crate_name) {
                    crate_prs.entry(crate_name.clone()).or_default().push(pr_num);
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

/// List changed Cargo.toml files between two tags.
fn git_changed_cargo_tomls(sdk_repo: &Path, prev_tag: &str, tag: &str) -> Result<Vec<String>> {
    let range = format!("{prev_tag}..{tag}");
    let output = git(sdk_repo, &["diff", "--name-only", &range, "--", "*/Cargo.toml"])?;
    Ok(output
        .lines()
        .filter(|f| !f.starts_with('.'))
        .map(String::from)
        .collect())
}

/// Read a Cargo.toml at a given ref and return `(name, version)`.
fn git_crate_version(
    sdk_repo: &Path,
    git_ref: &str,
    toml_path: &str,
) -> Result<Option<(String, String)>> {
    let spec = format!("{git_ref}:{toml_path}");
    let content = match git(sdk_repo, &["show", &spec]) {
        Ok(c) => c,
        Err(_) => return Ok(None),
    };

    let manifest = cargo_toml::Manifest::from_str(&content)?;
    Ok(manifest.package.map(|p| (p.name, p.version.get().map(|v| v.to_string()).unwrap_or_default())))
}

/// Regex for backport commit messages like `[stable2506] Backport #1234`.
static BACKPORT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[stable\d{4}\] Backport #(\d+)").unwrap());
/// Regex for merge commit messages like `Fix thing (#1234)`.
static MERGE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\(#(\d+)\)\s*$").unwrap());

/// Extract PR numbers from commit messages between two tags.
fn git_extract_pr_numbers(sdk_repo: &Path, prev_tag: &str, tag: &str) -> Result<Vec<u64>> {
    let range = format!("{prev_tag}..{tag}");
    let output = git(sdk_repo, &["log", &range, "--format=%s"])?;

    let mut prs = HashSet::new();
    for line in output.lines() {
        if let Some(caps) = BACKPORT_RE.captures(line) {
            if let Ok(n) = caps[1].parse::<u64>() {
                prs.insert(n);
            }
        } else if let Some(caps) = MERGE_RE.captures(line) {
            if let Ok(n) = caps[1].parse::<u64>() {
                prs.insert(n);
            }
        }
    }

    let mut sorted: Vec<_> = prs.into_iter().collect();
    sorted.sort();
    Ok(sorted)
}

/// Regex matching prdoc filenames like `prdoc/stable2512/pr_10861.prdoc`.
static PRDOC_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"prdoc/.*/pr_(\d+)\.prdoc$|prdoc/pr_(\d+)\.prdoc$").unwrap());

/// Build PR number -> affected crate names index from local prdoc files on master.
fn build_local_prdoc_index(sdk_repo: &Path) -> Result<HashMap<u64, Vec<String>>> {
    let output = git(sdk_repo, &["ls-tree", "-r", "--name-only", "master", "prdoc/"])?;

    let mut index = HashMap::new();
    for path in output.lines() {
        let pr_num = match PRDOC_RE.captures(path) {
            Some(caps) => {
                let num_str = caps.get(1).or(caps.get(2)).unwrap().as_str();
                match num_str.parse::<u64>() {
                    Ok(n) => n,
                    Err(_) => continue,
                }
            }
            None => continue,
        };

        let content = match git(sdk_repo, &["show", &format!("master:{path}")]) {
            Ok(c) => c,
            Err(_) => continue,
        };

        if let Ok(crates) = parse_prdoc_crates(&content) {
            if !crates.is_empty() {
                index.insert(pr_num, crates);
            }
        }
    }

    Ok(index)
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
    fn maintained_state_released() {
        let s: MaintainedState = serde_json::from_value(json!("released")).unwrap();
        assert!(s.is_released());
    }

    #[test]
    fn maintained_state_deprecated() {
        let s: MaintainedState = serde_json::from_value(
            json!({"deprecated": {"since": "2025-01-01", "useInstead": "stable2503"}}),
        ).unwrap();
        assert!(s.is_released());
    }

    #[test]
    fn maintained_state_planned() {
        let s: MaintainedState = serde_json::from_value(json!("planned")).unwrap();
        assert!(!s.is_released());
    }

    #[test]
    fn published_tag_from_published() {
        let publish = DateAndTag::Published {
            when: "2025-06-15".into(),
            tag: "polkadot-stable2506-1".into(),
        };
        let info = PublishedTag::from_entry("stable2506-1", &publish).unwrap();
        assert_eq!(info.tag, "polkadot-stable2506-1");
        assert_eq!(info.name, "stable2506-1");
        assert_eq!(info.date, "2025-06-15");
    }

    #[test]
    fn published_tag_from_estimated() {
        let publish = DateAndTag::Estimated {};
        assert!(PublishedTag::from_entry("stable2506-3", &publish).is_none());
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
        let json: ReleasesJson = serde_json::from_str(fixture).unwrap();
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
