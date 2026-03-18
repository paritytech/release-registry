#![deny(clippy::missing_docs_in_private_items)]

//! PR Deployment Tracker for polkadot-sdk releases.

/// Downstream runtime consumption checks.
pub mod downstream;
/// GitHub REST and GraphQL API client.
pub mod github;
/// On-chain spec version tracking via Substrate RPC.
pub mod onchain;
/// GitHub Project V2 annotation logic.
pub mod project;
/// Release discovery and PR resolution.
pub mod releases;
/// Persistent tracker state.
pub mod state;
