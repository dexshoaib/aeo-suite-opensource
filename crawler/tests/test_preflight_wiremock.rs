use crawler::fetcher::{fetch_url, FetchError, FetcherConfig};
use crawler::robots::evaluate_robots_http_response;
use url::Url;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

#[tokio::test]
async fn test_wiremock_safe_fetch_success() {
    let mock_server = MockServer::start().await;
    let body_text = "User-agent: *\nDisallow: /admin\nAllow: /\nCrawl-delay: 2";

    Mock::given(method("GET"))
        .and(path("/robots.txt"))
        .respond_with(
            ResponseTemplate::new(200)
                .set_body_string(body_text)
                .insert_header("content-type", "text/plain"),
        )
        .mount(&mock_server)
        .await;

    let server_url = Url::parse(&mock_server.uri()).unwrap();
    let host = server_url.host_str().unwrap();
    let fetch_url_str = format!("{}/robots.txt", mock_server.uri());

    let config = FetcherConfig::test_config();
    let response = fetch_url(&fetch_url_str, host, &config)
        .await
        .expect("Fetch should succeed");

    assert_eq!(response.status, 200);
    assert_eq!(String::from_utf8(response.body).unwrap(), body_text);
}

#[tokio::test]
async fn test_wiremock_cross_domain_redirect_rejected() {
    let mock_server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/redirect"))
        .respond_with(
            ResponseTemplate::new(302)
                .insert_header("Location", "http://attacker-controlled.com/evil"),
        )
        .mount(&mock_server)
        .await;

    let server_url = Url::parse(&mock_server.uri()).unwrap();
    let host = server_url.host_str().unwrap();
    let fetch_url_str = format!("{}/redirect", mock_server.uri());

    let config = FetcherConfig::test_config();
    let err = fetch_url(&fetch_url_str, host, &config).await.unwrap_err();

    match err {
        FetchError::CrossDomainRedirect {
            target_host,
            token_domain,
        } => {
            assert_eq!(target_host, "attacker-controlled.com");
            assert_eq!(token_domain, host);
        }
        other => panic!("Expected CrossDomainRedirect, got {:?}", other),
    }
}

#[tokio::test]
async fn test_wiremock_same_domain_redirect_followed() {
    let mock_server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/step1"))
        .respond_with(ResponseTemplate::new(301).insert_header("Location", "/step2"))
        .mount(&mock_server)
        .await;

    Mock::given(method("GET"))
        .and(path("/step2"))
        .respond_with(ResponseTemplate::new(200).set_body_string("final destination"))
        .mount(&mock_server)
        .await;

    let server_url = Url::parse(&mock_server.uri()).unwrap();
    let host = server_url.host_str().unwrap();
    let fetch_url_str = format!("{}/step1", mock_server.uri());

    let config = FetcherConfig::test_config();
    let response = fetch_url(&fetch_url_str, host, &config)
        .await
        .expect("Redirect should be followed");

    assert_eq!(response.status, 200);
    assert_eq!(
        String::from_utf8(response.body).unwrap(),
        "final destination"
    );
    assert!(response.final_url.ends_with("/step2"));
}

#[tokio::test]
async fn test_wiremock_body_size_abort() {
    let mock_server = MockServer::start().await;

    // Generate 2 KB payload
    let large_payload = "A".repeat(2048);

    Mock::given(method("GET"))
        .and(path("/large"))
        .respond_with(ResponseTemplate::new(200).set_body_string(large_payload))
        .mount(&mock_server)
        .await;

    let server_url = Url::parse(&mock_server.uri()).unwrap();
    let host = server_url.host_str().unwrap();
    let fetch_url_str = format!("{}/large", mock_server.uri());

    // Configure small body budget (1024 bytes) to test streaming abort
    let mut config = FetcherConfig::test_config();
    config.max_body_bytes = 1024;

    let err = fetch_url(&fetch_url_str, host, &config).await.unwrap_err();

    assert_eq!(err, FetchError::BodyTooLarge);
}

#[tokio::test]
async fn test_wiremock_forbidden_ports_and_credentials() {
    // 1. Non-standard port with default config
    let config = FetcherConfig::default(); // allow_custom_ports: false
    let err = fetch_url("http://example.com:8080/test", "example.com", &config)
        .await
        .unwrap_err();
    assert_eq!(err, FetchError::ForbiddenPort(8080));

    // 2. Embedded credentials
    let err = fetch_url(
        "http://user:password@example.com/test",
        "example.com",
        &config,
    )
    .await
    .unwrap_err();
    assert_eq!(err, FetchError::EmbeddedCredentials);
}

#[tokio::test]
async fn test_wiremock_robots_429_and_5xx_status_eval() {
    let mock_server = MockServer::start().await;

    Mock::given(method("GET"))
        .and(path("/robots-429.txt"))
        .respond_with(ResponseTemplate::new(429))
        .mount(&mock_server)
        .await;

    Mock::given(method("GET"))
        .and(path("/robots-503.txt"))
        .respond_with(ResponseTemplate::new(503))
        .mount(&mock_server)
        .await;

    let server_url = Url::parse(&mock_server.uri()).unwrap();
    let host = server_url.host_str().unwrap();
    let config = FetcherConfig::test_config();

    let resp_429 = fetch_url(
        &format!("{}/robots-429.txt", mock_server.uri()),
        host,
        &config,
    )
    .await
    .unwrap();
    let eval_429 = evaluate_robots_http_response(resp_429.status, None, "/", "AEOSuiteBot");
    assert_eq!(
        eval_429.unwrap_err(),
        crawler::robots::RobotsError::RateLimited
    );

    let resp_503 = fetch_url(
        &format!("{}/robots-503.txt", mock_server.uri()),
        host,
        &config,
    )
    .await
    .unwrap();
    let eval_503 = evaluate_robots_http_response(resp_503.status, None, "/", "AEOSuiteBot");
    assert_eq!(
        eval_503.unwrap_err(),
        crawler::robots::RobotsError::ServerError(503)
    );
}

#[tokio::test]
async fn test_wiremock_end_to_end_preflight() {
    let mock_server = MockServer::start().await;
    let robots_txt = "User-agent: *\nDisallow: /admin\nAllow: /\nCrawl-delay: 2.5";

    Mock::given(method("GET"))
        .and(path("/robots.txt"))
        .respond_with(ResponseTemplate::new(200).set_body_string(robots_txt))
        .mount(&mock_server)
        .await;

    let server_url = Url::parse(&mock_server.uri()).unwrap();
    let host = server_url.host_str().unwrap();

    let secret_key = "test-django-secret-key-12345";
    let claims = crawler::token::TokenClaims {
        v: 1,
        kid: "v1".to_string(),
        sub: "3fa85f64-5717-4562-b3fc-2c963f66afa6".to_string(),
        org: "7ca24e62-4318-4e1b-b27a-5b1e60058b88".to_string(),
        dom: host.to_string(),
        iat: 1731000000,
        exp: 1731003600,
    };
    let token = crawler::token::mint_token(&claims, secret_key);

    let test_now = 1731002000;
    let config = FetcherConfig::test_config();

    // 1. Preflight on allowed path "/"
    let report_allowed = crawler::preflight::run_preflight(crawler::preflight::PreflightOptions {
        token: &token,
        secret_key,
        target_domain: Some(host),
        check_path: "/",
        base_url: Some(&mock_server.uri()),
        now: Some(test_now),
        config: config.clone(),
    })
    .await;

    assert_eq!(report_allowed.result, "ok");
    assert!(report_allowed.robots_allowed);
    assert_eq!(report_allowed.status_code, Some(200));
    assert_eq!(report_allowed.crawl_delay_seconds, Some(2.5));
    assert_eq!(report_allowed.pacing_ms, 2500);
    assert!(report_allowed.error_message.is_none());

    // 2. Preflight on disallowed path "/admin"
    let report_disallowed =
        crawler::preflight::run_preflight(crawler::preflight::PreflightOptions {
            token: &token,
            secret_key,
            target_domain: Some(host),
            check_path: "/admin",
            base_url: Some(&mock_server.uri()),
            now: Some(test_now),
            config: config.clone(),
        })
        .await;

    assert_eq!(report_disallowed.result, "disallowed_robots");
    assert!(!report_disallowed.robots_allowed);

    // 3. Preflight with expired token
    let report_expired = crawler::preflight::run_preflight(crawler::preflight::PreflightOptions {
        token: &token,
        secret_key,
        target_domain: Some(host),
        check_path: "/",
        base_url: Some(&mock_server.uri()),
        now: Some(1731005000), // after exp
        config,
    })
    .await;

    assert_eq!(report_expired.result, "invalid_token");
    assert!(!report_expired.robots_allowed);

    // 4. Verify token hygiene in JSON report (token string must NEVER appear)
    let json_output = serde_json::to_string(&report_allowed).unwrap();
    assert!(!json_output.contains(&token));
}
