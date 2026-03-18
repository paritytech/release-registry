use anyhow::{Context, Result};
use regex::Regex;
use serde_json::Value;
use std::collections::{HashMap, HashSet};

use crate::github::GitHubClient;
use crate::state::{CrateRelease, Release, State};

/// Index mapping PR number -> full path in prdoc/ (built from master tree).
type PrdocIndex = HashMap<u64, String>;

const SDK_OWNER: &str = "paritytech";
const SDK_REPO: &str = "polkadot-sdk";

/// A published tag from releases-v1.json with its publish date.
#[derive(Debug, Clone)]
struct PublishedTag {
    tag: String,
    name: String,
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

fn is_released(entry: &Value) -> bool {
    match &entry["state"] {
        Value::String(s) => s == "released",
        // Deprecated releases were previously released and have valid tags
        Value::Object(m) => m.contains_key("deprecated"),
        _ => false,
    }
}

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
    // Parse name: "stable2506-9" -> base="stable2506", patch=9
    let (base, patch) = parse_release_name(name);

    if patch > 0 {
        // Find previous patch on same branch (skip gaps from skipped patches)
        let candidates: Vec<_> = all_tags
            .iter()
            .filter(|t| {
                let (b, p) = parse_release_name(&t.name);
                b == base && p < patch
            })
            .collect();

        if let Some(prev) = candidates.last() {
            return Ok(prev.tag.clone());
        }
    }

    // First patch or main release: find latest tag from previous branch
    let all_bases: Vec<_> = all_tags
        .iter()
        .map(|t| parse_release_name(&t.name).0)
        .collect::<HashSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();

    let mut sorted_bases: Vec<_> = all_bases.iter().map(|s| s.as_str()).collect();
    sorted_bases.sort();

    let base_idx = sorted_bases.iter().position(|&b| b == base);
    if let Some(idx) = base_idx {
        if idx > 0 {
            let prev_base = sorted_bases[idx - 1];
            // Find latest tag from previous base
            let prev = all_tags
                .iter()
                .filter(|t| parse_release_name(&t.name).0 == prev_base)
                .last();
            if let Some(p) = prev {
                return Ok(p.tag.clone());
            }
        }
    }

    // Fallback: use the main release tag if we're on the first release
    anyhow::bail!("cannot determine prev_tag for {name}")
}

fn parse_release_name(name: &str) -> (String, u32) {
    if let Some(pos) = name.rfind('-') {
        if let Ok(n) = name[pos + 1..].parse::<u32>() {
            return (name[..pos].to_string(), n);
        }
    }
    (name.to_string(), 0)
}

/// Process a single tag: diff crates and resolve PRs.
async fn process_tag(
    gh: &GitHubClient,
    tag: &str,
    prev_tag: &str,
    publish_date: &str,
    prdoc_index: &PrdocIndex,
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

fn find_changed_cargo_tomls(compare: &Value) -> Vec<String> {
    let mut paths = Vec::new();
    if let Some(files) = compare["files"].as_array() {
        for file in files {
            if let Some(filename) = file["filename"].as_str() {
                if filename.ends_with("/Cargo.toml") && !filename.starts_with('.') {
                    paths.push(filename.to_string());
                }
            }
        }
    }
    paths
}

async fn get_crate_version(
    gh: &GitHubClient,
    toml_path: &str,
    git_ref: &str,
) -> Result<Option<(String, String)>> {
    let content = match gh.get_file_content(SDK_OWNER, SDK_REPO, toml_path, git_ref).await {
        Ok(c) => c,
        Err(_) => return Ok(None),
    };

    let parsed: toml::Value = toml::from_str(&content)?;
    let name = parsed
        .get("package")
        .and_then(|p| p.get("name"))
        .and_then(|n| n.as_str());
    let version = parsed
        .get("package")
        .and_then(|p| p.get("version"))
        .and_then(|v| v.as_str());

    match (name, version) {
        (Some(n), Some(v)) => Ok(Some((n.to_string(), v.to_string()))),
        _ => Ok(None),
    }
}

fn extract_pr_numbers(compare: &Value) -> Vec<u64> {
    let backport_re = Regex::new(r"\[stable\d{4}\] Backport #(\d+)").unwrap();
    let merge_re = Regex::new(r"\(#(\d+)\)\s*$").unwrap();

    let mut prs = HashSet::new();

    if let Some(commits) = compare["commits"].as_array() {
        for commit in commits {
            let msg = commit["commit"]["message"]
                .as_str()
                .unwrap_or_default();
            let first_line = msg.lines().next().unwrap_or_default();

            if let Some(caps) = backport_re.captures(first_line) {
                if let Ok(n) = caps[1].parse::<u64>() {
                    prs.insert(n);
                }
            } else if let Some(caps) = merge_re.captures(first_line) {
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
async fn build_prdoc_index(gh: &GitHubClient) -> Result<PrdocIndex> {
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

async fn fetch_prdoc_crates(
    gh: &GitHubClient,
    pr_number: u64,
    prdoc_index: &PrdocIndex,
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

fn parse_prdoc_crates(yaml_content: &str) -> Result<Vec<String>> {
    let doc: Value = serde_yaml::from_str(yaml_content)?;
    let mut crates = Vec::new();

    if let Some(arr) = doc.get("crates").and_then(|c| c.as_array()) {
        for entry in arr {
            if let Some(name) = entry.get("name").and_then(|n| n.as_str()) {
                crates.push(name.to_string());
            }
        }
    }

    Ok(crates)
}
