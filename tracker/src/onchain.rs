use anyhow::Result;
use chrono::prelude::*;
use regex::Regex;
use std::sync::LazyLock;
use subxt::config::substrate::H256;
use subxt::config::RpcConfigFor;
use subxt::rpcs::client::RpcClient;
use subxt::rpcs::LegacyRpcMethods;
use subxt::{config::PolkadotConfig, OnlineClient};

use crate::state::{Runtime, Upgrade};

/// Generated runtime types from metadata.
#[subxt::subxt(runtime_metadata_path = "./metadata.scale")]
mod substrate {}

/// Shorthand for legacy RPC methods on Polkadot-compatible chains.
type Rpc = LegacyRpcMethods<RpcConfigFor<PolkadotConfig>>;

/// Substrate chain RPC client.
struct ChainClient {
    /// Legacy RPC methods (block hash, runtime version, etc.).
    rpc: Rpc,
    /// High-level online client for storage queries.
    client: OnlineClient<PolkadotConfig>,
}

impl ChainClient {
    /// Connect to a chain via WebSocket URL.
    async fn connect(url: &str) -> Result<Self> {
        let rpc_client = RpcClient::from_url(url).await?;
        let rpc = Rpc::new(rpc_client.clone());
        let client = OnlineClient::<PolkadotConfig>::from_rpc_client(rpc_client).await?;
        Ok(Self { rpc, client })
    }

    /// Get the current chain head block number.
    async fn get_head_number(&self) -> Result<u32> {
        let block = self.client.at_current_block().await?;
        Ok(block.block_number() as u32)
    }

    /// Get block hash by number.
    async fn get_block_hash(&self, number: u32) -> Result<H256> {
        self.rpc
            .chain_get_block_hash(Some(number.into()))
            .await?
            .ok_or_else(|| anyhow::anyhow!("no hash for block {number}"))
    }

    /// Get runtime spec version at a given block hash.
    async fn get_spec_version(&self, hash: H256) -> Result<u32> {
        let version = self.rpc.state_get_runtime_version(Some(hash)).await?;
        Ok(version.spec_version)
    }

    /// Read the `Timestamp::now` storage value at a given block.
    async fn get_timestamp(&self, block_hash: H256) -> Result<DateTime<Utc>> {
        let addr = substrate::storage().timestamp().now();
        let ms: u64 = self
            .client
            .at_block(block_hash)
            .await?
            .storage()
            .fetch(addr, ())
            .await?
            .decode()?;

        DateTime::from_timestamp_millis(ms as i64)
            .ok_or_else(|| anyhow::anyhow!("invalid timestamp {ms}"))
    }

    /// Binary search for the first block with `target_spec`.
    async fn bisect_upgrade(&self, mut lower: u32, mut upper: u32, target_spec: u32) -> Result<u32> {
        while upper - lower > 1 {
            let mid = lower + (upper - lower) / 2;
            let hash = self.get_block_hash(mid).await?;
            let mid_spec = self.get_spec_version(hash).await?;
            log::debug!("bisect: block {mid} spec {mid_spec} (range {lower}..{upper})");
            if mid_spec >= target_spec {
                upper = mid;
            } else {
                lower = mid;
            }
        }
        Ok(upper)
    }
}

/// Regex for extracting `spec_version: N` from Rust source.
static SPEC_VERSION_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"spec_version:\s*(\d[\d_]*)").unwrap());

/// Parse spec_version from a runtime lib.rs file fetched via GitHub.
pub fn parse_spec_version(content: &str) -> Option<u64> {
    let caps = SPEC_VERSION_RE.captures(content)?;
    let raw = caps[1].replace('_', "");
    raw.parse().ok()
}

/// Check on-chain spec versions and find new upgrades.
pub async fn check_onchain(runtimes: &mut [Runtime]) -> Result<()> {
    log::info!("On-chain queries");
    for runtime in runtimes.iter_mut() {
        log::info!("{} ({}): connecting to {}", runtime.runtime, runtime.network, runtime.ws);

        let chain = match ChainClient::connect(&runtime.ws).await {
            Ok(c) => c,
            Err(e) => {
                log::warn!("Failed to connect: {e}");
                continue;
            }
        };

        let head = chain.get_head_number().await?;
        let head_hash = chain.get_block_hash(head).await?;
        let current_spec = chain.get_spec_version(head_hash).await?;
        log::info!("Head: block {head}, spec {current_spec}");

        let last_known_spec = runtime
            .upgrades
            .iter()
            .map(|u| u.spec_version)
            .max()
            .unwrap_or(0);

        if current_spec as u64 <= last_known_spec {
            log::debug!("No new upgrades (last known: {last_known_spec})");
            continue;
        }

        // Find the upgrade block via binary search
        let last_known_block = runtime
            .upgrades
            .iter()
            .map(|u| u.block_number)
            .max()
            .unwrap_or(0);

        // bisect finds the first block whose post-state has the new spec.
        // That block is the one where set_code executed (last block with old runtime).
        // The next block is the first one actually executed with the new runtime.
        let set_code_block = chain
            .bisect_upgrade(last_known_block as u32, head, current_spec)
            .await?;
        let upgrade_block = set_code_block + 1;
        let upgrade_hash = chain.get_block_hash(upgrade_block).await?;
        let upgrade_spec = chain.get_spec_version(upgrade_hash).await?;
        let timestamp = chain.get_timestamp(upgrade_hash).await?;

        log::info!(
            "set_code in block {set_code_block}, first block with spec {upgrade_spec} is {upgrade_block} ({timestamp})"
        );

        let block_url = format!("{}/block/{}", runtime.block_explorer_url, upgrade_block);
        runtime.upgrades.push(Upgrade {
            spec_version: upgrade_spec as u64,
            block_number: upgrade_block as u64,
            block_hash: format!("{:?}", upgrade_hash),
            date: timestamp.to_rfc3339(),
            block_url,
        });
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_spec_version_standard() {
        assert_eq!(parse_spec_version("spec_version: 1002003"), Some(1002003));
    }

    #[test]
    fn parse_spec_version_underscored() {
        assert_eq!(parse_spec_version("spec_version: 2_000_006"), Some(2000006));
    }

    #[test]
    fn parse_spec_version_extra_whitespace() {
        assert_eq!(parse_spec_version("spec_version:   42"), Some(42));
    }

    #[test]
    fn parse_spec_version_missing() {
        assert_eq!(parse_spec_version("impl_version: 0"), None);
    }
}
