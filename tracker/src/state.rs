use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct State {
    pub project: Project,
    pub runtimes: Vec<Runtime>,
    pub last_processed_tags_date: Option<String>,
    #[serde(default)]
    pub releases: Vec<Release>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub org: String,
    pub number: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Runtime {
    pub runtime: String,
    pub short: String,
    pub repo: String,
    pub branch: String,
    pub cargo_lock_path: String,
    pub cargo_toml_path: String,
    pub spec_version_path: String,
    pub network: String,
    pub rpc: String,
    pub ws: String,
    pub field_name: String,
    pub block_explorer_url: String,
    pub last_seen_commit: Option<String>,
    #[serde(default)]
    pub upgrades: Vec<Upgrade>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Upgrade {
    pub spec_version: u64,
    pub block_number: u64,
    pub block_hash: String,
    pub date: String,
    pub block_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Release {
    pub tag: String,
    pub prev_tag: String,
    #[serde(default)]
    pub crates: Vec<CrateRelease>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrateRelease {
    pub name: String,
    pub version: String,
    pub published: String,
    #[serde(default)]
    pub prs: Vec<u64>,
}

impl State {
    pub fn load(path: &Path) -> anyhow::Result<Self> {
        let data = std::fs::read_to_string(path)?;
        Ok(serde_json::from_str(&data)?)
    }

    pub fn save(&self, path: &Path) -> anyhow::Result<()> {
        let data = serde_json::to_string_pretty(self)?;
        std::fs::write(path, data + "\n")?;
        Ok(())
    }
}
