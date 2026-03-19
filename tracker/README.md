# Tracker

*Tracks when polkadot-sdk PRs reach downstream runtimes and go live on-chain.*

Tracker monitors [Polkadot SDK](https://github.com/paritytech/polkadot-sdk) releases, checks whether downstream runtimes have adopted the changes, verifies on-chain deployment, and annotates a GitHub Project with per-PR deployment status.

## How It Works

Tracker runs a four-step pipeline, each step building on the previous:

1. **Discover** -- reads [`releases-v1.json`](../releases-v1.json) to find new release tags, extracts crate version bumps and maps them to PRs via commit messages and [prdoc](https://github.com/nickvdp/prdoc) files
2. **Downstream** -- fetches `Cargo.lock` / `Cargo.toml` from downstream runtime repos (e.g. [paseo-network/runtimes](https://github.com/paseo-network/runtimes)) to check which crate versions have been adopted
3. **Onchain** -- connects to live chains via WebSocket RPC, binary-searches for runtime upgrade blocks, and records spec version, block number, and timestamp
4. **Annotate** -- updates a GitHub Project V2, tagging each PR with its release and a per-runtime deployment status:

| Status | Meaning |
|--------|---------|
| *(empty)* | Crates not yet picked up downstream |
| `pending > v{spec}` | Picked up, spec version not yet bumped |
| `pending v{spec}` | Spec bumped in code, not yet enacted on-chain |
| `v{spec}` | Live on-chain |

Partial adoption is shown as a suffix, e.g. `v1002300 (2/3 crates)`.

## Quick Start

<details>
<summary>Prerequisites</summary>

- Rust 1.70+
- A `GITHUB_TOKEN` with access to the target repos and project

</details>

```bash
cargo build --release -p tracker
```

## Usage

```bash
# Run the full pipeline
GITHUB_TOKEN=xxx ./target/release/tracker

# Preview without modifying state or GitHub
GITHUB_TOKEN=xxx ./target/release/tracker --dry-run

# Run a single step
GITHUB_TOKEN=xxx ./target/release/tracker --step discover
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | `false` | Run without writing state or updating GitHub |
| `--step <STEP>` | all | Run only one step: `discover`, `downstream`, `onchain`, `annotate` |
| `--state-path <PATH>` | `../state.json` | Path to the persistent state file |

## Configuration

All configuration lives in [`state.json`](./state.json). It defines which GitHub Project to annotate and which downstream runtimes to track:

```jsonc
{
  "project": { "org": "paritytech", "number": 274 },
  "runtimes": [
    {
      "runtime": "asset-hub-paseo",
      "short": "AH Paseo",
      "repo": "paseo-network/runtimes",
      "branch": "main",
      "rpc": "wss://asset-hub-paseo-rpc.dwellir.com",
      "in_repo": false
      // ...
    }
  ]
}
```

Runtimes with `"in_repo": true` (e.g. Asset Hub Westend, which lives in polkadot-sdk itself) skip version matching and assume all PRs are adopted once merged.

## Testing

```bash
# Unit tests
cargo test --lib -p tracker

# Integration tests (require GITHUB_TOKEN)
GITHUB_TOKEN=xxx cargo test -p tracker
```

