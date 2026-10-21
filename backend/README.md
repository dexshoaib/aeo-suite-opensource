# backend/ — Django + DRF API (modular monolith)

Lands in **chunk 0.2** per `docs/specs/SPEC-0.1-repo-local-dev-ci.md`.

One Django project, one app per concern (accounts, sites, prompts,
measurements, audits, fixes, reports, billing), DRF viewsets under
`/api/v1/`, OpenAPI schema via drf-spectacular. Multi-tenancy enforced in
one base manager + base viewset with an org-leak test.

Runs locally on Windows without Docker (ADR-0001). See
`docs/ARCHITECTURE.md` ("Backend: Django and DRF") before writing code.
