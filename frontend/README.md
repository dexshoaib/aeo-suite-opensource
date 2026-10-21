# frontend/ — Next.js dashboard + public pages

Lands in **chunk 0.3** per `docs/specs/SPEC-0.1-repo-local-dev-ci.md`.

Next.js (React + TypeScript), typed API client generated from the DRF
OpenAPI schema (openapi-typescript) so a serializer change breaks the
build, not production. Server-rendered public pages for the free audit
tool. Tooling: pnpm via corepack.

See `docs/ARCHITECTURE.md` ("Frontend: should it be Rust?") before
writing code — the answer is: dashboard in TypeScript, Rust stays in
`crawler/`.
