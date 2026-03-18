use anyhow::Result;
use std::collections::{HashMap, HashSet};

use crate::github::GitHubClient;
use crate::onchain::parse_spec_version;
use crate::state::State;

/// Check downstream runtimes for crate consumption.
pub async fn check_downstream(state: &mut State, gh: &GitHubClient, dry_run: bool) -> Result<()> {
    for runtime in &mut state.runtimes {
        let (owner, repo) = parse_repo(&runtime.repo);

        let latest_commit = gh.get_latest_commit(owner, repo, &runtime.branch).await?;

        let has_downstream = !runtime.downstream.deps.is_empty();
        if runtime.last_seen_commit.as_deref() == Some(&latest_commit) && has_downstream {
            eprintln!("  {} ({}): no new commits", runtime.runtime, runtime.network);
            continue;
        }

        eprintln!(
            "  {} ({}): checking commit {}",
            runtime.runtime,
            runtime.network,
            &latest_commit[..8]
        );

        // Fetch current Cargo.lock
        let cargo_lock = gh
            .get_raw_content(owner, repo, &runtime.cargo_lock_path, &latest_commit)
            .await?;
        let current_versions = parse_cargo_lock_versions(&cargo_lock);

        // Fetch runtime's Cargo.toml to know which crates are dependencies
        let cargo_toml = gh
            .get_raw_content(owner, repo, &runtime.cargo_toml_path, &latest_commit)
            .await?;
        let runtime_deps = parse_runtime_deps(&cargo_toml);

        // Fetch spec_version from downstream code
        let spec_version = match gh
            .get_raw_content(owner, repo, &runtime.spec_version_path, &latest_commit)
            .await
        {
            Ok(content) => parse_spec_version(&content),
            Err(e) => {
                eprintln!("    Could not fetch spec_version_path: {e}");
                None
            }
        };

        eprintln!(
            "    {} resolved crates, {} direct dependencies, code spec: {:?}",
            current_versions.len(),
            runtime_deps.len(),
            spec_version
        );

        runtime.downstream = crate::state::DownstreamInfo {
            versions: current_versions
                .into_iter()
                .filter(|(k, _)| runtime_deps.contains(k))
                .collect(),
            deps: runtime_deps,
            spec_version,
        };

        if !dry_run {
            runtime.last_seen_commit = Some(latest_commit);
        }
    }

    Ok(())
}

/// Returns (adopted_count, total_relevant_count).
#[allow(dead_code)]
pub fn compute_pr_coverage(
    pr_crate_names: &[String],
    release_crates: &HashMap<String, String>, // name -> version from release
    lock_versions: &HashMap<String, String>,  // name -> version from Cargo.lock
    runtime_deps: &HashSet<String>,           // crate names the runtime depends on
) -> (usize, usize) {
    let relevant: Vec<_> = pr_crate_names
        .iter()
        .filter(|name| runtime_deps.contains(name.as_str()))
        .collect();

    let total = relevant.len();
    let adopted = relevant
        .iter()
        .filter(|name| {
            if let (Some(release_ver), Some(lock_ver)) =
                (release_crates.get(name.as_str()), lock_versions.get(name.as_str()))
            {
                lock_ver == release_ver
            } else {
                false
            }
        })
        .count();

    (adopted, total)
}

/// Split an `owner/repo` string into `(owner, repo)`.
fn parse_repo(full: &str) -> (&str, &str) {
    let parts: Vec<&str> = full.splitn(2, '/').collect();
    (parts[0], parts[1])
}

/// Parse Cargo.lock to extract package name -> version mapping.
pub fn parse_cargo_lock_versions(content: &str) -> HashMap<String, String> {
    let mut versions = HashMap::new();
    let mut current_name: Option<String> = None;

    for line in content.lines() {
        if line.starts_with("name = ") {
            current_name = line
                .strip_prefix("name = ")
                .and_then(|s| s.strip_prefix('"'))
                .and_then(|s| s.strip_suffix('"'))
                .map(String::from);
        } else if line.starts_with("version = ") {
            if let Some(name) = current_name.take() {
                if let Some(ver) = line
                    .strip_prefix("version = ")
                    .and_then(|s| s.strip_prefix('"'))
                    .and_then(|s| s.strip_suffix('"'))
                {
                    versions.insert(name, ver.to_string());
                }
            }
        } else if line.trim().is_empty() {
            current_name = None;
        }
    }

    versions
}

/// Parse Cargo.toml to extract dependency names (all dependency sections).
pub fn parse_runtime_deps(content: &str) -> HashSet<String> {
    let mut deps = HashSet::new();
    let parsed: toml::Value = match toml::from_str(content) {
        Ok(v) => v,
        Err(_) => return deps,
    };

    for section in ["dependencies", "dev-dependencies", "build-dependencies"] {
        if let Some(table) = parsed.get(section).and_then(|v| v.as_table()) {
            for key in table.keys() {
                // Cargo.toml dep keys use hyphens, crate names in Cargo.lock also use hyphens
                deps.insert(key.clone());
            }
        }
    }

    // Also check workspace dependencies if present
    if let Some(workspace) = parsed.get("workspace") {
        if let Some(table) = workspace.get("dependencies").and_then(|v| v.as_table()) {
            for key in table.keys() {
                deps.insert(key.clone());
            }
        }
    }

    deps
}
