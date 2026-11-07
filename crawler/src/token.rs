use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use hmac::{Hmac, Mac};
use sha2::Sha256;
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

pub const PREFLIGHT_SALT: &[u8] = b"aeo-crawler-preflight-token-v1";

type HmacSha256 = Hmac<Sha256>;

#[derive(Error, Debug, PartialEq, Eq)]
pub enum TokenError {
    #[error("Malformed token structure")]
    MalformedToken,
    #[error("Base64 decode failure: {0}")]
    Base64Error(String),
    #[error("JSON decode failure: {0}")]
    JsonError(String),
    #[error("Invalid cryptographic signature")]
    InvalidSignature,
    #[error("Unsupported token version: {0}")]
    UnsupportedVersion(u32),
    #[error("Token has expired: exp={exp}, now={now}")]
    Expired { exp: i64, now: i64 },
    #[error("Domain mismatch: token={token_domain}, target={target_domain}")]
    DomainMismatch {
        token_domain: String,
        target_domain: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct TokenClaims {
    pub v: u32,
    pub kid: String,
    pub sub: String,
    pub org: String,
    pub dom: String,
    pub iat: i64,
    pub exp: i64,
}

pub fn derive_signing_key(secret_key: &str) -> [u8; 32] {
    let mut mac =
        HmacSha256::new_from_slice(secret_key.as_bytes()).expect("HMAC can take key of any size");
    mac.update(PREFLIGHT_SALT);
    mac.finalize().into_bytes().into()
}

pub fn normalize_host(host: &str) -> String {
    host.trim()
        .to_ascii_lowercase()
        .trim_end_matches('.')
        .to_string()
}

pub fn verify_token(
    token: &str,
    secret_key: &str,
    target_domain: Option<&str>,
    now: Option<i64>,
) -> Result<TokenClaims, TokenError> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 2 {
        return Err(TokenError::MalformedToken);
    }

    let payload_b64 = parts[0];
    let sig_b64 = parts[1];

    let payload_bytes = URL_SAFE_NO_PAD
        .decode(payload_b64)
        .map_err(|e| TokenError::Base64Error(e.to_string()))?;

    let sig_bytes = URL_SAFE_NO_PAD
        .decode(sig_b64)
        .map_err(|e| TokenError::Base64Error(e.to_string()))?;

    let derived_key = derive_signing_key(secret_key);
    let mut mac = HmacSha256::new_from_slice(&derived_key).expect("HMAC can take key of any size");
    mac.update(payload_b64.as_bytes());

    mac.verify_slice(&sig_bytes)
        .map_err(|_| TokenError::InvalidSignature)?;

    let claims: TokenClaims =
        serde_json::from_slice(&payload_bytes).map_err(|e| TokenError::JsonError(e.to_string()))?;

    if claims.v != 1 {
        return Err(TokenError::UnsupportedVersion(claims.v));
    }

    let current_time = now.unwrap_or_else(|| {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("Time went backwards")
            .as_secs() as i64
    });

    if claims.exp < current_time {
        return Err(TokenError::Expired {
            exp: claims.exp,
            now: current_time,
        });
    }

    if let Some(target) = target_domain {
        let normalized_target = normalize_host(target);
        if claims.dom != normalized_target {
            return Err(TokenError::DomainMismatch {
                token_domain: claims.dom,
                target_domain: normalized_target,
            });
        }
    }

    Ok(claims)
}

/// Mint a signed preflight token (useful for tests and integrations)
pub fn mint_token(claims: &TokenClaims, secret_key: &str) -> String {
    let derived_key = derive_signing_key(secret_key);
    let payload_json = serde_json::to_vec(claims).expect("Payload serialization failed");
    let payload_b64 = URL_SAFE_NO_PAD.encode(payload_json);

    let mut mac = HmacSha256::new_from_slice(&derived_key).expect("HMAC valid key");
    mac.update(payload_b64.as_bytes());
    let sig_b64 = URL_SAFE_NO_PAD.encode(mac.finalize().into_bytes());

    format!("{}.{}", payload_b64, sig_b64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shared_fixtures_verification() {
        let fixture_str = include_str!("../../shared_fixtures/crawler_token_vectors.json");
        let v: serde_json::Value = serde_json::from_str(fixture_str).unwrap();

        let secret_key = v["secret_key"].as_str().unwrap();
        let derived_hex = v["derived_key_hex"].as_str().unwrap();
        let test_now = v["test_clock_now"].as_i64().unwrap();

        let derived_hex_actual: String = derive_signing_key(secret_key)
            .iter()
            .map(|b| format!("{:02x}", b))
            .collect();
        assert_eq!(derived_hex_actual, derived_hex);

        // 1. Valid token
        let valid_token = v["valid"]["token"].as_str().unwrap();
        let claims = verify_token(valid_token, secret_key, Some("example.com"), Some(test_now))
            .expect("Valid token should pass");
        assert_eq!(claims.dom, "example.com");
        assert_eq!(claims.v, 1);
        assert_eq!(claims.kid, "v1");

        // 2. Expired token
        let expired_token = v["expired"]["token"].as_str().unwrap();
        let err = verify_token(
            expired_token,
            secret_key,
            Some("example.com"),
            Some(test_now),
        )
        .unwrap_err();
        assert!(matches!(err, TokenError::Expired { .. }));

        // 3. Tampered signature
        let tampered_sig = v["tampered_signature"]["token"].as_str().unwrap();
        let err = verify_token(
            tampered_sig,
            secret_key,
            Some("example.com"),
            Some(test_now),
        )
        .unwrap_err();
        assert_eq!(err, TokenError::InvalidSignature);

        // 4. Tampered payload
        let tampered_payload = v["tampered_payload"]["token"].as_str().unwrap();
        let err = verify_token(tampered_payload, secret_key, None, Some(test_now)).unwrap_err();
        assert_eq!(err, TokenError::InvalidSignature);

        // 5. Domain mismatch
        let err =
            verify_token(valid_token, secret_key, Some("other.com"), Some(test_now)).unwrap_err();
        assert!(matches!(err, TokenError::DomainMismatch { .. }));
    }
}
