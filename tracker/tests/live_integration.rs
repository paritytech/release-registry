use tracker::github::GitHubClient;

macro_rules! require_token {
    () => {
        match std::env::var("GITHUB_TOKEN").ok().map(GitHubClient::new) {
            Some(gh) => gh,
            None => {
                eprintln!("GITHUB_TOKEN not set, skipping");
                return;
            }
        }
    };
}

#[tokio::test]
async fn github_compare() {
    let gh = require_token!();
    let compare = gh
        .compare_tags(
            "paritytech",
            "polkadot-sdk",
            "polkadot-stable2506-7",
            "polkadot-stable2506-9",
        )
        .await
        .unwrap();
    let commits = compare["commits"].as_array().unwrap();
    assert!(!commits.is_empty(), "compare should return commits");
}

#[tokio::test]
async fn prdoc_fetch() {
    let gh = require_token!();
    // PR #7693 is a known prdoc with crates
    let content = gh
        .get_file_content(
            "paritytech",
            "polkadot-sdk",
            "prdoc/pr_7693.prdoc",
            "master",
        )
        .await
        .unwrap();
    let doc: serde_json::Value = serde_yaml::from_str(&content).unwrap();
    assert!(
        doc.get("crates").is_some(),
        "prdoc should have crates section"
    );
}

#[tokio::test]
async fn downstream_cargo_lock() {
    let gh = require_token!();
    let content = gh
        .get_raw_content("paseo-network", "runtimes", "Cargo.lock", "main")
        .await
        .unwrap();
    let versions = tracker::downstream::parse_cargo_lock_versions(&content);
    assert!(
        versions.contains_key("pallet-revive"),
        "paseo-network/runtimes should depend on pallet-revive"
    );
}

#[tokio::test]
async fn onchain_rpc_spec_version() {
    // Skip if no network access
    let client = match subxt::rpcs::client::RpcClient::from_url(
        "wss://sys.ibp.network/asset-hub-paseo",
    )
    .await
    {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Could not connect to RPC: {e}, skipping");
            return;
        }
    };
    let rpc =
        subxt::rpcs::LegacyRpcMethods::<subxt::config::RpcConfigFor<subxt::config::PolkadotConfig>>::new(
            client,
        );
    let version = rpc.state_get_runtime_version(None).await.unwrap();
    assert!(
        version.spec_version > 1_000_000,
        "asset-hub-paseo spec_version should be > 1M, got {}",
        version.spec_version
    );
}
