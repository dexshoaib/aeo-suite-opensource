# SPEC-0.2: Django/DRF Backend Skeleton — Accounts, Tenancy, Auth

**Status:** APPROVED (owner, 2026-10-19 — approved with 5 amendments, applied)
**Chunk:** 0.2 (Phase 0) · **Workflow step:** DEFINE output (per chunk loop)

---

## Statement of Intent

- **Outcome:** A production-quality Django/DRF backend skeleton: settings split, custom user model from migration 0001, `accounts` app (users, organizations, workspaces, memberships), the ADR-0004 tenancy base (one manager, one viewset, one automated leak test, one request-less scoping helper), allauth headless wired, healthcheck endpoint, strictly validated OpenAPI schema, pytest on real Postgres.
- **Why now:** Tenancy and auth are the two foundations that are painful to retrofit; every later app (sites, prompts, measurements, audits, fixes, billing) inherits them.
- **Success:** The leak test fails loudly if any endpoint — or any admin/management-command path — can return another org's data; sign-up/login works through allauth headless API endpoints without any UI; CI green including a Postgres test job and a zero-warnings schema check; OpenAPI schema generates and is served.
- **Constraint:** ADR-0001/0002 (no Docker, no Redis on the dev machine), ADR-0004 (tenancy rules), ADR-0005 (auth cookie transport), Windows + Python 3.12, Django 6.0 (`django.tasks` dependency from ADR-0002).
- **Out of scope:** Next.js app, TypeScript client generation, sites/prompts/measurements/audits/fixes/reports/billing apps, agency API keys, RLS, social login, MFA, real email delivery (console backend only).

## Decisions (owner-approved during DEFINE)

1. **allauth is wired NOW** (owner's explicit call, overriding the leaner default) — in **headless mode**: JSON auth endpoints designed for the future Next.js app; sessions (cookies) remain the auth mechanism, per the architecture doc.
2. **Custom user model from migration 0001** (`AUTH_USER_MODEL` set before the first migrate — the one Django change that is truly painful to retrofit).
3. **Tenancy per ADR-0004 + owner amendments (2026-10-19):** base manager + base viewset enforce org scoping; org context from any client-supplied header is accepted only after a server-side membership check; the automated cross-tenant leak test is structural (walks the tenant viewset registry, so future apps inherit it). **Foreign-org access returns 404, never 403 — a 403 would confirm the organization exists.** One explicit **`scope_to_organization()` helper** covers request-less contexts (Django admin, management commands) and the leak test exercises those paths too; background-task coverage lands with the job queue (see Deferrals).
4. **drf-spectacular in 0.2** (`/api/schema/` + browsable docs); **TS client generation deferred** to the Next.js chunk, which consumes the schema. **CI runs spectacular in strict mode (`--validate --fail-on-warn`) and fails on warnings** — 0.3's TypeScript client is generated from this schema, so a bad schema would break the frontend.
5. **Email + password only** in 0.2 — no social providers, no MFA. Dev uses the console email backend (deliberate deferral, below).
6. **Versions verified 2026-10-18:** Django 6.0 · DRF ≥ 3.17.0 (official Django 6.0 support, released 2026-03-18) · allauth ≥ 65.13.1 (official Django 6.0 support, released 2025-11-20; headless ships an OpenAPI spec). No version fallback needed.
7. **Auth cookie transport per ADR-0005 (owner-directed, recorded 2026-10-19):** dev = **Next.js same-origin proxy** — the browser talks only to the Next.js origin; Django needs no CORS-with-credentials in dev; `CSRF_TRUSTED_ORIGINS` carries the frontend origin. Decided now so chunk 0.3 does not stall on it.

## Assumptions (veto now, or I proceed with these)

1. **uv** for Python deps (`pyproject.toml` + `uv.lock`) — carries over from 0.1.
2. **django-environ** reads `.env` (0.1's `.env.example` grows the backend keys).
3. **ruff** only for 0.2 (lint); mypy/django-stubs deliberately deferred (see Deferrals).
4. Local DB names: `aeo_suite` (dev), test DB auto-created by pytest-django (`test_aeo_suite`).
5. CI runs its Postgres as a GitHub Actions **service container** — this does not violate ADR-0001 (which governs the dev machine, not CI).
6. Trunk-based + Conventional Commits carry over from 0.1.

## Deliberate deferrals (owner-directed, 2026-10-19)

Recorded so silence is never mistaken for oversight:

1. **Row-level security** — permitted later as defense-in-depth only, with its own ADR (ADR-0004 rule 2). Not scheduled.
2. **Backend type checking** — ruff-only in 0.2; mypy + django-stubs deliberately deferred until the backend surface stabilizes; the CI typecheck slot stays a stub.
3. **Email verification in dev** — console email backend; signup/verification mail prints to the console; real delivery is pre-launch hardening.
4. **Background-task tenancy coverage** — the `scope_to_organization()` helper is the hook; the leak-test extension for background jobs lands with the job queue chunk. `core/tenancy.py` carries a note until then.

## Project structure

    backend/
      manage.py
      pyproject.toml            # deps + ruff/pytest config; uv.lock alongside
      README.md                 # runbook: create DB → sync → migrate → run → test → smoke
      config/
        __init__.py
        settings/
          base.py               # shared: INSTALLED_APPS, DRF, allauth headless, spectacular
          local.py              # DEBUG=True, console email, localhost hosts, CSRF origins
          test.py               # fast password hasher, test DB, in-memory email
        urls.py                 # /api/v1/, /api/auth/ (headless), /api/schema/, admin
        wsgi.py · asgi.py
      apps/
        core/                   # shared infra, no product logic:
          models.py             #   TimeStampedModel
          tenancy.py            #   TenantQuerySet / TenantManager / TenantViewSet / scope_to_organization()
          views.py              #   HealthView (liveness + db check)
        accounts/
          models.py             #   User (custom), Organization, Workspace, Membership
          managers.py           #   user manager; org-scoped managers live in core.tenancy
          views.py              #   OrganizationViewSet, WorkspaceViewSet (tenant-scoped)
          serializers.py
          org_context.py        #   membership-checked org resolution → 404 on failure (ADR-0004 rule 3)
      tests/
        conftest.py             # fixtures: two orgs, users, memberships, API client
        test_health.py
        test_auth_headless.py   # signup → login → session → authenticated call
        test_tenancy_leak.py    # THE structural leak test (viewsets + admin + a management command)
        test_org_context.py     # header spoof of a non-member org → 404 (never 403)

## API surface (0.2)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health/` | liveness + db connectivity |
| `/api/auth/…` (allauth headless) | signup, login, logout, session info — JSON, cookie sessions |
| `GET/POST /api/v1/organizations/` | list orgs the user is a member of; create org (creator becomes owner) |
| `GET/POST /api/v1/workspaces/` | scoped to an org the user belongs to (org header + membership check) |
| `GET /api/schema/` + `/api/docs/` | drf-spectacular OpenAPI schema + browsable docs |

## Commands

- **Sync:** `cd backend && uv sync`
- **Migrate:** `uv run python manage.py migrate`
- **Run:** `uv run python manage.py runserver 127.0.0.1:8000`
- **Test:** `uv run pytest`
- **Schema check (strict):** `uv run python manage.py spectacular --file /tmp/schema.yaml --validate --fail-on-warn`
- **Lint:** `uv run ruff check .`
- **CI:** backend job on push/PR to `main` (lights up the 0.1 placeholder): ruff → `manage.py check` → `makemigrations --check` → `spectacular --validate --fail-on-warn` → `pytest` against a Postgres service.

## Testing strategy

- **pytest-django on real Postgres** — never SQLite (ADR-0004 rule 7; JSONB + tenant semantics differ).
- **The leak test is structural:** a registry of tenant viewsets; the test iterates it and asserts a foreign-org user gets **404 (never 403)** on every retrieve/list/update/delete. New apps register into the harness — the guarantee scales without rewriting tests.
- **Request-less paths are covered too:** the leak test additionally walks Django admin views and a management command run through the `scope_to_organization()` helper, asserting no foreign-org rows are visible. Background tasks join the harness when the job queue lands (Deferrals #4).
- **Header-spoof test:** valid cookie + `X-Organization-ID` of a non-member org → **404** (existence hidden, not forbidden).
- **Headless flow test:** signup → login → session cookie → authenticated call to a tenant endpoint.
- **Anti-fake-green:** the CI backend job runs the real suite; the 0.1 guard that failed on premature backend code is retired in the same PR that adds real code.

## Boundaries

- **Always:** `uv run pytest` green before any commit; migrations committed with their models; conventional commits; `.env` ignored.
- **Ask first:** new dependency; settings structure change; changing the tenancy base contract (it is a product-wide interface).
- **Never:** commit secrets; log passwords/tokens; bypass the base manager in any view; use SQLite anywhere; let the header alone authorize org access; return 403 where 404 hides the resource's existence.

## Acceptance criteria

1. `backend/` matches the structure; `uv sync` + `manage.py check` pass on the owner's Windows machine.
2. `AUTH_USER_MODEL` is a custom user active from migration 0001; no auth-related data migrations exist.
3. allauth headless signup/login/session endpoints respond correctly end-to-end via API (pytest evidence; owner smoke run).
4. Tenancy: base manager + viewset enforce org scoping; **foreign-org access returns 404 (never 403)**; the structural leak test passes over viewsets, admin and a management command; the header-spoof test passes with 404.
5. Health endpoint live; OpenAPI schema generates and `/api/docs/` renders.
6. CI backend job green with real Postgres service; ruff clean; `makemigrations --check` clean; **`spectacular --validate --fail-on-warn` exits 0**.
7. Backend README runbook present (create DB → sync → migrate → run → test → smoke-test commands).
8. Diff touches only the files in this structure plus spec/plan/todo and the ci.yml backend job.

## Definition of Done

Per owner workflow: acceptance criteria met, lint/test clean, self-review done, docs updated, small conventional commits, pushed, owner approval received.

## Open questions

- None blocking. DB name/port and ruff rule selection are assumptions above — veto now or they stand.
