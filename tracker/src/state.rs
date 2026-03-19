use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::path::Path;

/// Transient downstream data, not persisted in state.json.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct DownstreamInfo {
    /// Crate name -> resolved version from Cargo.lock.
    pub versions: HashMap<String, String>,
    /// Set of crate names the runtime depends on.
    pub deps: HashSet<String>,
    /// Spec version parsed from the runtime source.
    pub spec_version: Option<u64>,
}

/// Top-level persistent tracker state.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct State {
    /// GitHub Project V2 reference.
    pub project: Project,
    /// Tracked downstream runtimes.
    pub runtimes: Vec<Runtime>,
    /// ISO date of the most recently processed tag.
    pub last_processed_tags_date: Option<String>,
    /// Discovered releases with crate-level PR mappings.
    #[serde(default)]
    pub releases: Vec<Release>,
}

/// GitHub Project V2 coordinates.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Project {
    /// GitHub organization login.
    pub org: String,
    /// Project number.
    pub number: u64,
}

/// A downstream runtime to track.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Runtime {
    /// Runtime name (e.g. "asset-hub-polkadot").
    pub runtime: String,
    /// Short display label.
    pub short: String,
    /// GitHub `owner/repo`.
    pub repo: String,
    /// Git branch to track.
    pub branch: String,
    /// Path to Cargo.lock in the repo.
    pub cargo_lock_path: String,
    /// Path to the runtime's Cargo.toml.
    pub cargo_toml_path: String,
    /// Path to the file containing `spec_version`.
    pub spec_version_path: String,
    /// Chain network name.
    pub network: String,
    /// HTTP RPC endpoint.
    pub rpc: String,
    /// WebSocket RPC endpoint.
    pub ws: String,
    /// Project V2 field name for this runtime.
    pub field_name: String,
    /// Block explorer base URL.
    pub block_explorer_url: String,
    /// In-repo runtime (e.g. Westend in polkadot-sdk): skip version matching,
    /// treat all PRs as adopted since every PR lands on master directly.
    #[serde(default)]
    pub in_repo: bool,
    /// Last processed commit SHA.
    pub last_seen_commit: Option<String>,
    /// On-chain runtime upgrades discovered so far.
    #[serde(default)]
    pub upgrades: Vec<Upgrade>,
    /// Transient downstream info (not serialized).
    #[serde(skip)]
    pub downstream: DownstreamInfo,
}

/// An on-chain runtime upgrade event.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Upgrade {
    /// Runtime spec version after the upgrade.
    pub spec_version: u64,
    /// Block number where the new runtime first executed.
    pub block_number: u64,
    /// Block hash.
    pub block_hash: String,
    /// ISO 8601 timestamp.
    pub date: String,
    /// Block explorer URL for the upgrade block.
    pub block_url: String,
}

/// A polkadot-sdk release with its crate version bumps.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Release {
    /// Git tag for this release.
    pub tag: String,
    /// Git tag of the previous release.
    pub prev_tag: String,
    /// Crates with version bumps in this release.
    #[serde(default)]
    pub crates: Vec<CrateRelease>,
}

/// A single crate's version bump within a release.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CrateRelease {
    /// Crate name.
    pub name: String,
    /// New version.
    pub version: String,
    /// Publish date.
    pub published: String,
    /// PR numbers that contributed to this crate's changes.
    #[serde(default)]
    pub prs: Vec<u64>,
}

impl State {
    /// Load state from a JSON file.
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        let data = std::fs::read_to_string(path)?;
        Ok(serde_json::from_str(&data)?)
    }

    /// Save state to a JSON file.
    pub fn save(&self, path: &Path) -> anyhow::Result<()> {
        let data = serde_json::to_string_pretty(self)?;
        std::fs::write(path, data + "\n")?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn state_roundtrip() {
        let state = State {
            project: Project { org: "test-org".into(), number: 42 },
            runtimes: vec![],
            last_processed_tags_date: Some("2025-06-15".into()),
            releases: vec![Release {
                tag: "v1".into(),
                prev_tag: "v0".into(),
                crates: vec![CrateRelease {
                    name: "my-crate".into(),
                    version: "1.0.0".into(),
                    published: "2025-01-01".into(),
                    prs: vec![1, 2, 3],
                }],
            }],
        };

        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("state.json");
        state.save(&path).unwrap();
        let loaded = State::load(&path).unwrap();

        assert_eq!(loaded, state);
    }
}
