/// Default delay between requests in milliseconds per host (1 second)
pub const DEFAULT_PACING_MS: u64 = 1000;

/// Maximum concurrent requests per host
pub const MAX_CONCURRENT_PER_HOST: usize = 1;

/// Calculate pacing delay in milliseconds from an optional crawl-delay in seconds.
/// Rules:
/// - 1 concurrent request per host
/// - Default 1000ms delay
/// - Preflight reports `pacing_ms = max(robots_crawl_delay, 1000)`
pub fn calculate_pacing_ms(crawl_delay_seconds: Option<f64>) -> u64 {
    match crawl_delay_seconds {
        Some(delay) if delay > 0.0 => {
            let delay_ms = (delay * 1000.0).round() as u64;
            std::cmp::max(delay_ms, DEFAULT_PACING_MS)
        }
        _ => DEFAULT_PACING_MS,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_calculate_pacing_ms() {
        // No crawl delay -> default 1000ms
        assert_eq!(calculate_pacing_ms(None), 1000);

        // Crawl delay less than 1s -> floor is 1000ms
        assert_eq!(calculate_pacing_ms(Some(0.5)), 1000);

        // Crawl delay greater than 1s -> uses robots delay
        assert_eq!(calculate_pacing_ms(Some(2.5)), 2500);
        assert_eq!(calculate_pacing_ms(Some(5.0)), 5000);

        // Zero or negative delay -> default 1000ms
        assert_eq!(calculate_pacing_ms(Some(0.0)), 1000);
        assert_eq!(calculate_pacing_ms(Some(-1.0)), 1000);
    }
}
