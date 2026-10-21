# crawler/ — Rust crawl + audit engine

Lands in **chunk 1.1** per `docs/specs/SPEC-0.1-repo-local-dev-ci.md`.

Standalone Rust service: JSON in (crawl job: site, URL list, limits),
JSON out (fetched pages + rule-based audit results). Contract stays
plain JSON so the implementation is swappable. Suggested crates: tokio,
reqwest, scraper or lol_html, url, robots.txt parser.

Rules: identify with a clear user agent, respect robots.txt and rate
limits, crawl only verified domains. Snapshot tests on saved HTML
fixtures with known expected scores. See `docs/ARCHITECTURE.md`
("Crawler and page audit engine").
