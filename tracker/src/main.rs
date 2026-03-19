//! PR Deployment Tracker for polkadot-sdk releases.
//!
//! Tracks when PRs merged in polkadot-sdk reach downstream runtimes and go live on-chain,
//! annotating a GitHub Project V2 with release tags and per-runtime deployment status.

/// Downstream runtime consumption checks.
mod downstream;
/// GitHub REST and GraphQL API client.
mod github;
/// On-chain spec version tracking via Substrate RPC.
mod onchain;
/// GitHub Project V2 annotation logic.
mod project;
/// Release discovery and PR resolution.
mod releases;
/// Persistent tracker state.
mod state;

use anyhow::{Context, Result};
use clap::Parser;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, PartialEq, Eq, clap::ValueEnum)]
enum Step {
    /// Discover new releases from releases-v1.json and resolve PRs via prdocs.
    Discover,
    /// Check downstream runtimes for crate consumption.
    Downstream,
    /// Query on-chain spec versions and detect runtime upgrades.
    Onchain,
    /// Annotate the GitHub Project V2 with release tags and deployment status.
    Annotate,
}

impl Step {
    const ALL: &[Step] = &[Step::Discover, Step::Downstream, Step::Onchain, Step::Annotate];
}

/// CLI arguments.
#[derive(Parser)]
#[clap(name = "tracker", about = "PR Deployment Tracker for polkadot-sdk")]
struct Cli {
    /// Run without modifying state or GitHub project
    #[clap(long)]
    dry_run: bool,

    /// Run only a specific step
    #[clap(long)]
    step: Option<Step>,

    /// Path to state.json (default: ../state.json relative to binary)
    #[clap(long)]
    state_path: Option<PathBuf>,
}

struct Runner {
    gh: github::GitHubClient,
    state: state::State,
    state_path: PathBuf,
    releases_json: releases::ReleasesJson,
    dry_run: bool,
}

impl Runner {
    async fn run(mut self, steps: &[Step]) -> Result<()> {
        for &step in steps {
            self.run_step(step).await?;
        }

        if !self.dry_run {
            eprintln!("\nSaving state to {}", self.state_path.display());
            self.state.save(&self.state_path)?;
        }

        eprintln!("Done.");
        Ok(())
    }

    async fn run_step(&mut self, step: Step) -> Result<()> {
        match step {
            Step::Discover => {
                releases::discover_and_resolve(&mut self.state, &self.gh, &self.releases_json)
                    .await
            }
            Step::Downstream => {
                downstream::check_downstream(&mut self.state, &self.gh).await
            }
            Step::Onchain => onchain::check_onchain(&mut self.state.runtimes).await,
            Step::Annotate => project::annotate(&self.state, &self.gh, self.dry_run).await,
        }
    }
}

fn resolve_state_path(cli_path: Option<PathBuf>) -> PathBuf {
    cli_path.unwrap_or_else(|| {
        let mut p = std::env::current_dir().unwrap();
        if !p.ends_with("tracker") {
            p.push("tracker");
        }
        p.join("state.json")
    })
}

fn resolve_releases_path(state_path: &Path) -> PathBuf {
    state_path
        .parent()
        .and_then(|p| p.parent())
        .unwrap_or(state_path)
        .join("releases-v1.json")
}

/// Entry point: parse CLI args, load state, run pipeline steps, save state.
#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    let token = std::env::var("GITHUB_TOKEN").context("GITHUB_TOKEN env var required")?;
    let state_path = resolve_state_path(cli.state_path);

    eprintln!("Loading state from {}", state_path.display());
    let state = state::State::load(&state_path)?;
    let releases_json = serde_json::from_str(&std::fs::read_to_string(
        resolve_releases_path(&state_path),
    )?)?;

    let single;
    let steps: &[Step] = match cli.step {
        Some(Step::Annotate) => &[Step::Downstream, Step::Annotate],
        Some(step) => { single = [step]; &single },
        None => Step::ALL,
    };

    let runner = Runner { gh: github::GitHubClient::new(token), state, state_path, releases_json, dry_run: cli.dry_run };
    runner.run(steps).await
}
