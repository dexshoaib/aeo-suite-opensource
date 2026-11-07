use std::net::{IpAddr, SocketAddr};
use std::time::Duration;
use thiserror::Error;
use url::Url;

use crate::ssrf::{resolve_and_pin_ip_with_options, SsrfError};
use crate::token::normalize_host;

pub const DEFAULT_USER_AGENT: &str = "AEOSuiteBot/1.0 (+https://app.example-aeo.com/bot)";
pub const DEFAULT_MAX_BODY_BYTES: usize = 10 * 1024 * 1024; // 10 MB
pub const DEFAULT_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const DEFAULT_TOTAL_TIMEOUT: Duration = Duration::from_secs(30);
pub const DEFAULT_MAX_REDIRECTS: usize = 5;

#[derive(Error, Debug, PartialEq)]
pub enum FetchError {
    #[error("Unsupported scheme: {0}")]
    UnsupportedScheme(String),
    #[error("Forbidden port {0}")]
    ForbiddenPort(u16),
    #[error("Embedded credentials in URL forbidden")]
    EmbeddedCredentials,
    #[error("Redirect downgrade from HTTPS to HTTP forbidden")]
    DisallowedSchemeDowngrade,
    #[error("Cross-domain redirect forbidden: {target_host} != {token_domain}")]
    CrossDomainRedirect {
        target_host: String,
        token_domain: String,
    },
    #[error("Too many redirects (limit {0})")]
    TooManyRedirects(usize),
    #[error("Response body exceeded 10 MB limit")]
    BodyTooLarge,
    #[error("Request timed out: {0}")]
    Timeout(String),
    #[error("SSRF check failed: {0}")]
    Ssrf(#[from] SsrfError),
    #[error("HTTP error: {0}")]
    Http(String),
    #[error("Invalid URL: {0}")]
    InvalidUrl(String),
    #[error("Missing Location header on redirect")]
    MissingLocation,
}

#[derive(Debug, Clone)]
pub struct FetcherConfig {
    pub user_agent: String,
    pub max_body_bytes: usize,
    pub connect_timeout: Duration,
    pub total_timeout: Duration,
    pub max_redirects: usize,
    pub allow_loopback: bool,
    pub allow_custom_ports: bool,
}

impl Default for FetcherConfig {
    fn default() -> Self {
        FetcherConfig {
            user_agent: DEFAULT_USER_AGENT.to_string(),
            max_body_bytes: DEFAULT_MAX_BODY_BYTES,
            connect_timeout: DEFAULT_CONNECT_TIMEOUT,
            total_timeout: DEFAULT_TOTAL_TIMEOUT,
            max_redirects: DEFAULT_MAX_REDIRECTS,
            allow_loopback: false,
            allow_custom_ports: false,
        }
    }
}

impl FetcherConfig {
    /// Configuration preset for tests running against local Wiremock instances
    pub fn test_config() -> Self {
        FetcherConfig {
            user_agent: DEFAULT_USER_AGENT.to_string(),
            max_body_bytes: DEFAULT_MAX_BODY_BYTES,
            connect_timeout: Duration::from_secs(5),
            total_timeout: Duration::from_secs(5),
            max_redirects: DEFAULT_MAX_REDIRECTS,
            allow_loopback: true,
            allow_custom_ports: true,
        }
    }
}

#[derive(Debug, Clone)]
pub struct FetchResponse {
    pub final_url: String,
    pub status: u16,
    pub headers: reqwest::header::HeaderMap,
    pub body: Vec<u8>,
    pub ip_address: IpAddr,
}

/// Fetch a target URL with pinned IP transport, strict domain gating, and streaming body cap
pub async fn fetch_url(
    url_str: &str,
    token_domain: &str,
    config: &FetcherConfig,
) -> Result<FetchResponse, FetchError> {
    let normalized_token_domain = normalize_host(token_domain);
    let mut current_url = Url::parse(url_str).map_err(|e| FetchError::InvalidUrl(e.to_string()))?;
    let mut redirect_count = 0;

    loop {
        // 1. Validate scheme
        let scheme = current_url.scheme();
        if scheme != "http" && scheme != "https" {
            return Err(FetchError::UnsupportedScheme(scheme.to_string()));
        }

        // 2. Validate port
        let port = match current_url.port() {
            Some(p) => {
                if !config.allow_custom_ports {
                    if scheme == "http" && p != 80 {
                        return Err(FetchError::ForbiddenPort(p));
                    }
                    if scheme == "https" && p != 443 {
                        return Err(FetchError::ForbiddenPort(p));
                    }
                }
                p
            }
            None => {
                if scheme == "http" {
                    80
                } else {
                    443
                }
            }
        };

        // 3. Validate userinfo
        if !current_url.username().is_empty() || current_url.password().is_some() {
            return Err(FetchError::EmbeddedCredentials);
        }

        // 4. Validate domain matches token domain
        let host_str = current_url
            .host_str()
            .ok_or_else(|| FetchError::InvalidUrl("Missing host".into()))?;
        let normalized_host = normalize_host(host_str);
        if normalized_host != normalized_token_domain {
            return Err(FetchError::CrossDomainRedirect {
                target_host: normalized_host,
                token_domain: normalized_token_domain,
            });
        }

        // 5. SSRF validation & IP pinning
        let pinned_ip =
            resolve_and_pin_ip_with_options(host_str, port, config.allow_loopback).await?;
        let socket_addr = SocketAddr::new(pinned_ip, port);

        // 6. Build HTTP client with pinned DNS resolution
        let client = reqwest::Client::builder()
            .resolve(host_str, socket_addr)
            .connect_timeout(config.connect_timeout)
            .timeout(config.total_timeout)
            .redirect(reqwest::redirect::Policy::none())
            .user_agent(&config.user_agent)
            .build()
            .map_err(|e| FetchError::Http(e.to_string()))?;

        // 7. Execute request
        let response = client.get(current_url.clone()).send().await.map_err(|e| {
            if e.is_timeout() {
                FetchError::Timeout(e.to_string())
            } else {
                FetchError::Http(e.to_string())
            }
        })?;

        // 8. Handle redirects manually
        let status = response.status().as_u16();
        if (300..400).contains(&status) {
            redirect_count += 1;
            if redirect_count > config.max_redirects {
                return Err(FetchError::TooManyRedirects(config.max_redirects));
            }

            let location_header = response
                .headers()
                .get(reqwest::header::LOCATION)
                .ok_or(FetchError::MissingLocation)?
                .to_str()
                .map_err(|_| FetchError::InvalidUrl("Non-ASCII Location header".into()))?;

            let next_url = current_url
                .join(location_header)
                .map_err(|e| FetchError::InvalidUrl(e.to_string()))?;

            // Strictly reject HTTPS -> HTTP downgrade
            if current_url.scheme() == "https" && next_url.scheme() == "http" {
                return Err(FetchError::DisallowedSchemeDowngrade);
            }

            current_url = next_url;
            continue;
        }

        // 9. Stream body with hard 10 MB cap
        if let Some(content_length) = response.content_length() {
            if content_length > config.max_body_bytes as u64 {
                return Err(FetchError::BodyTooLarge);
            }
        }

        let headers = response.headers().clone();
        let mut body = Vec::new();
        let mut mut_response = response;

        while let Some(part) = mut_response.chunk().await.map_err(|e| {
            if e.is_timeout() {
                FetchError::Timeout(e.to_string())
            } else {
                FetchError::Http(e.to_string())
            }
        })? {
            if body.len() + part.len() > config.max_body_bytes {
                return Err(FetchError::BodyTooLarge);
            }
            body.extend_from_slice(&part);
        }

        return Ok(FetchResponse {
            final_url: current_url.to_string(),
            status,
            headers,
            body,
            ip_address: pinned_ip,
        });
    }
}
