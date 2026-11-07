use std::env;
use std::fs;
use std::process::ExitCode;

use crawler::fetcher::FetcherConfig;
use crawler::preflight::{run_preflight, PreflightOptions, RESULT_OK};

#[tokio::main]
async fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();

    let mut token = None;
    let mut token_file = None;
    let mut secret = env::var("DJANGO_SECRET_KEY").ok();
    let mut domain = None;
    let mut target_url = None;
    let mut check_path = "/".to_string();
    let mut allow_loopback = false;
    let mut allow_custom_ports = false;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--token" => {
                if i + 1 < args.len() {
                    token = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--token-file" => {
                if i + 1 < args.len() {
                    token_file = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--secret" => {
                if i + 1 < args.len() {
                    secret = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--domain" => {
                if i + 1 < args.len() {
                    domain = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--target-url" => {
                if i + 1 < args.len() {
                    target_url = Some(args[i + 1].clone());
                    i += 1;
                }
            }
            "--path" => {
                if i + 1 < args.len() {
                    check_path = args[i + 1].clone();
                    i += 1;
                }
            }
            "--allow-loopback" => {
                allow_loopback = true;
            }
            "--allow-custom-ports" => {
                allow_custom_ports = true;
            }
            "--help" | "-h" => {
                eprintln!(
                    "Usage: crawler_preflight (--token <TOKEN> | --token-file <PATH>) [options]"
                );
                eprintln!();
                eprintln!("Options:");
                eprintln!("  --token <TOKEN>          Preflight token string");
                eprintln!("  --token-file <PATH>      File containing preflight token");
                eprintln!(
                    "  --secret <SECRET>        Django SECRET_KEY (defaults to DJANGO_SECRET_KEY env)"
                );
                eprintln!("  --domain <DOMAIN>        Expected target domain");
                eprintln!("  --target-url <URL>       Override robots base URL");
                eprintln!(
                    "  --path <PATH>            Path to check against robots rules (default: /)"
                );
                eprintln!(
                    "  --allow-loopback         Allow loopback IP connections (testing only)"
                );
                eprintln!("  --allow-custom-ports     Allow non-standard ports (testing only)");
                return ExitCode::from(0);
            }
            _ => {}
        }
        i += 1;
    }

    // Resolve token: from --token or --token-file
    let token_str = if let Some(t) = token {
        t
    } else if let Some(tf) = token_file {
        match fs::read_to_string(&tf) {
            Ok(content) => content.trim().to_string(),
            Err(e) => {
                eprintln!("Error reading token file {}: {}", tf, e);
                return ExitCode::from(1);
            }
        }
    } else {
        eprintln!("Error: Either --token or --token-file must be provided");
        return ExitCode::from(1);
    };

    let secret_str = secret.unwrap_or_default();

    let config = FetcherConfig {
        allow_loopback,
        allow_custom_ports,
        ..Default::default()
    };

    let report = run_preflight(PreflightOptions {
        token: &token_str,
        secret_key: &secret_str,
        target_domain: domain.as_deref(),
        check_path: &check_path,
        base_url: target_url.as_deref(),
        now: None,
        config,
    })
    .await;

    // Output JSON report - NEVER echo token!
    match serde_json::to_string_pretty(&report) {
        Ok(json_str) => println!("{}", json_str),
        Err(e) => eprintln!("Serialization error: {}", e),
    }

    if report.result == RESULT_OK {
        ExitCode::from(0)
    } else {
        ExitCode::from(1)
    }
}
