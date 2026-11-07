use thiserror::Error;

#[derive(Error, Debug, PartialEq, Eq)]
pub enum RobotsError {
    #[error("Server returned 429 Too Many Requests (backoff required)")]
    RateLimited,
    #[error("Server returned 5xx server error ({0}) - fail closed per RFC 9309")]
    ServerError(u16),
    #[error("Invalid HTTP status: {0}")]
    HttpStatusError(u16),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Rule {
    pub is_allow: bool,
    pub pattern: String,
    pub length: usize,
}

#[derive(Debug, Clone, Default)]
pub struct Group {
    pub user_agents: Vec<String>,
    pub rules: Vec<Rule>,
    pub crawl_delay: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct RobotsTxt {
    pub groups: Vec<Group>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RobotsEvaluation {
    pub allowed: bool,
    pub matching_pattern: Option<String>,
    pub crawl_delay_seconds: Option<f64>,
}

impl RobotsTxt {
    /// Parse robots.txt according to RFC 9309
    pub fn parse(content: &str) -> Self {
        // Strip BOM if present
        let clean_content = content.strip_prefix('\u{FEFF}').unwrap_or(content);

        let mut groups = Vec::new();
        let mut current_uas: Vec<String> = Vec::new();
        let mut current_rules: Vec<Rule> = Vec::new();
        let mut current_delay: Option<f64> = None;
        let mut in_rules = false;

        for line in clean_content.lines() {
            // Strip comments
            let comment_idx = line.find('#').unwrap_or(line.len());
            let line = line[..comment_idx].trim();
            if line.is_empty() {
                continue;
            }

            let Some((key, val)) = line.split_once(':') else {
                continue;
            };

            let key = key.trim().to_ascii_lowercase();
            let val = val.trim();

            if key == "user-agent" {
                if in_rules {
                    // Flush completed group
                    if !current_uas.is_empty() {
                        groups.push(Group {
                            user_agents: std::mem::take(&mut current_uas),
                            rules: std::mem::take(&mut current_rules),
                            crawl_delay: current_delay.take(),
                        });
                    }
                    in_rules = false;
                }
                current_uas.push(val.to_ascii_lowercase());
            } else if key == "allow" {
                if !current_uas.is_empty() {
                    in_rules = true;
                    if !val.is_empty() {
                        current_rules.push(Rule {
                            is_allow: true,
                            pattern: val.to_string(),
                            length: val.len(),
                        });
                    }
                }
            } else if key == "disallow" {
                if !current_uas.is_empty() {
                    in_rules = true;
                    if !val.is_empty() {
                        current_rules.push(Rule {
                            is_allow: false,
                            pattern: val.to_string(),
                            length: val.len(),
                        });
                    }
                }
            } else if key == "crawl-delay" && !current_uas.is_empty() {
                in_rules = true;
                if let Ok(d) = val.parse::<f64>() {
                    if d >= 0.0 {
                        current_delay = Some(d);
                    }
                }
            }
        }

        // Flush last group
        if !current_uas.is_empty() {
            groups.push(Group {
                user_agents: current_uas,
                rules: current_rules,
                crawl_delay: current_delay,
            });
        }

        RobotsTxt { groups }
    }

    /// Evaluate access for a given path and bot product token (e.g. "AEOSuiteBot")
    pub fn evaluate(&self, path: &str, bot_product: &str) -> RobotsEvaluation {
        let bot_token = bot_product.to_ascii_lowercase();

        // 1. Check for specific bot product match
        let mut matched_rules = Vec::new();
        let mut matched_delay = None;
        let mut found_specific = false;

        for group in &self.groups {
            if group.user_agents.iter().any(|ua| ua == &bot_token) {
                found_specific = true;
                matched_rules.extend(group.rules.clone());
                if matched_delay.is_none() {
                    matched_delay = group.crawl_delay;
                }
            }
        }

        // 2. If no specific match, fall back to wildcard '*'
        if !found_specific {
            for group in &self.groups {
                if group.user_agents.iter().any(|ua| ua == "*") {
                    matched_rules.extend(group.rules.clone());
                    if matched_delay.is_none() {
                        matched_delay = group.crawl_delay;
                    }
                }
            }
        }

        // 3. If no matching groups or rules, default to allow
        if matched_rules.is_empty() {
            return RobotsEvaluation {
                allowed: true,
                matching_pattern: None,
                crawl_delay_seconds: matched_delay,
            };
        }

        // 4. Find all matching rules for path
        let mut matching: Vec<&Rule> = matched_rules
            .iter()
            .filter(|r| match_path(&r.pattern, path))
            .collect();

        if matching.is_empty() {
            return RobotsEvaluation {
                allowed: true,
                matching_pattern: None,
                crawl_delay_seconds: matched_delay,
            };
        }

        // 5. Precedence: longest match wins
        let max_len = matching.iter().map(|r| r.length).max().unwrap();
        matching.retain(|r| r.length == max_len);

        // 6. Equal length: Allow takes precedence over Disallow
        if let Some(allow_rule) = matching.iter().find(|r| r.is_allow) {
            RobotsEvaluation {
                allowed: true,
                matching_pattern: Some(allow_rule.pattern.clone()),
                crawl_delay_seconds: matched_delay,
            }
        } else {
            let disallow_rule = matching[0];
            RobotsEvaluation {
                allowed: false,
                matching_pattern: Some(disallow_rule.pattern.clone()),
                crawl_delay_seconds: matched_delay,
            }
        }
    }
}

/// Match an RFC 9309 path pattern against a URL path
pub fn match_path(pattern: &str, path: &str) -> bool {
    let (pat, exact_end) = if let Some(stripped) = pattern.strip_suffix('$') {
        (stripped, true)
    } else {
        (pattern, false)
    };

    match_wildcard(pat.as_bytes(), path.as_bytes(), exact_end)
}

fn match_wildcard(p: &[u8], s: &[u8], exact_end: bool) -> bool {
    if p.is_empty() {
        return if exact_end { s.is_empty() } else { true };
    }

    if p[0] == b'*' {
        // Advance past all consecutive '*'
        let mut p_idx = 0;
        while p_idx < p.len() && p[p_idx] == b'*' {
            p_idx += 1;
        }
        if p_idx == p.len() {
            // Pattern ends with '*', which matches everything remaining
            return true;
        }
        for s_idx in 0..=s.len() {
            if match_wildcard(&p[p_idx..], &s[s_idx..], exact_end) {
                return true;
            }
        }
        false
    } else if !s.is_empty() && p[0] == s[0] {
        match_wildcard(&p[1..], &s[1..], exact_end)
    } else {
        false
    }
}

/// Evaluate robots.txt HTTP response status per RFC 9309 §2.3.1.2
pub fn evaluate_robots_http_response(
    status_code: u16,
    body: Option<&str>,
    target_path: &str,
    bot_product: &str,
) -> Result<RobotsEvaluation, RobotsError> {
    match status_code {
        200..=299 => {
            let content = body.unwrap_or("");
            let parsed = RobotsTxt::parse(content);
            Ok(parsed.evaluate(target_path, bot_product))
        }
        404 | 410 => {
            // 404 Not Found or 410 Gone: allow all
            Ok(RobotsEvaluation {
                allowed: true,
                matching_pattern: None,
                crawl_delay_seconds: None,
            })
        }
        429 => Err(RobotsError::RateLimited),
        500..=599 => Err(RobotsError::ServerError(status_code)),
        _ => {
            // Any other 4xx (client error) treated as allow all per RFC 9309 §2.3.1.2
            if (400..500).contains(&status_code) {
                Ok(RobotsEvaluation {
                    allowed: true,
                    matching_pattern: None,
                    crawl_delay_seconds: None,
                })
            } else {
                Err(RobotsError::HttpStatusError(status_code))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_specific_user_agent_precedence() {
        let robots = r#"
User-agent: *
Disallow: /

User-agent: AEOSuiteBot
Allow: /
Disallow: /admin
Crawl-delay: 2
"#;
        let parsed = RobotsTxt::parse(robots);
        let eval_home = parsed.evaluate("/", "AEOSuiteBot");
        assert!(eval_home.allowed);
        assert_eq!(eval_home.crawl_delay_seconds, Some(2.0));

        let eval_admin = parsed.evaluate("/admin/users", "AEOSuiteBot");
        assert!(!eval_admin.allowed);
        assert_eq!(eval_admin.matching_pattern, Some("/admin".to_string()));

        // Other bot falls back to *
        let eval_other = parsed.evaluate("/", "OtherBot");
        assert!(!eval_other.allowed);
    }

    #[test]
    fn test_longest_match_precedence() {
        let robots = r#"
User-agent: *
Disallow: /fish
Allow: /fish/salmon.html
"#;
        let parsed = RobotsTxt::parse(robots);

        // /fish/salmon.html matches both, but Allow is 19 chars vs Disallow 5 chars -> Allow wins
        let eval_salmon = parsed.evaluate("/fish/salmon.html", "AEOSuiteBot");
        assert!(eval_salmon.allowed);
        assert_eq!(
            eval_salmon.matching_pattern,
            Some("/fish/salmon.html".to_string())
        );

        // /fish/cod.html matches only Disallow: /fish
        let eval_cod = parsed.evaluate("/fish/cod.html", "AEOSuiteBot");
        assert!(!eval_cod.allowed);
    }

    #[test]
    fn test_equal_length_allow_precedence() {
        let robots = r#"
User-agent: *
Disallow: /path
Allow: /path
"#;
        let parsed = RobotsTxt::parse(robots);
        let eval = parsed.evaluate("/path/file", "AEOSuiteBot");
        assert!(eval.allowed);
        assert_eq!(eval.matching_pattern, Some("/path".to_string()));
    }

    #[test]
    fn test_wildcard_and_eol_patterns() {
        let robots = r#"
User-agent: *
Disallow: /*.php$
Disallow: /private/*
Allow: /private/public
"#;
        let parsed = RobotsTxt::parse(robots);

        // *.php$ matches /test.php but not /test.php?arg=1
        assert!(!parsed.evaluate("/test.php", "AEOSuiteBot").allowed);
        assert!(parsed.evaluate("/test.php?arg=1", "AEOSuiteBot").allowed);

        // /private/* vs /private/public
        assert!(
            !parsed
                .evaluate("/private/secret.txt", "AEOSuiteBot")
                .allowed
        );
        assert!(parsed.evaluate("/private/public", "AEOSuiteBot").allowed);
    }

    #[test]
    fn test_empty_disallow_allows_all() {
        let robots = r#"
User-agent: *
Disallow:
"#;
        let parsed = RobotsTxt::parse(robots);
        assert!(parsed.evaluate("/any/path", "AEOSuiteBot").allowed);
    }

    #[test]
    fn test_http_status_evaluation() {
        // 200 parses body
        let res200 = evaluate_robots_http_response(
            200,
            Some("User-agent: *\nDisallow: /secret"),
            "/secret",
            "AEOSuiteBot",
        )
        .unwrap();
        assert!(!res200.allowed);

        // 404 / 410 allows all
        let res404 = evaluate_robots_http_response(404, None, "/secret", "AEOSuiteBot").unwrap();
        assert!(res404.allowed);
        assert!(res404.matching_pattern.is_none());

        let res410 = evaluate_robots_http_response(410, None, "/secret", "AEOSuiteBot").unwrap();
        assert!(res410.allowed);

        // 429 returns RateLimited
        let res429 = evaluate_robots_http_response(429, None, "/", "AEOSuiteBot");
        assert_eq!(res429.unwrap_err(), RobotsError::RateLimited);

        // 500 / 503 returns ServerError (fail closed)
        let res500 = evaluate_robots_http_response(500, None, "/", "AEOSuiteBot");
        assert_eq!(res500.unwrap_err(), RobotsError::ServerError(500));

        let res503 = evaluate_robots_http_response(503, None, "/", "AEOSuiteBot");
        assert_eq!(res503.unwrap_err(), RobotsError::ServerError(503));
    }
}
