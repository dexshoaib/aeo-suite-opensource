# ADR-0004: Tenant isolation via base manager + leak tests (RLS optional later); membership-checked org context; MultiFernet vault

## Status

Accepted (product owner, 2026-10-18 — "we go with your verdict only", full review approved without exceptions)

## Date

2026-10-18

## Context

The Development Security Blueprint (bare-metal, no Docker/Redis — aligned
with ADR-0001/0002) proposed a tenant-isolation middleware that binds
`SET LOCAL app.current_organization_id = %s` to the PostgreSQL session on
every request, keyed off an `X-Organization-ID` request header.

Review of 2026-10-18 (owner-approved) found two real defects:

1. **The middleware is a no-op as written.** `SET LOCAL` only has effect
   inside a transaction block; the blueprint's `process_request` executes
   it bare (no enclosing `transaction.atomic()`), so the binding silently
   does nothing. Worse, nothing in the blueprint ever *consumes* the
   variable — no PostgreSQL RLS policy is shown — so the session variable
   defends nothing even when set.
2. **The header path has an authorization hole.** The middleware
   validates only that `X-Organization-ID` is a well-formed UUID
   (`uuid.UUID(org_id)`); it never checks that the requesting user is a
   member of that organization. Any authenticated user could claim any
   org id.

The blueprint's other sections are sound: ORM/parameterized-cursor SQL
discipline, Fernet-based credential encryption at rest, and the local
hardening matrix (least-privilege DB user, localhost-only binding, DEBUG
discipline).

## Decision

**1. Primary tenant isolation is the pattern `ARCHITECTURE.md` already
mandates:** one shared database, organization id on every tenant row,
enforced in **one base manager + one base viewset**, plus an **automated
cross-tenant leak test** that fails if any endpoint returns another
organization's data. This is the primary and testable control. Chunk 0.2
implements exactly this.

**2. The `SET LOCAL` middleware pattern is rejected as proposed.** A
session variable earns its keep only when a PostgreSQL Row Level Security
policy consumes it:

    CREATE POLICY tenant_isolation ON core_measurement_answer
      USING (workspace_id = current_setting('app.current_organization_id')::uuid);

Postgres RLS is **permitted later as defense-in-depth**, as its own
decision with its own ADR, and only with the `transaction.atomic()`
scoping the original blueprint omitted. It is not scheduled.

**3. Organization context switching rule (chunk 0.2 AC):** an
`X-Organization-ID`-style header (or any client-supplied org selector) is
accepted **only after a server-side membership check** for the
authenticated user. Server-side membership is the authority; the header
is a selector, never a credential. Format validation alone is not
authorization.

**4. Credential vault: Fernet with MultiFernet from day one.**
`MultiFernet` wraps the primary key with a standby key so rotation is a
configuration event, not a re-encryption migration. Applies to WordPress
credentials and provider API keys when those chunks land. The vault
raises on a missing `FIELD_ENCRYPTION_KEY` (fail closed), as the
blueprint already does.

**5. Hardening matrix adopted for chunk 0.2+:** the local database user
gets standard DML privileges on the application schema only (never the
postgres superuser); `ALLOWED_HOSTS` stays localhost-only in
development; `DEBUG` discipline per the blueprint.

**6. SQL discipline kept as a lint rule, not prose:** raw SQL must use
parameterized `cursor()` execution; f-string/`+`-built SQL is banned.
Enforced by a CI grep/lint step when the backend code lands.

**7. Test database is PostgreSQL, always.** The blueprint's own class
name (`SQLiteAndPostgresTenantIsolationMiddleware`) notwithstanding —
SQLite does not support `SET LOCAL` and JSONB behaves differently.
Per SPEC-0.1, tests run on real Postgres; a silent SQLite fallback is a
defect, not a convenience.

## Alternatives Considered

### Fix the middleware (wrap request in transaction.atomic, add RLS policies) and keep it

- Pros: database-level isolation is the strongest pattern; survives a
  forgotten filter in a future viewset
- Cons: request-scoped transactions for every request; RLS policy
  maintenance across every tenant table; Django migrations do not run as
  the tenant role; meaningful complexity before any tenant exists
- **Deferred** — RLS later as defense-in-depth if/when warranted; base
  manager + leak tests first

### Trust the header after UUID validation (blueprint as written)

- Pros: zero extra queries
- Cons: format validation is not authorization; any authenticated user
  claims any org
- **Rejected** (security defect)

### django-encrypted-model-fields / django-fernet-fields packages for the vault

- Pros: maintained field types, less bespoke code
- Cons: extra dependency for a small, well-understood primitive;
  MultiFernet rotation is trivial to own
- **Rejected** for now — hand-rolled vault stays small and fail-closed

## Consequences

- Chunk 0.2's tenancy acceptance criteria now include: base manager +
  base viewset enforcement, the automated leak test, and the
  membership-checked org-context rule (D1 + D2 of the approved review).
- The security blueprint remains a reference; its middleware section is
  annotated as superseded by this ADR (reference file kept verbatim in
  `docs/references/dev_security_blueprint.pdf`).
- Key rotation procedure (MultiFernet standby key) must be documented in
  `.env.example` comments when the vault lands.
- The CI raw-SQL lint step is owed when backend code lands (chunk 0.2+).
