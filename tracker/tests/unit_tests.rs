use std::collections::{HashMap, HashSet};
use std::path::PathBuf;

use tracker::downstream::{parse_cargo_lock_versions, parse_runtime_deps};
use tracker::onchain::parse_spec_version;
use tracker::state::State;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
}

fn read_fixture(name: &str) -> String {
    std::fs::read_to_string(fixture(name)).unwrap()
}

#[test]
fn parse_cargo_lock_from_fixture() {
    let content = read_fixture("cargo-lock-sample.lock");
    assert_eq!(
        parse_cargo_lock_versions(&content),
        HashMap::from([
            ("pallet-balances".into(), "39.0.1".into()),
            ("pallet-revive".into(), "0.3.0".into()),
            ("frame-system".into(), "38.1.0".into()),
            ("sp-core".into(), "34.0.0".into()),
        ])
    );
}

#[test]
fn parse_runtime_deps_from_fixture() {
    let content = read_fixture("cargo-toml-sample.toml");
    assert_eq!(
        parse_runtime_deps(&content),
        HashSet::from([
            "pallet-balances".into(),
            "frame-system".into(),
            "pallet-revive".into(),
            "sp-io".into(),
            "sp-core".into(),
        ])
    );
}

#[test]
fn parse_spec_version_from_fixture() {
    let content = read_fixture("lib-rs-sample.rs");
    assert_eq!(parse_spec_version(&content), Some(2_000_006));
}

#[test]
fn state_load_save_roundtrip() {
    let state = State::load(&fixture("state-sample.json")).unwrap();

    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("state-out.json");
    state.save(&path).unwrap();
    let reloaded = State::load(&path).unwrap();

    assert_eq!(reloaded, state);
}
