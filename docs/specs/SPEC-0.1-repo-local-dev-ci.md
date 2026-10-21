# SPEC-0.1: Repository, Local Dev Environment, CI Skeleton

**Status:** DRAFT — awaiting owner approval
**Chunk:** 0.1 (Phase 0) · **Workflow step:** DEFINE output (per chunk loop)

---

## Statement of Intent

- **Outcome:** One versioned repo that every later chunk lands in, with CI green from day one and a documented local (no-Docker) runbook on the owner's Windows machine.
- **Why now:** Every later chunk needs a stable scaffold, a pinned tool contract, and a CI gate before any product code exists.
- **Success:** Fresh clone + setup script verifies the toolchain on the owner's device; a push triggers a green CI run; ADRs 0001/0002 are recorded.
- **Constraint:** No Docker and no Redis in development (ADR-0001, ADR-0002); everything runs as local processes on Windows.
- **Out of scope:** Django project (0.2), Next.js app (0.3), Rust crate (1.1), any product feature, any deployment work.

## Decisions (owner-approved during DEFINE)

1. **Private GitHub repo + GitHub Actions** for version control and CI.
2. **Development without Docker** — plain local processes; Docker introduced at the production stage (ADR-0001).
3. **Task queue:** dev = `django.tasks` (Django 6 built-in) + `django-tasks` DatabaseBackend on the existing local PostgreSQL; prod = Celery + Redis in Docker, unchanged from the architecture doc. App code touches one thin internal `enqueue()` interface, never a broker directly (ADR-0002). Consequence: **Redis is not required for chunks 0.1–1.2.**
4. **Rust stays the crawler language** (architecture doc, "Crawler and page audit engine"); `cargo` is a required dev tool.

## Assumptions (veto now, or I proceed with these)

1. **Python tooling: uv** (venv + lockfile); Python ≥ 3.12 (Django 6.0 floor).
2. **Frontend tooling: pnpm** via corepack; Node ≥ 20 (22 LTS recommended).
3. **PostgreSQL ≥ 16** installed locally (owner confirmed installed; script verifies version).
4. **Rust stable** toolchain via rustup.
5. **Branching:** trunk-based; one PR per chunk; Conventional Commits (`type(scope): summary`).
6. **CI shape:** one workflow, path-filtered jobs per area (backend / frontend / crawler) that **auto-skip while their directories are still empty**; unit/build/integration/e2e/security stages stubbed with TODOs tied to future chunks.

## Project structure (scaffold only — placeholders, no application code)

```
backend/                  # Django + DRF (chunk 0.2)   → README.md placeholder
frontend/                 # Next.js + TS (chunk 0.3)   → README.md placeholder
crawler/                  # Rust audit engine (1.1)    → README.md placeholder
docs/
  ARCHITECTURE.md         # already written (source of truth)
  specs/                  # this file
  decisions/              # ADR-0001, ADR-0002 written at ship
scripts/
  setup-dev.ps1           # Windows toolchain check: python, node, psql, cargo
.github/workflows/ci.yml
.env.example              # placeholder keys only, no real secrets
.gitignore
README.md                 # quickstart: clone → setup → what runs where
```

## Commands

- **Owner, Windows:** `powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1`
- **CI:** automatic on every push / PR to `main`.

## CI stage order (product rule; stages light up as chunks land)

`lint → typecheck → unit → build → integration → e2e → security audit`

0.1 delivers: ruff slot (backend), eslint + tsc slot (frontend), `cargo fmt/clippy/check` slot (crawler) — each defined but auto-skipping until its directory has code.

## Testing strategy (for this chunk)

- `setup-dev.ps1`: verified on the owner's machine; owner pastes the output as evidence.
- CI: verified with one green run on the scaffold **and one intentional red run** (temporary failing step) to prove checks actually execute — a CI that can't fail is theater.

## Acceptance criteria

1. Repo matches the structure above and is pushed to the private GitHub repo.
2. CI is green on push; jobs exist for backend/frontend/crawler and auto-skip while empty.
3. `setup-dev.ps1` exits 0 on the owner's machine (all ✔), or prints exact install guidance for anything missing.
4. README quickstart present; `docs/ARCHITECTURE.md` committed; ADR-0001 and ADR-0002 recorded in `docs/decisions/`.
5. `.env.example` contains placeholders only; `.gitignore` excludes `.env`, venvs, `node_modules/`, Rust `target/`; no secrets anywhere in history.
6. Diff touches only the files listed in the structure — no unrelated changes.

## Definition of Done

Per owner workflow: acceptance criteria met, lint/type clean, self-review done, docs updated, small conventional commits, pushed, owner approval received.

## Open questions

- Repo name — owner's choice when creating the private GitHub repo (suggestion: `aeo-suite`). Non-blocking.
