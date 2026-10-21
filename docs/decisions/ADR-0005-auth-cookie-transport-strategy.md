# ADR-0005: Auth cookie transport — same-origin Next.js proxy in dev; no CORS-credentials anywhere in development

## Status

Accepted (owner-directed decision, 2026-10-19 — "decide now … so 0.3 doesn't stall"; recorded during the SPEC-0.2 amendment round)

## Date

2026-10-19

## Context

SPEC-0.2 wires allauth in headless mode with **cookie sessions** (decision 1).
Chunk 0.3 adds the Next.js app: dev frontend on `localhost:3000`, Django on
`127.0.0.1:8000`. Cookie auth across those two origins is the classic dev
trap:

1. **SameSite=None requires Secure.** Modern Chromium rejects
   `SameSite=None` cookies without the `Secure` attribute, and `Secure`
   requires HTTPS — so cross-origin dev cookies force certificates (mkcert)
   or browser flag hacks on the owner's Windows machine.
2. **Host mismatch silently drops cookies.** A cookie set for `localhost`
   is not sent to `127.0.0.1` (and vice versa) — a failure mode that costs
   hours and presents as "auth randomly not working".
3. **CORS + CSRF bookkeeping doubles.** Every auth route needs
   credentials-capable CORS, and Django's CSRF needs trusted origins for the
   second origin.

The amendment round (owner, 2026-10-19) directed: decide now, record the
decision in an ADR, so chunk 0.3 does not stall on auth wiring.

## Decision

**1. Development uses a same-origin proxy: the Next.js dev server forwards
`/api/*` to Django.** The Next.js app calls **relative** `/api/...` paths;
`next.config.ts` rewrites `/api/:path*` to `http://127.0.0.1:8000/api/:path*`.
The browser only ever talks to `localhost:3000`, so session cookies are
first-party: no CORS-with-credentials, no `SameSite=None`, no HTTPS
requirement in dev.

**2. CSRF stays on, with one trusted origin.** Django keeps enforcing CSRF
on session-authenticated unsafe methods. Because the browser's `Origin` is
`http://localhost:3000` while Django serves on `127.0.0.1:8000`,
`CSRF_TRUSTED_ORIGINS` in `local.py` includes `http://localhost:3000`
(the placeholder lands in 0.2; harmless and self-documenting). Production
adds its real frontend origin at deploy time.

**3. allauth headless is configured against the externally visible origin**
(the proxy origin the browser sees), not the upstream Django port — this
keeps signup/login/session URLs and cookie settings consistent.

**4. Production shape stays open but biased to parity.** The expected
production topology is one registrable domain serving the frontend and
proxying `/api` to Django — the dev proxy mirrors it. Any deviation
(separate auth domain, subdomain cookies) supersedes this ADR with a new
one.

**5. Forbidden patterns in development:** `CORS_ALLOW_CREDENTIALS=True`
setups, `SameSite=None` cookies over plain HTTP, `Access-Control-Allow-*`
lists for auth endpoints, JWT-in-localStorage as an auth mechanism (also
rejected below).

**6. Chunk 0.2 impact: none functionally.** 0.2 serves cookie sessions on
`127.0.0.1:8000` and is tested directly (pytest + owner smoke via
PowerShell). The proxy itself is 0.3 work; only the `CSRF_TRUSTED_ORIGINS`
placeholder and this record land now.

## Alternatives Considered

### Cross-origin cookies in dev (browser talks to both :3000 and :8000)

- Pros: no proxy layer; "realistic" two-service topology; simpler Next.js
  config.
- Cons: `SameSite=None; Secure` forces dev HTTPS; localhost/127.0.0.1
  cookie-domain traps; CORS + CSRF bookkeeping on every auth route; allauth
  headless origin config duplicated per origin.
- **Rejected** — fragile on Windows dev and worse dev/prod parity than the
  proxy.

### Token auth (JWT in localStorage) instead of cookies

- Pros: sidesteps CSRF entirely; trivial cross-origin.
- Cons: contradicts the approved architecture (sessions/cookies, SPEC-0.2
  decision 1); tokens in localStorage are XSS-exposed; bypasses the allauth
  headless session model that 0.3 builds on.
- **Rejected** — out of line with the recorded architecture decision.

## Consequences

- Chunk 0.3 ships `next.config.ts` rewrites + a relative API base URL;
  Django needs **no CORS middleware** for development.
- `backend/README.md` (0.2 runbook) documents the CSRF origins and the
  cookie model per environment.
- Leak-test and header-spoof semantics are unaffected — they run
  server-side against Django directly.
- If production design later requires cross-origin auth, a new ADR
  supersedes this one; the proxy decision costs nothing to unwind on the
  Django side.
