use anyhow::{Context, Result};
use std::collections::{HashMap, HashSet};

use crate::github::GitHubClient;
use crate::state::State;

struct ProjectInfo {
    project_id: String,
    fields: HashMap<String, FieldInfo>,
}

struct FieldInfo {
    id: String,
}

/// Annotate PRs in the GitHub Project V2.
pub async fn annotate(state: &State, gh: &GitHubClient, dry_run: bool) -> Result<()> {
    let project = fetch_project_info(gh, &state.project.org, state.project.number).await?;
    eprintln!("  Project ID: {}", project.project_id);
    eprintln!("  Fields: {:?}", project.fields.keys().collect::<Vec<_>>());

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

    let unique_prs: HashSet<u64> = pr_tags.keys().copied().collect();
    eprintln!("  {} unique PRs to annotate", unique_prs.len());

    if dry_run {
        for (pr, tags) in &pr_tags {
            eprintln!("    PR #{pr}: {}", tags.join(", "));
        }
        return Ok(());
    }

    // Ensure "Release Tags" field exists
    let release_tags_field = match project.fields.get("Release Tags") {
        Some(f) => f.id.clone(),
        None => {
            eprintln!("  Creating 'Release Tags' field...");
            create_text_field(gh, &project.project_id, "Release Tags").await?
        }
    };

    // Ensure per-runtime fields exist
    let mut runtime_field_ids: HashMap<String, String> = HashMap::new();
    for runtime in &state.runtimes {
        let field_id = match project.fields.get(&runtime.field_name) {
            Some(f) => f.id.clone(),
            None => {
                eprintln!("  Creating '{}' field...", runtime.field_name);
                create_text_field(gh, &project.project_id, &runtime.field_name).await?
            }
        };
        runtime_field_ids.insert(runtime.field_name.clone(), field_id);
    }

    // Process each PR
    for (&pr_number, tags) in &pr_tags {
        let pr_node_id = match get_pr_node_id(gh, "paritytech", "polkadot-sdk", pr_number).await {
            Ok(id) => id,
            Err(e) => {
                eprintln!("    PR #{pr_number}: could not fetch node ID: {e}");
                continue;
            }
        };

        // Add PR to project
        let item_id = add_item_to_project(gh, &project.project_id, &pr_node_id).await?;

        // Set "Release Tags" field
        let tags_value = tags.join(", ");
        set_field_value(gh, &project.project_id, &item_id, &release_tags_field, &tags_value).await?;

        // Set per-runtime status fields
        for runtime in &state.runtimes {
            if let Some(field_id) = runtime_field_ids.get(&runtime.field_name) {
                let status = compute_runtime_status(state, runtime, pr_number);
                if !status.is_empty() {
                    set_field_value(gh, &project.project_id, &item_id, field_id, &status).await?;
                }
            }
        }

        eprintln!("    PR #{pr_number}: {tags_value}");
    }

    Ok(())
}

fn compute_runtime_status(
    state: &State,
    runtime: &crate::state::Runtime,
    pr_number: u64,
) -> String {
    // Find which crates from this PR are relevant to this runtime
    let mut pr_crates: Vec<String> = Vec::new();
    for release in &state.releases {
        for crate_rel in &release.crates {
            if crate_rel.prs.contains(&pr_number) {
                if !pr_crates.contains(&crate_rel.name) {
                    pr_crates.push(crate_rel.name.clone());
                }
            }
        }
    }

    if pr_crates.is_empty() {
        return String::new();
    }

    let latest_spec = runtime
        .upgrades
        .iter()
        .map(|u| u.spec_version)
        .max()
        .unwrap_or(0);

    // For now, just report the latest on-chain spec if any upgrades exist
    if latest_spec > 0 {
        format!("v{latest_spec}")
    } else {
        String::new()
    }
}

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
                fields.insert(
                    name.to_string(),
                    FieldInfo {
                        id: id.to_string(),
                    },
                );
            }
        }
    }

    Ok(ProjectInfo { project_id, fields })
}

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
