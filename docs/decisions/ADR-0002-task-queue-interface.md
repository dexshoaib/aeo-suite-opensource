# ADR-0002: Task queue interface — django.tasks (DB backend) in dev, Celery + Redis in prod

## Status

Accepted (product owner, 2026-10-17)

## Date

2026-10-17

## Context

The architecture doc specifies Celery + Redis for background jobs.
Celery no longer officially supports Windows (the prefork pool does not
work; `--pool=solo` is a workaround), and the owner's development device
is Windows without Redis installed. Meanwhile Django 6.0 (released
2025-12-03) ships a built-in Tasks framework (`django.tasks`: `@task`
decorator, `.enqueue()`, pluggable backends), and the community
`django-tasks` package provides a `DatabaseBackend` with a worker
command that persists tasks in PostgreSQL — a database the dev machine
already runs.

Relevant verified facts (2026-10-17): Django 6.0 release notes (built-in
tasks framework; backends configured via `TASKS` setting); django-tasks
DatabaseBackend + worker command; Celery Windows support status.

## Decision

All asynchronous work goes through **one thin internal queue interface**
(same "one swappable interface" rule the architecture doc applies to AI
providers):

- Application code never imports Celery or `django.tasks` directly; it
  calls the internal `enqueue()` facade.
- **Development backend:** `django.tasks` + `django-tasks`
  DatabaseBackend on the existing local PostgreSQL. No Redis, no extra
  service (ADR-0001 alignment).
- **Production backend:** Celery + Redis in Docker, unchanged from the
  architecture doc. The facade gains a Celery implementation; the swap
  is configuration plus one implementation module, not a rewrite.
- Every task remains idempotent and logs model/inputs per the product
  rules — which is also what makes the two backends interchangeable.

## Alternatives Considered

### Celery everywhere from day one
- Pros: dev/prod identical; no facade needed
- Cons: unsupported on Windows dev; forces Redis installation the owner
  explicitly wanted to avoid; broker debugging before any queue exists
- Rejected for development

### Celery in dev with a database broker (Kombu SQLAlchemy transport)
- Pros: keeps Celery API in dev
- Cons: least-maintained Kombu transport, Celery-on-Windows issues
  remain, worst of both worlds
- Rejected

### django.tasks DB backend in production too
- Pros: dev/prod identical, one less system
- Cons: Postgres-as-queue is the wrong tool at the projected scale
  (~100k engine queries/week), and the doc's Celery choice brings
  retries, rate limits, and beat scheduling the product needs
- Rejected for production; correct for development volumes

## Consequences

- Redis is **not required for development in chunks 0.1–1.2**; it enters
  with the queue work in chunk 1.3 (dev) and never runs on the dev
  machine — it is a production-side component.
- The facade module is a small standing abstraction; if it ever grows
  beyond enqueue/status/result, that is a signal to revisit.
- Scheduled runs (weekly prompt measurement) arrive in chunk 2 and need
  their own bridge: Celery beat in production, a management-command
  loop in development. Designed at that chunk's DEFINE step.
- `.env.example` documents REDIS_URL as commented-out until production.
