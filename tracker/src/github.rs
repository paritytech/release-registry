use anyhow::{bail, Context, Result};
use base64::Engine;
use reqwest::header::{ACCEPT, AUTHORIZATION, USER_AGENT};
use serde::de::DeserializeOwned;
use serde_json::Value;

/// HTTP client for GitHub REST and GraphQL APIs.
pub struct GitHubClient {
    /// Underlying HTTP client.
    client: reqwest::Client,
    /// Personal access token.
    token: String,
}

impl GitHubClient {
    /// Create a new client with the given token.
    pub fn new(token: String) -> Self {
        Self {
            client: reqwest::Client::new(),
            token,
        }
    }

    /// GET a URL and deserialize the JSON response.
    pub async fn get_json<T: DeserializeOwned>(&self, url: &str) -> Result<T> {
        let resp = self
            .client
            .get(url)
            .header(AUTHORIZATION, format!("Bearer {}", self.token))
            .header(USER_AGENT, "tracker")
            .header(ACCEPT, "application/vnd.github.v3+json")
            .send()
            .await?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            bail!("GET {url} returned {status}: {body}");
        }
        Ok(resp.json().await?)
    }

    /// Compare two refs, returning the full JSON response.
    pub async fn compare_tags(&self, owner: &str, repo: &str, base: &str, head: &str) -> Result<Value> {
        let url = format!(
            "https://api.github.com/repos/{owner}/{repo}/compare/{base}...{head}"
        );
        self.get_json(&url).await
    }

    /// Fetch file content (base64-decoded) at a given ref.
    pub async fn get_file_content(
        &self,
        owner: &str,
        repo: &str,
        path: &str,
        git_ref: &str,
    ) -> Result<String> {
        let url = format!(
            "https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={git_ref}"
        );
        let resp: Value = self.get_json(&url).await?;
        let encoded = resp["content"]
            .as_str()
            .context("no content field")?
            .replace('\n', "");
        let bytes = base64::engine::general_purpose::STANDARD.decode(&encoded)?;
        Ok(String::from_utf8(bytes)?)
    }

    /// Fetch raw file content (for large files that exceed the contents API limit).
    pub async fn get_raw_content(
        &self,
        owner: &str,
        repo: &str,
        path: &str,
        git_ref: &str,
    ) -> Result<String> {
        let url = format!(
            "https://raw.githubusercontent.com/{owner}/{repo}/{git_ref}/{path}"
        );
        let resp = self
            .client
            .get(&url)
            .header(AUTHORIZATION, format!("Bearer {}", self.token))
            .header(USER_AGENT, "tracker")
            .send()
            .await?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            bail!("GET {url} returned {status}: {body}");
        }
        Ok(resp.text().await?)
    }

    /// Execute a GraphQL query.
    pub async fn graphql_query(&self, query: &str, variables: Value) -> Result<Value> {
        let body = serde_json::json!({
            "query": query,
            "variables": variables,
        });

        let resp = self
            .client
            .post("https://api.github.com/graphql")
            .header(AUTHORIZATION, format!("Bearer {}", self.token))
            .header(USER_AGENT, "tracker")
            .json(&body)
            .send()
            .await?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            bail!("GraphQL request returned {status}: {body}");
        }

        let result: Value = resp.json().await?;
        if let Some(errors) = result.get("errors") {
            bail!("GraphQL errors: {errors}");
        }
        Ok(result)
    }

    /// Get latest commit SHA on a branch.
    pub async fn get_latest_commit(
        &self,
        owner: &str,
        repo: &str,
        branch: &str,
    ) -> Result<String> {
        let url = format!(
            "https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
        );
        let resp: Value = self.get_json(&url).await?;
        resp["sha"]
            .as_str()
            .map(String::from)
            .context("no sha in commit response")
    }
}

