pub mod fetcher;
pub mod pacing;
pub mod preflight;
pub mod robots;
pub mod ssrf;
pub mod token;

pub use fetcher::{
    fetch_url, FetchError, FetchResponse, FetcherConfig, DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_MAX_BODY_BYTES, DEFAULT_MAX_REDIRECTS, DEFAULT_TOTAL_TIMEOUT, DEFAULT_USER_AGENT,
};
pub use pacing::{calculate_pacing_ms, DEFAULT_PACING_MS, MAX_CONCURRENT_PER_HOST};
pub use preflight::{run_preflight, PreflightOptions, PreflightReport};
pub use robots::{evaluate_robots_http_response, RobotsError, RobotsEvaluation, RobotsTxt, Rule};
pub use ssrf::{
    parse_and_canonicalize_ip, resolve_and_pin_ip, resolve_and_pin_ip_with_options,
    validate_ip_safety, validate_ip_safety_with_options, validate_resolved_addresses, SsrfError,
};
pub use token::{mint_token, normalize_host, verify_token, TokenClaims, TokenError};
