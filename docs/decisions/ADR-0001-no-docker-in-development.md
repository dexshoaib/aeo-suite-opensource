# ADR-0001: No Docker in development; Docker reserved for production

## Status

Accepted (product owner, 2026-10-17)

## Date

2026-10-17

## Context

The architecture document specifies "Docker Compose in development and CI
on GitHub Actions". Development happens on the owner's Windows machine,
where running an entire container stack adds startup friction, file-watch
latency, and a debugging layer that hides the simple local-process
reality during the phase where iteration speed matters most. The owner
directed that early chunks be verified directly as local processes, and
that Docker be introduced only when the product moves toward production.

## Decision

Development runs **without Docker**. Each service runs as a plain local
process on the owner's device (Django runserver, Next.js dev, cargo-run
crawler, local PostgreSQL). Docker (Compose on a VPS, per the
architecture doc) is introduced at the production stage; CI runs on
GitHub Actions without depending on containers for chunk 0.x work.

## Alternatives Considered

### Docker Compose from day one (as originally documented)
- Pros: dev/prod parity from the first commit; no environment drift
- Cons: slower inner loop on Windows, harder debugging for a solo
  founder, container skills taxed before any product code exists
- Rejected for development; adopted later at the production stage

### WSL2-only development
- Pros: Linux parity for local processes
- Cons: adds a platform layer the owner did not ask for; files split
  across filesystems
- Rejected: owner's stated setup is Windows-native

## Consequences

- `scripts/setup-dev.ps1` becomes the dev-environment contract; it is
  the thing that keeps "works on my machine" true.
- Environment drift between dev and production is a real risk; it is
  mitigated when the production Docker stage lands by encoding the
  production environment as containers and re-verifying behavior.
- The architecture doc's "Deployment" section applies from production
  onward; the amendment is registered in `docs/ARCHITECTURE.md`.
- Services that would have been containers in dev (Postgres) are
  installed natively; the setup script checks their versions.
