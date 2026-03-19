#!/usr/bin/env bash
# Bootstrap the tracker state from scratch.
# Usage: ./bootstrap.sh [--sdk-repo PATH]
#
# Requires: GITHUB_TOKEN env var, a local polkadot-sdk checkout.
# Builds the tracker, then runs discover -> onchain -> downstream -> annotate (dry-run).

set -euo pipefail

SDK_REPO="${POLKADOT_SDK_DIR:-$HOME/polkadot-sdk}"

for arg in "$@"; do
  case "$arg" in
    --sdk-repo=*) SDK_REPO="${arg#*=}" ;;
    --sdk-repo) shift; SDK_REPO="$1" ;;
  esac
  shift 2>/dev/null || true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_PATH="$SCRIPT_DIR/state.json"
TRACKER="$SCRIPT_DIR/target/release/tracker"

: "${GITHUB_TOKEN:?GITHUB_TOKEN env var required}"

if [ ! -d "$SDK_REPO/.git" ]; then
  echo "Error: $SDK_REPO is not a git repo. Set --sdk-repo or POLKADOT_SDK_DIR." >&2
  exit 1
fi

echo "==> Fetching latest tags in $SDK_REPO"
git -C "$SDK_REPO" fetch --tags --quiet 2>/dev/null || echo "    (fetch skipped, using existing tags)"

echo "==> Building tracker"
cargo build --release --manifest-path "$SCRIPT_DIR/Cargo.toml" --quiet

echo "==> Writing minimal state.json"
cat > "$STATE_PATH" <<'EOF'
{
  "project": {
    "org": "paritytech",
    "number": 274
  },
  "runtimes": [
    {
      "runtime": "Asset Hub",
      "short": "AH",
      "repo": "paseo-network/runtimes",
      "branch": "main",
      "cargo_lock_path": "Cargo.lock",
      "cargo_toml_path": "system-parachains/asset-hub-paseo/Cargo.toml",
      "spec_version_path": "system-parachains/asset-hub-paseo/src/lib.rs",
      "network": "Paseo",
      "rpc": "https://paseo-asset-hub-rpc.polkadot.io",
      "ws": "wss://sys.ibp.network/asset-hub-paseo",
      "field_name": "AH Paseo",
      "block_explorer_url": "https://assethub-paseo.subscan.io",
      "upgrades": []
    },
    {
      "runtime": "Asset Hub",
      "short": "AH",
      "repo": "paritytech/polkadot-sdk",
      "branch": "master",
      "cargo_lock_path": "Cargo.lock",
      "cargo_toml_path": "cumulus/parachains/runtimes/assets/asset-hub-westend/Cargo.toml",
      "spec_version_path": "cumulus/parachains/runtimes/assets/asset-hub-westend/src/lib.rs",
      "network": "Westend",
      "rpc": "https://westend-asset-hub-rpc.polkadot.io",
      "ws": "wss://westend-asset-hub-rpc.polkadot.io",
      "field_name": "AH Westend",
      "block_explorer_url": "https://assethub-westend.subscan.io",
      "in_repo": true,
      "upgrades": []
    },
    {
      "runtime": "Asset Hub",
      "short": "AH",
      "repo": "polkadot-fellows/runtimes",
      "branch": "main",
      "cargo_lock_path": "Cargo.lock",
      "cargo_toml_path": "system-parachains/asset-hubs/asset-hub-kusama/Cargo.toml",
      "spec_version_path": "system-parachains/asset-hubs/asset-hub-kusama/src/lib.rs",
      "network": "Kusama",
      "rpc": "https://kusama-asset-hub-rpc.polkadot.io",
      "ws": "wss://kusama-asset-hub-rpc.polkadot.io",
      "field_name": "AH Kusama",
      "block_explorer_url": "https://assethub-kusama.subscan.io",
      "upgrades": []
    },
    {
      "runtime": "Asset Hub",
      "short": "AH",
      "repo": "polkadot-fellows/runtimes",
      "branch": "main",
      "cargo_lock_path": "Cargo.lock",
      "cargo_toml_path": "system-parachains/asset-hubs/asset-hub-polkadot/Cargo.toml",
      "spec_version_path": "system-parachains/asset-hubs/asset-hub-polkadot/src/lib.rs",
      "network": "Polkadot",
      "rpc": "https://polkadot-asset-hub-rpc.polkadot.io",
      "ws": "wss://polkadot-asset-hub-rpc.polkadot.io",
      "field_name": "AH Polkadot",
      "block_explorer_url": "https://assethub-polkadot.subscan.io",
      "upgrades": []
    }
  ],
  "releases": []
}
EOF

echo "==> Step 1: Discover releases"
"$TRACKER" --sdk-repo "$SDK_REPO" --step discover

echo "==> Step 2: Check on-chain upgrades"
"$TRACKER" --sdk-repo "$SDK_REPO" --step onchain

echo "==> Step 3: Check downstream + annotate (dry-run)"
"$TRACKER" --sdk-repo "$SDK_REPO" --dry-run --step annotate

RELEASES=$(python3 -c "import json; d=json.load(open('$STATE_PATH')); print(len(d['releases']))")
CRATES=$(python3 -c "import json; d=json.load(open('$STATE_PATH')); print(sum(len(r['crates']) for r in d['releases']))")
UPGRADES=$(python3 -c "import json; d=json.load(open('$STATE_PATH')); print(sum(len(rt['upgrades']) for rt in d['runtimes']))")

echo ""
echo "==> Bootstrap complete"
echo "    Releases: $RELEASES"
echo "    Crate entries: $CRATES"
echo "    On-chain upgrades: $UPGRADES"
echo "    State: $STATE_PATH"
