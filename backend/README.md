# AEO Suite — Backend

Django 6 + Django REST Framework API: an email-only custom user model,
organization/workspace tenancy with membership-checked access (foreign
data answers 404, never 403), cookie-session auth through django-allauth
in headless mode, and a strictly validated OpenAPI schema at
`/api/schema/` with interactive docs at `/api/docs/`.

Runs natively on Windows, macOS, or Linux — no Docker required in
development. Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/),
PostgreSQL 16+.

## 1. Database (one-time)

The app connects as a least-privilege role: `LOGIN` + `CREATEDB`, not a
superuser. `CREATEDB` is required because pytest creates and destroys a
scratch database (`test_aeo_suite`) on every test run; nothing beyond
that is granted. From a `psql` session as your admin user (PowerShell):

    psql -U postgres -h localhost
    CREATE ROLE aeo LOGIN PASSWORD '<choose-a-strong-password>' CREATEDB;
    CREATE DATABASE aeo_suite OWNER aeo;
    \q

The `postgres` password is whatever you set during the PostgreSQL
install. If `psql` answers `password authentication failed for user
"postgres"`, use that install-time password — or reset it the standard
way: temporarily set `trust` for local connections in `pg_hba.conf`,
`ALTER ROLE postgres WITH PASSWORD '...'`, restore `scram-sha-256`,
reload.

## 2. Environment

Copy the template to a `.env` file at the REPOSITORY ROOT (gitignored,
never committed):

    Copy-Item .env.example .env

Fill in real values. The backend reads exactly these keys:

| Key | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Long random string: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_DEBUG` | `True` locally; never `True` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `DATABASE_URL` | `postgres://aeo:<password>@localhost:5432/aeo_suite` |
| `CSRF_TRUSTED_ORIGINS` | Frontend origin(s) allowed to post forms; default `http://localhost:3000` |

## 3. Install, migrate, run

    cd backend
    uv sync
    uv run python manage.py migrate
    uv run python manage.py runserver

Smoke check while the server runs (PowerShell):

    Invoke-RestMethod http://localhost:8000/api/v1/health/

    status database
    ------ --------
    ok     ok

- `200` with `{"status": "ok", "database": "ok"}` — service and
  database healthy.
- `503` with `{"status": "error", "database": "error"}` — the server
  is up but the database is unreachable: re-check `DATABASE_URL` and
  that PostgreSQL is running (`Get-Service postgresql*`).

Interactive API docs: `http://localhost:8000/api/docs/` (the `/api/v1/`
surface) and `http://localhost:8000/api/auth/openapi.yaml` (the auth
endpoints). Django admin: `http://localhost:8000/admin/` after
`uv run python manage.py createsuperuser`.

Development emails (verification mail on signup, password resets)
print to the server console — no SMTP is configured locally.

## 4. Tests

    uv run pytest

Tests run on real PostgreSQL, never SQLite: pytest-django creates and
destroys `test_aeo_suite` around each run — that is what the role's
`CREATEDB` is for. Expected result: all tests pass with exactly one
warning, `RemovedInDjango2028Warning` about the `EMAIL_BACKEND`
setting name. That is a Django 6 deprecation (horizon 2028) tracked
for a future settings migration; nothing fails on it today.

## 5. Gates (what CI runs)

From `backend/`, the same checks CI runs on every push:

    uv run ruff check .
    uv run python manage.py check
    uv run python manage.py makemigrations --check --dry-run
    uv run python manage.py spectacular --file "$env:TEMP\schema.yaml" --validate --fail-on-warn
    uv run pytest

The schema gate is strict — zero warnings tolerated — because the
frontend's TypeScript client is generated from `/api/schema/`.

## 6. Auth and cookies (frontend integration notes)

- The single auth surface is JSON under `/api/auth/` — headless
  endpoints, no server-rendered auth pages. Browser clients use
  `/api/auth/browser/v1/...` (signup, login, current session).
- Sessions are cookie-based: signup/login issue the session cookie,
  and that same cookie authorizes `/api/v1/` calls.
- There is no CORS middleware in development; the frontend runs
  behind a same-origin proxy. If you serve the frontend from another
  origin, add it to `CSRF_TRUSTED_ORIGINS`.
- The JSON signup contract is `{email, password}` — a password
  confirmation field is a UI concern and does not exist in the API.

## 7. Management commands

    uv run python manage.py list_workspaces <organization-id>

Lists the workspaces of one organization without a request object —
the same scoping helper that request-less contexts (background jobs,
commands) use. Unknown and malformed ids answer the same error and
never reveal whether an organization exists.
