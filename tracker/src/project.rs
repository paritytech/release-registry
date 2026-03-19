use anyhow::{Context, Result};
use std::collections::HashMap;

use crate::github::GitHubClient;
use crate::releases::{SDK_OWNER, SDK_REPO};
use crate::state::State;

/// Fetched GitHub Project V2 metadata.
struct ProjectInfo {
    /// Global node ID of the project.
    project_id: String,
    /// Field name -> field node ID.
    fields: HashMap<String, String>,
}


/// Build a lookup from PR number to the crates it touches and all known release
/// versions containing that PR. We collect all versions rather than just the
/// earliest because polkadot-sdk publishes crate versions from independent
/// release branches, and a higher version number does not guarantee it contains
/// all changes from a lower one.
fn build_pr_crate_map(state: &State) -> HashMap<u64, HashMap<String, Vec<String>>> {
    let mut map: HashMap<u64, HashMap<String, Vec<String>>> = HashMap::new();
    for release in &state.releases {
        for crate_rel in &release.crates {
            for &pr in &crate_rel.prs {
                let versions = map.entry(pr)
                    .or_default()
                    .entry(crate_rel.name.clone())
                    .or_default();
                if !versions.contains(&crate_rel.version) {
                    versions.push(crate_rel.version.clone());
                }
            }
        }
    }
    map
}

/// Format runtime status annotations for a PR as `" [AH Paseo=v2000006]"` or empty.
fn format_status_summary(state: &State, pr_crates: &HashMap<u64, HashMap<String, Vec<String>>>, pr: u64) -> String {
    let mut parts = Vec::new();
    let crates = pr_crates.get(&pr);
    for runtime in &state.runtimes {
        let status = compute_runtime_status(runtime, crates);
        if !status.is_empty() {
            parts.push(format!("{}={}", runtime.field_name, status));
        }
    }
    if parts.is_empty() {
        String::new()
    } else {
        format!(" [{}]", parts.join(", "))
    }
}

/// Annotate PRs in the GitHub Project V2.
pub async fn annotate(state: &State, gh: &GitHubClient, dry_run: bool) -> Result<()> {
    log::info!("Annotate GitHub Project");
    let project = fetch_project_info(gh, &state.project.org, state.project.number).await?;
    log::debug!("Project ID: {}", project.project_id);
    log::debug!("Fields: {:?}", project.fields.keys().collect::<Vec<_>>());

    // Build PR -> release tags mapping
    let mut pr_tags: HashMap<u64, Vec<String>> = HashMap::new();
    for release in &state.releases {
        for crate_rel in &release.crates {
            for &pr in &crate_rel.prs {
                pr_tags.entry(pr).or_default().push(release.tag.clone());
            }
        }
    }

    // Deduplicate tags per PR
    for tags in pr_tags.values_mut() {
        tags.sort();
        tags.dedup();
    }

    log::info!("{} unique PRs to annotate", pr_tags.len());

    let pr_crates = build_pr_crate_map(state);

    if dry_run {
        for (pr, tags) in &pr_tags {
            let status_str = format_status_summary(state, &pr_crates, *pr);
            log::info!("PR #{pr}: {}{status_str}", tags.join(", "));
        }
        return Ok(());
    }

    // Ensure "Release Tags" field exists
    let release_tags_field = match project.fields.get("Release Tags") {
        Some(f) => f.clone(),
        None => {
            log::info!("Creating 'Release Tags' field...");
            create_text_field(gh, &project.project_id, "Release Tags").await?
        }
    };

    // Ensure per-runtime fields exist
    let mut runtime_field_ids: HashMap<String, String> = HashMap::new();
    for runtime in &state.runtimes {
        let field_id = match project.fields.get(&runtime.field_name) {
            Some(f) => f.clone(),
            None => {
                log::info!("Creating '{}' field...", runtime.field_name);
                create_text_field(gh, &project.project_id, &runtime.field_name).await?
            }
        };
        runtime_field_ids.insert(runtime.field_name.clone(), field_id);
    }

    // Process each PR
    for (&pr_number, tags) in &pr_tags {
        let pr_node_id = match get_pr_node_id(gh, SDK_OWNER, SDK_REPO, pr_number).await {
            Ok(id) => id,
            Err(e) => {
                log::warn!("PR #{pr_number}: could not fetch node ID: {e}");
                continue;
            }
        };

        // Add PR to project
        let item_id = add_item_to_project(gh, &project.project_id, &pr_node_id).await?;

        // Set "Release Tags" field
        let tags_value = tags.join(", ");
        set_field_value(gh, &project.project_id, &item_id, &release_tags_field, &tags_value).await?;

        // Set per-runtime status fields (always set, even empty, to clear stale values)
        let crates = pr_crates.get(&pr_number);
        for runtime in &state.runtimes {
            if let Some(field_id) = runtime_field_ids.get(&runtime.field_name) {
                let status = compute_runtime_status(runtime, crates);
                set_field_value(gh, &project.project_id, &item_id, field_id, &status).await?;
            }
        }

        let status_str = format_status_summary(state, &pr_crates, pr_number);
        log::debug!("PR #{pr_number}: {tags_value}{status_str}");
    }

    Ok(())
}

/// Compute the per-runtime status for a PR following the state machine:
///   (empty)                        - crates not picked up by downstream
///   pending > v{onchain_spec}      - picked up, spec not bumped
///   pending v{new_spec}            - picked up, spec bumped, not enacted on-chain
///   v{spec}                        - enacted on-chain
/// Partial adoption appends ` (N/M crates)`.
fn compute_runtime_status(
    runtime: &crate::state::Runtime,
    pr_release_crates: Option<&HashMap<String, Vec<String>>>,
) -> String {
    let pr_release_crates = match pr_release_crates {
        Some(c) if !c.is_empty() => c,
        _ => return String::new(),
    };

    // For in-repo runtimes, every PR on master is already adopted.
    // Skip deps filtering and version matching entirely.
    let (adopted, total) = if runtime.in_repo {
        let total = pr_release_crates.len();
        (total, total)
    } else {
        // Filter to crates that are actual dependencies of this runtime
        let relevant: Vec<_> = pr_release_crates
            .keys()
            .filter(|name| runtime.downstream.deps.contains(name.as_str()))
            .cloned()
            .collect();

        if relevant.is_empty() {
            return String::new();
        }

        // Count how many relevant crates have a downstream version that matches one
        // of the known release versions containing this PR. We use exact matching
        // rather than >= because polkadot-sdk publishes from independent release
        // branches, and a higher version does not imply it contains the same backports.
        let adopted = relevant
            .iter()
            .filter(|name| {
                let release_versions = pr_release_crates.get(name.as_str());
                let lock_ver = runtime.downstream.versions.get(name.as_str());
                matches!((release_versions, lock_ver), (Some(versions), Some(l)) if versions.iter().any(|v| v == l))
            })
            .count();

        (adopted, relevant.len())
    };

    if adopted == 0 {
        return String::new();
    }

    let partial_suffix = if adopted < total {
        format!(" ({adopted}/{total} crates)")
    } else {
        String::new()
    };

    let onchain_spec = runtime
        .upgrades
        .iter()
        .map(|u| u.spec_version)
        .max()
        .unwrap_or(0);
    let code_spec = runtime.downstream.spec_version.unwrap_or(0);

    if code_spec > onchain_spec {
        format!("pending v{code_spec}{partial_suffix}")
    } else if onchain_spec > 0 {
        format!("v{onchain_spec}{partial_suffix}")
    } else {
        format!("pending > v{code_spec}{partial_suffix}")
    }
}

/// Fetch project ID and field definitions via GraphQL.
async fn fetch_project_info(gh: &GitHubClient, org: &str, number: u64) -> Result<ProjectInfo> {
    let query = r#"
        query($org: String!, $number: Int!) {
            organization(login: $org) {
                projectV2(number: $number) {
                    id
                    fields(first: 50) {
                        nodes {
                            ... on ProjectV2Field {
                                id
                                name
                            }
                            ... on ProjectV2SingleSelectField {
                                id
                                name
                            }
                            ... on ProjectV2IterationField {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
    "#;

    let vars = serde_json::json!({
        "org": org,
        "number": number as i64,
    });

    let resp = gh.graphql_query(query, vars).await?;
    let project = &resp["data"]["organization"]["projectV2"];

    let project_id = project["id"]
        .as_str()
        .context("no project ID")?
        .to_string();

    let mut fields = HashMap::new();
    if let Some(nodes) = project["fields"]["nodes"].as_array() {
        for node in nodes {
            if let (Some(id), Some(name)) = (node["id"].as_str(), node["name"].as_str()) {
                fields.insert(name.to_string(), id.to_string());
            }
        }
    }

    Ok(ProjectInfo { project_id, fields })
}

/// Create a TEXT field on a Project V2, returning its node ID.
async fn create_text_field(gh: &GitHubClient, project_id: &str, name: &str) -> Result<String> {
    let query = r#"
        mutation($projectId: ID!, $name: String!) {
            createProjectV2Field(input: {
                projectId: $projectId,
                dataType: TEXT,
                name: $name
            }) {
                projectV2Field {
                    ... on ProjectV2Field {
                        id
                    }
                }
            }
        }
    "#;

    let vars = serde_json::json!({
        "projectId": project_id,
        "name": name,
    });

    let resp = gh.graphql_query(query, vars).await?;
    resp["data"]["createProjectV2Field"]["projectV2Field"]["id"]
        .as_str()
        .map(String::from)
        .context("no field ID in response")
}

/// Fetch the GraphQL node ID of a pull request.
async fn get_pr_node_id(gh: &GitHubClient, owner: &str, repo: &str, number: u64) -> Result<String> {
    let query = r#"
        query($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                pullRequest(number: $number) {
                    id
                }
            }
        }
    "#;

    let vars = serde_json::json!({
        "owner": owner,
        "repo": repo,
        "number": number as i64,
    });

    let resp = gh.graphql_query(query, vars).await?;
    resp["data"]["repository"]["pullRequest"]["id"]
        .as_str()
        .map(String::from)
        .context("no PR node ID")
}

/// Add a content node (PR/issue) to a Project V2, returning the item ID.
async fn add_item_to_project(
    gh: &GitHubClient,
    project_id: &str,
    content_id: &str,
) -> Result<String> {
    let query = r#"
        mutation($projectId: ID!, $contentId: ID!) {
            addProjectV2ItemById(input: {
                projectId: $projectId,
                contentId: $contentId
            }) {
                item {
                    id
                }
            }
        }
    "#;

    let vars = serde_json::json!({
        "projectId": project_id,
        "contentId": content_id,
    });

    let resp = gh.graphql_query(query, vars).await?;
    resp["data"]["addProjectV2ItemById"]["item"]["id"]
        .as_str()
        .map(String::from)
        .context("no item ID in response")
}

/// Set a text field value on a project item.
async fn set_field_value(
    gh: &GitHubClient,
    project_id: &str,
    item_id: &str,
    field_id: &str,
    value: &str,
) -> Result<()> {
    let query = r#"
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: String!) {
            updateProjectV2ItemFieldValue(input: {
                projectId: $projectId,
                itemId: $itemId,
                fieldId: $fieldId,
                value: { text: $value }
            }) {
                projectV2Item {
                    id
                }
            }
        }
    "#;

    let vars = serde_json::json!({
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "value": value,
    });

    gh.graphql_query(query, vars).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::*;
    use std::collections::{HashMap, HashSet};

    fn make_state(releases: Vec<Release>, runtimes: Vec<Runtime>) -> State {
        State {
            project: Project { org: "test".into(), number: 1 },
            runtimes,
            last_processed_tags_date: None,
            releases,
        }
    }

    fn make_upgrade(spec_version: u64) -> Upgrade {
        Upgrade {
            spec_version,
            block_number: 100,
            block_hash: "0x00".into(),
            date: "2025-01-01".into(),
            block_url: "https://explorer/100".into(),
        }
    }

    fn make_runtime(
        versions: HashMap<String, String>,
        deps: HashSet<String>,
        spec_version: Option<u64>,
        upgrades: Vec<Upgrade>,
    ) -> Runtime {
        Runtime {
            runtime: "test-runtime".into(),
            short: "TR".into(),
            repo: "org/repo".into(),
            branch: "main".into(),
            cargo_lock_path: "Cargo.lock".into(),
            cargo_toml_path: "Cargo.toml".into(),
            spec_version_path: "lib.rs".into(),
            network: "testnet".into(),
            rpc: "https://rpc".into(),
            ws: "wss://ws".into(),
            field_name: "TR Test".into(),
            block_explorer_url: "https://explorer".into(),
            in_repo: false,
            last_seen_commit: None,
            upgrades,
            downstream: DownstreamInfo { versions, deps, spec_version },
        }
    }

    #[test]
    fn build_pr_crate_map_basic() {
        let state = make_state(vec![
            Release {
                tag: "v1".into(),
                prev_tag: "v0".into(),
                crates: vec![
                    CrateRelease { name: "crate-a".into(), version: "1.0.0".into(), published: "2025-01-01".into(), prs: vec![10, 20] },
                ],
            },
        ], vec![]);

        let map = build_pr_crate_map(&state);
        assert_eq!(map[&10]["crate-a"], vec!["1.0.0"]);
        assert_eq!(map[&20]["crate-a"], vec!["1.0.0"]);
    }

    #[test]
    fn build_pr_crate_map_collects_all_versions() {
        let state = make_state(vec![
            Release {
                tag: "v1".into(),
                prev_tag: "v0".into(),
                crates: vec![
                    CrateRelease { name: "crate-a".into(), version: "1.0.0".into(), published: "2025-01-01".into(), prs: vec![10] },
                ],
            },
            Release {
                tag: "v2".into(),
                prev_tag: "v1".into(),
                crates: vec![
                    CrateRelease { name: "crate-a".into(), version: "2.0.0".into(), published: "2025-02-01".into(), prs: vec![10] },
                ],
            },
        ], vec![]);

        let map = build_pr_crate_map(&state);
        assert_eq!(map[&10]["crate-a"], vec!["1.0.0", "2.0.0"]);
    }

    #[test]
    fn compute_runtime_status_no_crates() {
        let rt = make_runtime(HashMap::new(), HashSet::new(), None, vec![]);
        assert_eq!(compute_runtime_status(&rt, None), "");
    }

    #[test]
    fn compute_runtime_status_not_in_deps() {
        let rt = make_runtime(HashMap::new(), HashSet::new(), None, vec![]);
        let crates = HashMap::from([("crate-a".into(), vec!["1.0.0".into()])]);
        assert_eq!(compute_runtime_status(&rt, Some(&crates)), "");
    }

    #[test]
    fn compute_runtime_status_adopted_enacted() {
        let rt = make_runtime(
            HashMap::from([("crate-a".into(), "1.0.0".into())]),
            HashSet::from(["crate-a".into()]),
            Some(2000006),
            vec![make_upgrade(2000006)],
        );
        let crates = HashMap::from([("crate-a".into(), vec!["1.0.0".into()])]);
        assert_eq!(compute_runtime_status(&rt, Some(&crates)), "v2000006");
    }

    #[test]
    fn compute_runtime_status_adopted_pending() {
        let rt = make_runtime(
            HashMap::from([("crate-a".into(), "1.0.0".into())]),
            HashSet::from(["crate-a".into()]),
            Some(3000000),
            vec![make_upgrade(2000006)],
        );
        let crates = HashMap::from([("crate-a".into(), vec!["1.0.0".into()])]);
        assert_eq!(compute_runtime_status(&rt, Some(&crates)), "pending v3000000");
    }

    #[test]
    fn compute_runtime_status_partial_adoption() {
        let rt = make_runtime(
            HashMap::from([("crate-a".into(), "2.0.0".into())]),
            HashSet::from(["crate-a".into(), "crate-b".into()]),
            Some(2000006),
            vec![make_upgrade(2000006)],
        );
        let crates = HashMap::from([
            ("crate-a".into(), vec!["1.0.0".into(), "2.0.0".into()]),
            ("crate-b".into(), vec!["1.0.0".into()]),
        ]);
        assert_eq!(
            compute_runtime_status(&rt, Some(&crates)),
            "v2000006 (1/2 crates)"
        );
    }

    #[test]
    fn compute_runtime_status_version_from_different_branch_not_adopted() {
        let rt = make_runtime(
            // Downstream has version 0.24.1 (from a branch without the backport)
            HashMap::from([("crate-a".into(), "0.24.1".into())]),
            HashSet::from(["crate-a".into()]),
            Some(2000006),
            vec![make_upgrade(2000006)],
        );
        // PR was backported to branches producing 0.21.1, 0.23.1, and 0.25.0
        let crates = HashMap::from([("crate-a".into(), vec![
            "0.21.1".into(), "0.23.1".into(), "0.25.0".into(),
        ])]);
        // 0.24.1 is not in the known versions, so not adopted
        assert_eq!(compute_runtime_status(&rt, Some(&crates)), "");
    }

    #[test]
    fn compute_runtime_status_in_repo_enacted() {
        let mut rt = make_runtime(
            HashMap::new(),
            HashSet::new(),
            Some(1022001),
            vec![make_upgrade(1022001)],
        );
        rt.in_repo = true;
        let crates = HashMap::from([("crate-a".into(), vec!["1.0.0".into()])]);
        assert_eq!(compute_runtime_status(&rt, Some(&crates)), "v1022001");
    }

    #[test]
    fn compute_runtime_status_in_repo_pending() {
        let mut rt = make_runtime(
            HashMap::new(),
            HashSet::new(),
            Some(1023000),
            vec![make_upgrade(1022001)],
        );
        rt.in_repo = true;
        let crates = HashMap::from([("crate-a".into(), vec!["1.0.0".into()])]);
        assert_eq!(compute_runtime_status(&rt, Some(&crates)), "pending v1023000");
    }

    #[test]
    fn compute_runtime_status_in_repo_no_crates() {
        let mut rt = make_runtime(
            HashMap::new(),
            HashSet::new(),
            Some(1022001),
            vec![make_upgrade(1022001)],
        );
        rt.in_repo = true;
        assert_eq!(compute_runtime_status(&rt, None), "");
    }
}
