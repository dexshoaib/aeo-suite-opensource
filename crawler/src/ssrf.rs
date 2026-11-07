use ipnet::{IpNet, Ipv4Net, Ipv6Net};
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::str::FromStr;
use thiserror::Error;

#[derive(Error, Debug, PartialEq, Eq)]
pub enum SsrfError {
    #[error("Embedded credentials in host or URL are forbidden")]
    EmbeddedCredentials,
    #[error("Invalid IP literal format: {0}")]
    InvalidIpLiteral(String),
    #[error("Blocked IP address ({ip}) belongs to restricted range: {range}")]
    BlockedIp { ip: IpAddr, range: String },
    #[error("DNS resolution failed for host {host}: {reason}")]
    DnsResolutionFailed { host: String, reason: String },
    #[error("No IP addresses returned for host: {0}")]
    NoAddressesResolved(String),
}

pub struct BlockedRange {
    pub net: IpNet,
    pub description: &'static str,
}

pub static BLOCKED_IPV4_RANGES: &[(&str, &str)] = &[
    ("0.0.0.0/8", "Current network"),
    ("10.0.0.0/8", "Private-Use"),
    ("100.64.0.0/10", "Shared Address Space / CGNAT"),
    ("127.0.0.0/8", "Loopback"),
    ("169.254.0.0/16", "Link-Local / Cloud Metadata"),
    ("172.16.0.0/12", "Private-Use"),
    ("192.0.0.0/24", "IETF Protocol Assignments"),
    ("192.0.2.0/24", "TEST-NET-1"),
    ("192.88.99.0/24", "6to4 Relay Anycast"),
    ("192.168.0.0/16", "Private-Use"),
    ("198.18.0.0/15", "Benchmarking"),
    ("198.51.100.0/24", "TEST-NET-2"),
    ("203.0.113.0/24", "TEST-NET-3"),
    ("224.0.0.0/4", "Multicast"),
    ("240.0.0.0/4", "Reserved for Future Use"),
    ("255.255.255.255/32", "Limited Broadcast"),
];

pub static BLOCKED_IPV6_RANGES: &[(&str, &str)] = &[
    ("::/128", "Unspecified"),
    ("::1/128", "Loopback"),
    ("::ffff:0:0/96", "IPv4-mapped"),
    ("64:ff9b::/96", "IPv4/IPv6 translation"),
    ("100::/64", "Discard-Only"),
    ("2001::/23", "IETF Protocol Assignments"),
    ("2001:db8::/32", "Documentation"),
    ("2002::/16", "6to4"),
    ("fc00::/7", "Unique Local"),
    ("fe80::/10", "Link-Local"),
    ("ff00::/8", "Multicast"),
];

pub fn get_blocked_networks() -> Vec<BlockedRange> {
    let mut nets = Vec::new();
    for (cidr, desc) in BLOCKED_IPV4_RANGES {
        let net = IpNet::V4(Ipv4Net::from_str(cidr).unwrap());
        nets.push(BlockedRange {
            net,
            description: desc,
        });
    }
    for (cidr, desc) in BLOCKED_IPV6_RANGES {
        let net = IpNet::V6(Ipv6Net::from_str(cidr).unwrap());
        nets.push(BlockedRange {
            net,
            description: desc,
        });
    }
    nets
}

/// Canonicalize an IP-literal string, handling standard notation,
/// integer representations (decimal, octal, hex), and IPv4-mapped IPv6.
pub fn parse_and_canonicalize_ip(input: &str) -> Option<IpAddr> {
    let trimmed = input.trim().trim_start_matches('[').trim_end_matches(']');

    // 1. Try standard IP parsing first
    if let Ok(ip) = IpAddr::from_str(trimmed) {
        return Some(match ip {
            IpAddr::V6(v6) => {
                if let Some(v4) = v6.to_ipv4_mapped() {
                    IpAddr::V4(v4)
                } else {
                    IpAddr::V6(v6)
                }
            }
            v4 => v4,
        });
    }

    // 2. Try single integer (hex e.g. 0x7f000001 or decimal e.g. 2130706433)
    if let Some(hex_str) = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
    {
        if let Ok(num) = u32::from_str_radix(hex_str, 16) {
            return Some(IpAddr::V4(Ipv4Addr::from(num)));
        }
    } else if let Ok(num) = trimmed.parse::<u32>() {
        return Some(IpAddr::V4(Ipv4Addr::from(num)));
    }

    // 3. Try octal / hex components separated by dots (e.g. 0177.0.0.1 or 0x7f.0.0.1)
    let parts: Vec<&str> = trimmed.split('.').collect();
    if parts.len() == 4 {
        let mut octets = [0u8; 4];
        for (i, part) in parts.iter().enumerate() {
            let val = if let Some(hex_part) =
                part.strip_prefix("0x").or_else(|| part.strip_prefix("0X"))
            {
                u32::from_str_radix(hex_part, 16).ok()?
            } else if part.starts_with('0') && part.len() > 1 {
                u32::from_str_radix(part, 8).ok()?
            } else {
                part.parse::<u32>().ok()?
            };
            if val > 255 {
                return None;
            }
            octets[i] = val as u8;
        }
        return Some(IpAddr::V4(Ipv4Addr::new(
            octets[0], octets[1], octets[2], octets[3],
        )));
    }

    None
}

/// Validate whether an IP address is globally routable and outside all blocked CIDR blocks.
pub fn validate_ip_safety_with_options(ip: &IpAddr, allow_loopback: bool) -> Result<(), SsrfError> {
    let unmapped = match ip {
        IpAddr::V6(v6) => {
            if let Some(v4) = v6.to_ipv4_mapped() {
                IpAddr::V4(v4)
            } else {
                IpAddr::V6(*v6)
            }
        }
        IpAddr::V4(v4) => IpAddr::V4(*v4),
    };

    if allow_loopback && unmapped.is_loopback() {
        return Ok(());
    }

    let blocked_nets = get_blocked_networks();
    for blocked in blocked_nets {
        if blocked.net.contains(&unmapped) {
            return Err(SsrfError::BlockedIp {
                ip: unmapped,
                range: format!("{} ({})", blocked.net, blocked.description),
            });
        }
    }

    Ok(())
}

pub fn validate_ip_safety(ip: &IpAddr) -> Result<(), SsrfError> {
    validate_ip_safety_with_options(ip, false)
}

/// Validate that every address in a resolved address list is safe.
pub fn validate_resolved_addresses(
    addrs: &[SocketAddr],
    allow_loopback: bool,
) -> Result<(), SsrfError> {
    if addrs.is_empty() {
        return Err(SsrfError::NoAddressesResolved(
            "empty address list".to_string(),
        ));
    }
    for addr in addrs {
        validate_ip_safety_with_options(&addr.ip(), allow_loopback)?;
    }
    Ok(())
}

/// Resolve host and validate that ALL resolved addresses are safe.
/// Returns the first safe IP to pin the connection to.
pub async fn resolve_and_pin_ip_with_options(
    host: &str,
    port: u16,
    allow_loopback: bool,
) -> Result<IpAddr, SsrfError> {
    // If host is an IP literal, validate directly
    if let Some(literal_ip) = parse_and_canonicalize_ip(host) {
        validate_ip_safety_with_options(&literal_ip, allow_loopback)?;
        return Ok(literal_ip);
    }

    // Resolve via tokio async DNS lookup
    let addr_str = format!("{}:{}", host, port);
    let resolved_iter =
        tokio::net::lookup_host(&addr_str)
            .await
            .map_err(|e| SsrfError::DnsResolutionFailed {
                host: host.to_string(),
                reason: e.to_string(),
            })?;

    let mut addrs: Vec<SocketAddr> = resolved_iter.collect();
    if addrs.is_empty() {
        return Err(SsrfError::NoAddressesResolved(host.to_string()));
    }

    // Must validate EVERY returned address. If any address is blocked, reject all.
    validate_resolved_addresses(&addrs, allow_loopback)?;

    // Return the first validated safe IP
    Ok(addrs.remove(0).ip())
}

pub async fn resolve_and_pin_ip(host: &str, port: u16) -> Result<IpAddr, SsrfError> {
    resolve_and_pin_ip_with_options(host, port, false).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ip_canonicalization() {
        // Decimal literal 127.0.0.1
        let ip = parse_and_canonicalize_ip("2130706433").unwrap();
        assert_eq!(ip, IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)));

        // Hex literal 0x7f000001
        let ip = parse_and_canonicalize_ip("0x7f000001").unwrap();
        assert_eq!(ip, IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)));

        // Octal notation 0177.0.0.1
        let ip = parse_and_canonicalize_ip("0177.0.0.1").unwrap();
        assert_eq!(ip, IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)));

        // IPv4-mapped IPv6 ::ffff:127.0.0.1
        let ip = parse_and_canonicalize_ip("::ffff:127.0.0.1").unwrap();
        assert_eq!(ip, IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)));
    }

    #[test]
    fn test_ssrf_blocked_ranges() {
        assert!(validate_ip_safety(&IpAddr::from_str("127.0.0.1").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("10.0.0.1").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("172.16.5.5").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("192.168.1.1").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("169.254.169.254").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("100.64.0.1").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("::1").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("fe80::1").unwrap()).is_err());
        assert!(validate_ip_safety(&IpAddr::from_str("fc00::1").unwrap()).is_err());

        // Valid public IP
        assert!(validate_ip_safety(&IpAddr::from_str("93.184.216.34").unwrap()).is_ok());
        assert!(validate_ip_safety(&IpAddr::from_str("1.1.1.1").unwrap()).is_ok());
    }

    #[test]
    fn test_exhaustive_cidr_boundaries() {
        // Amendment A9: verify first, last, -1, +1 for each block
        for (cidr, desc) in BLOCKED_IPV4_RANGES {
            let net = Ipv4Net::from_str(cidr).unwrap();
            let first = net.network();
            let last = net.broadcast();

            // First and last address must both be blocked
            assert!(
                validate_ip_safety(&IpAddr::V4(first)).is_err(),
                "Failed to block first address of {} ({})",
                cidr,
                desc
            );
            assert!(
                validate_ip_safety(&IpAddr::V4(last)).is_err(),
                "Failed to block last address of {} ({})",
                cidr,
                desc
            );

            // Check boundary -1 (if valid u32)
            let first_u32 = u32::from(first);
            if first_u32 > 0 {
                let before_ip = Ipv4Addr::from(first_u32 - 1);
                // If before_ip is not in another blocked block, it should be ok
                // (e.g. 10.0.0.0 - 1 = 9.255.255.255 which is public routable)
                if !net.contains(&before_ip) && first_u32 == u32::from(Ipv4Addr::new(10, 0, 0, 0)) {
                    assert!(validate_ip_safety(&IpAddr::V4(before_ip)).is_ok());
                }
            }

            // Check boundary +1
            let last_u32 = u32::from(last);
            if last_u32 < u32::MAX {
                let after_ip = Ipv4Addr::from(last_u32 + 1);
                // 10.255.255.255 + 1 = 11.0.0.0 which is public routable
                if !net.contains(&after_ip)
                    && last_u32 == u32::from(Ipv4Addr::new(10, 255, 255, 255))
                {
                    assert!(validate_ip_safety(&IpAddr::V4(after_ip)).is_ok());
                }
            }
        }
    }

    #[test]
    fn test_multi_ip_dns_rejection() {
        // Multi-IP resolution where all are public passes
        let safe_addrs = vec![
            SocketAddr::new(IpAddr::from_str("93.184.216.34").unwrap(), 443),
            SocketAddr::new(IpAddr::from_str("1.1.1.1").unwrap(), 443),
        ];
        assert!(validate_resolved_addresses(&safe_addrs, false).is_ok());

        // Multi-IP resolution where at least one address is private/loopback fails entire resolution
        let poisoned_addrs = vec![
            SocketAddr::new(IpAddr::from_str("93.184.216.34").unwrap(), 443),
            SocketAddr::new(IpAddr::from_str("192.168.1.1").unwrap(), 443),
        ];
        assert!(validate_resolved_addresses(&poisoned_addrs, false).is_err());

        let poisoned_loopback = vec![
            SocketAddr::new(IpAddr::from_str("1.1.1.1").unwrap(), 443),
            SocketAddr::new(IpAddr::from_str("127.0.0.1").unwrap(), 443),
        ];
        assert!(validate_resolved_addresses(&poisoned_loopback, false).is_err());
    }
}
