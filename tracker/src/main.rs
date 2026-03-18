mod downstream;
mod github;
mod onchain;
mod project;
mod releases;
mod state;

use anyhow::{Context, Result};
use clap::Parser;
use std::path::PathBuf;

#[derive(Parser)]
#[clap(name = "tracker", about = "PR Deployment Tracker for polkadot-sdk")]
struct Cli {
    /// Run without modifying state or GitHub project
    #[clap(long)]
    dry_run: bool,

    /// Run only a specific step
    #[clap(long, value_parser = ["discover", "downstream", "onchain", "annotate"])]
    step: Option<String>,

    /// Path to state.json (default: ../state.json relative to binary)
    #[clap(long)]
    state_path: Option<PathBuf>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    let token = std::env::var("GITHUB_TOKEN").context("GITHUB_TOKEN env var required")?;
    let gh = github::GitHubClient::new(token);

    let state_path = cli.state_path.unwrap_or_else(|| {
        // Default: state.json in repo root (one level up from tracker/)
        let mut p = std::env::current_dir().unwrap();
        // If we're inside tracker/, go up
        if p.ends_with("tracker") {
            p.pop();
        }
        p.join("state.json")
    });

    eprintln!("Loading state from {}", state_path.display());
    let mut state = state::State::load(&state_path)?;

    let releases_path = state_path
        .parent()
        .unwrap_or(state_path.as_path())
        .join("releases-v1.json");
    let releases_json: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&releases_path)?)?;

    let run_all = cli.step.is_none();
    let step = cli.step.as_deref();

    if run_all || step == Some("discover") {
        eprintln!("\n=== Step 1+2: Discover releases & resolve PRs ===");
        releases::discover_and_resolve(&mut state, &gh, &releases_json, cli.dry_run).await?;
    }

    if run_all || step == Some("downstream") {
        eprintln!("\n=== Step 3: Check downstream consumption ===");
        downstream::check_downstream(&mut state, &gh, cli.dry_run).await?;
    }

    if run_all || step == Some("onchain") {
        eprintln!("\n=== Step 4+5: On-chain queries ===");
        onchain::check_onchain(&mut state.runtimes, &gh, cli.dry_run).await?;
    }

    if run_all || step == Some("annotate") {
        eprintln!("\n=== Step 6: Annotate GitHub Project ===");
        project::annotate(&state, &gh, cli.dry_run).await?;
    }

    if !cli.dry_run {
        eprintln!("\nSaving state to {}", state_path.display());
        state.save(&state_path)?;
    }

    eprintln!("Done.");
    Ok(())
}
