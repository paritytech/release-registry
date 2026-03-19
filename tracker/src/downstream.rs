use anyhow::Result;
use std::collections::{HashMap, HashSet};
use std::str::FromStr;

use crate::github::GitHubClient;
use crate::onchain::parse_spec_version;
use crate::state::State;

/// Check downstream runtimes for crate consumption.
pub async fn check_downstream(state: &mut State, gh: &GitHubClient) -> Result<()> {
    log::info!("Check downstream consumption");
    for runtime in &mut state.runtimes {
        let (owner, repo) = parse_repo(&runtime.repo);

        let latest_commit = gh.get_latest_commit(owner, repo, &runtime.branch).await?;

        let has_downstream = !runtime.downstream.deps.is_empty();
        if runtime.last_seen_commit.as_deref() == Some(&latest_commit) && has_downstream {
            log::debug!("{} ({}): no new commits", runtime.runtime, runtime.network);
            continue;
        }

        log::info!(
            "{} ({}): checking commit {}",
            runtime.runtime,
            runtime.network,
            &latest_commit[..8]
        );

        // In-repo runtimes don't need Cargo.lock/Cargo.toml version matching,
        // but still need spec_version for the status state machine.
        if runtime.in_repo {
            let spec_version = match gh
                .get_raw_content(owner, repo, &runtime.spec_version_path, &latest_commit)
                .await
            {
                Ok(content) => parse_spec_version(&content),
                Err(e) => {
                    log::warn!("Could not fetch spec_version_path: {e}");
                    None
                }
            };

            log::debug!("in-repo runtime, code spec: {:?}", spec_version);

            runtime.downstream = crate::state::DownstreamInfo {
                versions: HashMap::new(),
                deps: HashSet::new(),
                spec_version,
            };
        } else {
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
                    log::warn!("Could not fetch spec_version_path: {e}");
                    None
                }
            };

            log::debug!(
                "{} resolved crates, {} direct dependencies, code spec: {:?}",
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
        }

        runtime.last_seen_commit = Some(latest_commit);
    }

    Ok(())
}

/// Split an `owner/repo` string into `(owner, repo)`.
pub fn parse_repo(full: &str) -> (&str, &str) {
    full.split_once('/').expect("repo must contain '/'")
}

/// Parse Cargo.lock to extract package name -> version mapping.
pub fn parse_cargo_lock_versions(content: &str) -> HashMap<String, String> {
    let lock = match cargo_lock::Lockfile::from_str(content) {
        Ok(v) => v,
        Err(_) => return HashMap::new(),
    };
    lock.packages
        .into_iter()
        .map(|p| (p.name.as_str().to_string(), p.version.to_string()))
        .collect()
}

/// Parse Cargo.toml to extract dependency names (all dependency sections).
pub fn parse_runtime_deps(content: &str) -> HashSet<String> {
    let manifest = match cargo_toml::Manifest::from_str(content) {
        Ok(v) => v,
        Err(_) => return HashSet::new(),
    };

    let mut deps: HashSet<String> = HashSet::new();
    deps.extend(manifest.dependencies.into_keys());
    deps.extend(manifest.dev_dependencies.into_keys());
    deps.extend(manifest.build_dependencies.into_keys());
    if let Some(workspace) = manifest.workspace {
        deps.extend(workspace.dependencies.into_keys());
    }
    deps
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_repo_standard() {
        assert_eq!(parse_repo("paritytech/polkadot-sdk"), ("paritytech", "polkadot-sdk"));
    }

    #[test]
    fn parse_repo_with_hyphens() {
        assert_eq!(parse_repo("paseo-network/runtimes"), ("paseo-network", "runtimes"));
    }

    #[test]
    fn parse_cargo_lock_versions_basic() {
        let input = r#"
[[package]]
name = "pallet-balances"
version = "39.0.1"

[[package]]
name = "frame-system"
version = "38.1.0"
"#;
        assert_eq!(
            parse_cargo_lock_versions(input),
            HashMap::from([
                ("pallet-balances".into(), "39.0.1".into()),
                ("frame-system".into(), "38.1.0".into()),
            ])
        );
    }

    #[test]
    fn parse_cargo_lock_versions_empty() {
        assert!(parse_cargo_lock_versions("").is_empty());
    }

    #[test]
    fn parse_runtime_deps_all_sections() {
        let toml = r#"
[dependencies]
pallet-balances = "39"

[dev-dependencies]
sp-io = "38"

[build-dependencies]
substrate-wasm-builder = "24"
"#;
        assert_eq!(
            parse_runtime_deps(toml),
            HashSet::from([
                "pallet-balances".into(),
                "sp-io".into(),
                "substrate-wasm-builder".into(),
            ])
        );
    }

    #[test]
    fn parse_runtime_deps_workspace() {
        let toml = r#"
[workspace.dependencies]
sp-core = "34"
"#;
        assert_eq!(
            parse_runtime_deps(toml),
            HashSet::from(["sp-core".into()])
        );
    }

    #[test]
    fn parse_runtime_deps_invalid_toml() {
        assert!(parse_runtime_deps("not valid toml {{{").is_empty());
    }
}
