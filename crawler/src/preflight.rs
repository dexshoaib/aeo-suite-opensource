use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::fetcher::{fetch_url, FetchError, FetcherConfig};
use crate::pacing::calculate_pacing_ms;
use crate::robots::{evaluate_robots_http_response, RobotsError};
use crate::token::{normalize_host, verify_token};

pub const RESULT_OK: &str = "ok";
pub const RESULT_DISALLOWED_ROBOTS: &str = "disallowed_robots";
pub const RESULT_SSRF_BLOCKED: &str = "ssrf_blocked";
pub const RESULT_REDIRECT_CROSS_DOMAIN: &str = "redirect_cross_domain";
pub const RESULT_DISALLOWED_SCHEME_DOWNGRADE: &str = "disallowed_scheme_downgrade";
pub const RESULT_FETCH_FAILED: &str = "fetch_failed";
pub const RESULT_INVALID_TOKEN: &str = "invalid_token";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PreflightReport {
    pub domain: String,
    pub result: String,
    pub status_code: Option<u16>,
    pub ip_address: Option<String>,
    pub robots_allowed: bool,
    pub crawl_delay_seconds: Option<f64>,
    pub pacing_ms: u64,
    pub error_message: Option<String>,
    pub checked_at: i64,
}

pub struct PreflightOptions<'a> {
    pub token: &'a str,
    pub secret_key: &'a str,
    pub target_domain: Option<&'a str>,
    pub check_path: &'a str,
    pub base_url: Option<&'a str>,
    pub now: Option<i64>,
    pub config: FetcherConfig,
}

pub async fn run_preflight(options: PreflightOptions<'_>) -> PreflightReport {
    let now = options.now.unwrap_or_else(|| {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64
    });

    // 1. Verify token
    let claims = match verify_token(
        options.token,
        options.secret_key,
        options.target_domain,
        Some(now),
    ) {
        Ok(c) => c,
        Err(e) => {
            let fallback_domain = options
                .target_domain
                .map(normalize_host)
                .unwrap_or_else(|| "unknown".to_string());
            return PreflightReport {
                domain: fallback_domain,
                result: RESULT_INVALID_TOKEN.to_string(),
                status_code: None,
                ip_address: None,
                robots_allowed: false,
                crawl_delay_seconds: None,
                pacing_ms: 1000,
                error_message: Some(e.to_string()),
                checked_at: now,
            };
        }
    };

    let domain = claims.dom.clone();

    // 2. Form robots.txt URL
    let robots_url = match options.base_url {
        Some(base) => {
            if base.ends_with('/') {
                format!("{}robots.txt", base)
            } else {
                format!("{}/robots.txt", base)
            }
        }
        None => format!("https://{}/robots.txt", domain),
    };

    // 3. Fetch robots.txt
    let fetch_result = fetch_url(&robots_url, &domain, &options.config).await;

    let response = match fetch_result {
        Ok(resp) => resp,
        Err(err) => {
            let (result_code, err_msg) = match err {
                FetchError::CrossDomainRedirect {
                    target_host,
                    token_domain,
                } => (
                    RESULT_REDIRECT_CROSS_DOMAIN,
                    format!(
                        "Redirect to cross-domain {} forbidden (token domain: {})",
                        target_host, token_domain
                    ),
                ),
                FetchError::DisallowedSchemeDowngrade => (
                    RESULT_DISALLOWED_SCHEME_DOWNGRADE,
                    "Redirect downgrade from HTTPS to HTTP forbidden".to_string(),
                ),
                FetchError::Ssrf(ssrf_err) => (
                    RESULT_SSRF_BLOCKED,
                    format!("SSRF boundary check rejected host: {}", ssrf_err),
                ),
                FetchError::ForbiddenPort(p) => (
                    RESULT_SSRF_BLOCKED,
                    format!("Non-standard port {} forbidden", p),
                ),
                FetchError::EmbeddedCredentials => (
                    RESULT_SSRF_BLOCKED,
                    "Embedded credentials forbidden in URL".to_string(),
                ),
                other => (
                    RESULT_FETCH_FAILED,
                    format!("Failed to retrieve robots.txt: {}", other),
                ),
            };

            return PreflightReport {
                domain,
                result: result_code.to_string(),
                status_code: None,
                ip_address: None,
                robots_allowed: false,
                crawl_delay_seconds: None,
                pacing_ms: 1000,
                error_message: Some(err_msg),
                checked_at: now,
            };
        }
    };

    // 4. Evaluate robots.txt HTTP response status & content
    let status_code = response.status;
    let ip_str = response.ip_address.to_string();
    let body_str = String::from_utf8_lossy(&response.body);

    let robots_eval = evaluate_robots_http_response(
        status_code,
        Some(&body_str),
        options.check_path,
        "AEOSuiteBot",
    );

    match robots_eval {
        Ok(eval) => {
            let pacing_ms = calculate_pacing_ms(eval.crawl_delay_seconds);
            if eval.allowed {
                PreflightReport {
                    domain,
                    result: RESULT_OK.to_string(),
                    status_code: Some(status_code),
                    ip_address: Some(ip_str),
                    robots_allowed: true,
                    crawl_delay_seconds: eval.crawl_delay_seconds,
                    pacing_ms,
                    error_message: None,
                    checked_at: now,
                }
            } else {
                PreflightReport {
                    domain,
                    result: RESULT_DISALLOWED_ROBOTS.to_string(),
                    status_code: Some(status_code),
                    ip_address: Some(ip_str),
                    robots_allowed: false,
                    crawl_delay_seconds: eval.crawl_delay_seconds,
                    pacing_ms,
                    error_message: Some(format!(
                        "Path {} disallowed by robots.txt rule: {:?}",
                        options.check_path, eval.matching_pattern
                    )),
                    checked_at: now,
                }
            }
        }
        Err(err) => {
            let (result_code, msg) = match err {
                RobotsError::RateLimited => (
                    RESULT_DISALLOWED_ROBOTS,
                    "robots.txt responded with HTTP 429 Too Many Requests (backoff required)"
                        .to_string(),
                ),
                RobotsError::ServerError(code) => (
                    RESULT_DISALLOWED_ROBOTS,
                    format!(
                        "robots.txt responded with HTTP {} server error (fail-closed per RFC 9309)",
                        code
                    ),
                ),
                RobotsError::ClientError(code) => (
                    RESULT_DISALLOWED_ROBOTS,
                    format!(
                        "robots.txt responded with HTTP {} client error (fail-closed per product decision)",
                        code
                    ),
                ),
                RobotsError::HttpStatusError(code) => (
                    RESULT_FETCH_FAILED,
                    format!("robots.txt responded with unexpected HTTP status {}", code),
                ),
            };

            PreflightReport {
                domain,
                result: result_code.to_string(),
                status_code: Some(status_code),
                ip_address: Some(ip_str),
                robots_allowed: false,
                crawl_delay_seconds: None,
                pacing_ms: 1000,
                error_message: Some(msg),
                checked_at: now,
            }
        }
    }
}
