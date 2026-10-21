# AEO Software: Technical Build Documentation

> **Source of truth** for the AEO SaaS build. Authored Oct 15, 2026 (@Shoaib).
> **Rev 2 (Oct 15, 2026) supersedes Rev 1** — applied to this file Oct 17, 2026 with owner approval ("approved with modifications": Rev 2 verbatim, with the amendment annotations below retained).
>
> **Amendment register** (transparent changes; details in `docs/decisions/`):
> - **[ADR-0001](decisions/ADR-0001-no-docker-in-development.md) — Development without Docker (approved by product owner, Oct 17, 2026; RE-AFFIRMED Oct 17, 2026 against Rev 2):** During the development phase, all services run as plain local processes on the owner's device (no Docker Compose). Docker is introduced at the production/deployment stage. The "Deployment" section below still describes the original Docker Compose plan and applies from production onward.
> - **[ADR-0002](decisions/ADR-0002-task-queue-interface.md) — Task queue interface (approved by product owner, Oct 17, 2026; RE-AFFIRMED Oct 17, 2026 against Rev 2):** Development uses `django.tasks` (Django 6 built-in) with the `django-tasks` DatabaseBackend on local PostgreSQL — no Redis in development for chunks 0.1–1.2. Production keeps Celery + Redis in Docker, unchanged from this document. All async work goes through one thin internal `enqueue()` facade.
> - **[ADR-0003](decisions/ADR-0003-layered-content-engine-and-cross-encoder-routing.md) — Layered content engine + cross-encoder routing (approved by product owner, Oct 18, 2026):** Fix generation uses the layered design — three paths (template-only / constrained LLM rewrite / ask the customer) feeding one validator; code routes on a local cross-encoder score. All five corrective requirements from the honest assessment are hard requirements (retrieve-then-rerank, thresholds tuned on ~200 labeled pairs, validator after every path, low band = "no good passage on this page", swappable provider). Every routing decision is logged; thresholds live in config. Build order: extract + template + validator first, LLM layer only when data shows template failures. Validator interface is specified before the router. Chunking is structure-aware. The standalone "Deterministic Semantic Templating Blueprint" is retired as a build target (source material for the template path only); its "$0.00 / sub-5ms / zero risk" claims are excluded from all specs.
> - **[ADR-0004](decisions/ADR-0004-tenant-isolation-and-security-hardening.md) — Tenant isolation and security hardening (approved by product owner, Oct 18, 2026):** Primary tenant isolation = one base manager + one base viewset + automated cross-tenant leak test. The security blueprint's `SET LOCAL` middleware is rejected as written (no-op outside a transaction block; no RLS policy consumes the variable); Postgres RLS permitted later as defense-in-depth, its own decision. Org context from any client-supplied header is accepted only after a server-side membership check — format validation is not authorization. Credential vault uses Fernet with MultiFernet rotation from day one. Hardening matrix adopted; raw f-string SQL banned by CI lint; tests always run on PostgreSQL.
> - **Rev 2 changelog (Oct 15, 2026 — owner-approved application Oct 17, 2026):** (1) Architecture diagram added — 11 components incl. Playwright worker and billing provider as outside services. (2) Intent taxonomy renamed: "buying intent" → informational / comparison / navigational. (3) Adaptive measurement runs: start 10/engine/week, extend to ~30 where the confidence interval stays too wide; 20–30 runs is a pilot-confirmed target, not a proven rule. (4) Citation rates reported per intent type; never average intents; intent classification: navigational = code rules, informational vs comparison = decision model; fix recommendations segmented by intent. (5) Capacity example extended (30 runs/prompt → 600k queries/week → sampling must be adaptive). (6) Decision-model candidate named: "TypeSafe Jev" (early access; test against a small LM on ~200 labeled examples before committing). (7) Phase 2 exit criterion now "reliable rates per intent" with adaptive multi-run queries. (8) The Rev 1 step "store the raw answer and the cited URLs for every run" no longer appears as a bulleted step — the data model (answer table, object storage) is unchanged, so this is presentational only.

If the code and this document disagree, stop and ask the product owner. Do not silently change the architecture; propose the change and wait for approval.

---

## Recommended stack at a glance

Keep Django and DRF for the backend, use PostgreSQL instead of MySQL, build the dashboard in TypeScript, and use Rust only where it earns its place: the crawler and audit engine.

| Layer | Recommended | Why | Alternative |
|---|---|---|---|
| Frontend | Next.js (React and TypeScript) | Mature tables, charts, auth and billing libraries; server-rendered public pages for your free audit tool | SvelteKit; Leptos (Rust) if you insist |
| Crawler and audit engine | Rust service | Fast HTML parsing, many parallel fetches, low memory | Python with asyncio to start |
| API | Django and DRF | Admin, auth, ORM and migrations out of the box; fastest path to a working product | Django Ninja for typed endpoints |
| Background jobs | Celery with Redis | Long prompt runs, retries and schedules | Dramatiq; Temporal later |
| Main database | PostgreSQL | JSONB for crawl results, full-text search, partitioning, pgvector | MySQL works but is weaker here |
| Time-series results | Postgres partitions first | Citation checks become millions of rows | ClickHouse or TimescaleDB later |
| Files | S3-compatible storage (Cloudflare R2 or S3) | Crawl snapshots and report PDFs | Local disk in development |
| AI layer | Rules in code, a language model for rewriting, optional decision model | See the decision layer section | Provider-agnostic wrapper |
| Auth | Django allauth with sessions or JWT | Teams, invites, roles | Clerk |
| Billing | A payments provider that supports your country and your customers' countries | Check Stripe, Razorpay and merchant-of-record services before choosing | None needed for pilots |
| Hosting | Docker on a VPS with managed Postgres | Cheap and simple at the start | AWS or GCP when you outgrow it |
| Monitoring | Sentry and structured logs | Catch failed crawls and API errors early | Grafana later |

## Frontend: should it be Rust?

No: build the dashboard in TypeScript with Next.js, and use Rust for the crawler, where it makes a real difference. A Rust frontend is possible, but it will slow you down in the phase where speed matters most.

Your product is a data-heavy dashboard. Tables, charts, forms, filters and white-label reports are far better served by the React ecosystem (TanStack Table, Recharts, shadcn/ui).

Rust frontends are younger. Leptos, Yew and Dioxus compile to WebAssembly and have smaller component ecosystems, fewer examples, and slower build cycles. AI coding assistants are also less reliable on them.

Your public pages must be fast and crawlable. An AEO tool whose own site is not optimized for AI answers is a poor advertisement. Server-rendered Next.js makes the free audit page and marketing pages easy to get right.

You still get type safety. Generate the API schema from DRF with drf-spectacular, then generate a typed TypeScript client from it with openapi-typescript. A change in a Django serializer then breaks the frontend build, not production.

If you still want Rust on the frontend, use Leptos with server-side rendering, and start it after the product has paying customers, not before.

## Architecture

The dashboard talks only to the Django API. Django hands slow work to the Redis queue, where Celery workers and the Rust crawler pick it up. Workers read and write PostgreSQL through Django's code, and the crawler posts its results back to Django.

**Django is the hub; heavy work runs in queued workers.** 11 components (transcribed from the Rev 2 diagram; dashed = outside services, arrows point from caller to callee):

| # | Component | Role |
|---|---|---|
| 1 | Next.js dashboard | Reports, approvals, free audit; typed client from OpenAPI |
| 2 | **Django and DRF API** (hub) | Accounts, plans, approvals; business logic; OpenAPI schema |
| 3 | Billing provider *(outside)* | Payments and webhooks; keeps plan state in sync |
| 4 | PostgreSQL | Sites, runs, answers, audits; source of truth |
| 5 | Redis | Job queue for workers; rate limits and cache |
| 6 | Object storage | HTML snapshots, report PDFs; Cloudflare R2 or S3 |
| 7 | Celery workers | Prompt runs, reports, fixes; read and write the database |
| 8 | Rust crawler | Fetches pages, runs page rules; posts results back to Django |
| 9 | Playwright worker | Renders JavaScript pages; called by the crawler |
| 10 | AI engines and models *(outside)* | Citation queries, rewrites, decision calls through APIs |
| 11 | Customer websites *(outside)* | Crawled for page audits; fixes published via WordPress |

## Backend: Django and DRF

Build one Django project as a modular monolith, with a separate app per concern, and split out only the crawler. This keeps deployment simple and lets you ship faster than with microservices.

### Suggested Django apps

- **accounts**: users, organizations, roles and invites.
- **sites**: client sites, domains and ownership verification.
- **prompts**: prompt sets grouped by topic and intent type (informational, comparison, navigational).
- **measurements**: runs, raw AI answers, extracted citations.
- **audits**: page snapshots, rule scores and issues.
- **fixes**: generated changes, approvals, publish log and rollback data.
- **reports**: white-label PDF and web reports.
- **billing**: plans, usage counters and subscription state.

**Multi-tenancy.** Use one shared database with an organization ID on every tenant row. The hierarchy is agency organization, then client workspace, then site. Enforce the filter in one base manager and base viewset, and add an automated test that fails if any endpoint returns another organization's data. *(Amended by [ADR-0004](decisions/ADR-0004-tenant-isolation-and-security-hardening.md): this base manager + leak test is the primary control; a `SET LOCAL` session-variable middleware is rejected as written, and PostgreSQL RLS is permitted later as defense-in-depth only; org context supplied via request header is accepted only after a server-side membership check.)*

**API.** Use DRF viewsets under `/api/v1/`, with drf-spectacular generating the OpenAPI schema, pagination on every list, and throttling tied to the customer's plan.

**Background jobs.** Use Celery with Redis for crawl dispatch, prompt runs and report building. Make every task idempotent, retry with backoff, apply per-organization rate limits, and store job state in the database so the dashboard can show progress.

Django admin is your internal operations console for free: use it to inspect failed runs and support customers.

## Database and storage

Use PostgreSQL as the single source of truth, Redis for queues and caching, and S3-compatible object storage for large files. Add a dedicated analytics database only when the numbers demand it.

| Store | Holds | Notes |
|---|---|---|
| PostgreSQL | Organizations, sites, pages, prompts, runs, answers, citations, audits, fixes | JSONB for audit results; partition the answers table by month |
| Redis | Celery queue, rate-limit counters, short-lived cache | Not a source of truth |
| Object storage | Raw HTML snapshots, raw AI answers if large, report PDFs | Cloudflare R2 or S3 |
| ClickHouse (later) | Citation time series for fast dashboards | Add when Postgres dashboards slow down, likely at tens of millions of rows |

Core tables: `site`, `page`, `page_snapshot`, `prompt`, `run` (prompt, engine, time), `answer` (raw text, cited URLs), `citation`, `audit_result`, `fix`, `publish_event`.

**Why Postgres over MySQL.** MySQL would work, but Postgres gives you better JSONB handling, table partitioning and extensions such as pgvector, which you may want for matching passages to questions. Django supports both equally.

Take daily backups with point-in-time recovery, and test a restore before you onboard paying customers.

## Crawler and page audit engine (Rust)

Build the crawler as a separate Rust service that takes a crawl job, fetches pages in parallel, runs rule-based checks, and returns JSON to Django. This is where Rust gives you real speed and low memory use.

**How it connects.** Django puts a job (site, URL list, limits) on a Redis queue. The Rust worker picks it up, crawls, and posts results to an internal Django endpoint. Keep the contract as plain JSON so you can swap the implementation later.

**Suggested crates:** tokio (async runtime), reqwest (HTTP), scraper or lol_html (HTML parsing), url, and a robots.txt parser. Pages that need JavaScript to render should go to a separate Playwright worker; rendering JavaScript from Rust is hard and not worth building yourself.

**Rule-based checks (all in code, no AI):**

1. Direct answer placed near the top of the page.
2. Heading structure, including question-style headings.
3. JSON-LD structured data present and valid (FAQPage, Article, Organization, Product).
4. Access for AI crawlers in robots.txt and in actual server responses.
5. Canonical tags, page size, load time, publish and update dates, author information.
6. Consistent brand and entity details across pages.

Each check returns a score, a severity and a plain-language issue. Version the rule set so a score of 72 this month means the same as a score of 72 last month.

**Crawling rules.** Identify your crawler with a clear user agent, respect robots.txt and rate limits, and crawl only domains the customer has verified as theirs.

If Rust slows you down at the start, write the first version in Python with the same JSON contract and port it once the rules settle.

## Citation measurement engine

Measure citations by asking each AI engine each prompt many times and reporting a rate with a confidence range, because a single answer proves nothing.

1. Build a prompt set for each site: 30 to 100 prompts, each tagged with a topic and an intent type (informational, comparison or navigational).
2. Query engines through official APIs where they exist and record which engine and model version answered. API answers can differ from what people see in the consumer apps, so say so in your reports.
3. Repeat each prompt several times (for example 5 to 10) per engine per week.
4. Repeat each prompt adaptively: start at 10 runs per engine per week and extend up to about 30 where the confidence range is still too wide to decide anything. Treat 20 to 30 runs as a target to confirm on your own pilot data, not a proven rule.
5. Parse citations in code: match the customer's domain and URLs, and match brand names with a list of spelling variants.
6. Report the citation rate per intent type as cited runs divided by total runs, with a Wilson confidence interval, and compare before and after a change only when the intervals clearly separate. Do not average intents together: a brand can be cited often on informational prompts and almost never on comparison prompts, and each needs a different fix.
7. Control cost with a prompt quota per plan, scheduling, and caching.

**Intent classification.** Tag each prompt with its intent when you create it. Navigational prompts usually contain a brand or domain name, so rules in code can catch them; separating informational from comparison is a fuzzier judgment that suits the small decision model. Fix recommendations then depend on the segment: a low comparison rate points toward comparison pages and structured product data, and a low informational rate points toward answer-first content.

**Capacity example.** 50 sites with 100 prompts, 5 runs each, on 4 engines is 100,000 queries a week. At 30 runs per prompt the same load is 600,000, which is why sampling must be adaptive. Measure your real cost per query in the first pilot and set plan limits from that number.

**Do not scrape chat interfaces.** It breaks often and may violate the providers' terms. Google AI Overviews has no official API, so treat it as optional and use a third-party search data provider, with the method disclosed.

## Rules, decision model and language model

Use code for anything with a right answer, a decision model for fuzzy high-volume judgments, and a language model only where text must be written.

| Decision | Layer | Why |
|---|---|---|
| Was my URL cited? | Code | Exact URL or domain match |
| Is the schema valid? | Code | A validator gives a definite answer |
| Page score and fix priority | Code | A formula using traffic, citation rate and audit score |
| Before and after statistics | Code | Arithmetic must be exact |
| Sentiment of a brand mention | Decision model or small language model | Fuzzy, and thousands of cases |
| Does this passage answer the question directly? | Decision model or small language model | Fuzzy judgment *(Amended by [ADR-0003](decisions/ADR-0003-layered-content-engine-and-cross-encoder-routing.md): implemented as a local cross-encoder in the retrieve-then-rerank routing step; thresholds tuned, decisions logged.)* |
| Intent of a prompt (informational, comparison, navigational) | Code rules for navigational; decision model or small language model for the rest | Classification |
| Auto-apply a fix or send it to a human | Code thresholds on model confidence and risk rules | Keep the final control in rules you can read |
| Rewrite copy, draft FAQ answers | Language model | Generation |

### Rules for the AI layer

- Put every model behind one interface, for example `decide(question, state)` returning a choice and a confidence, so you can swap providers.
- Validate every model output in code before saving it, and log the model name, version and input.
- Never let a rewrite add facts that are not on the page or supplied by the customer.
- Test the TypeSafe Jev decision model against a small language model on about 200 labeled examples before committing to either. It is in early access, and its speed and cost claims are mostly the vendor's own.

## Publishing fixes safely

Start by handing customers a ready-to-paste change set, then add one-click WordPress publishing with approval and rollback. Publishing to a customer's live site is the highest-risk feature you will build.

**Phase one:** output a downloadable change set with a diff, new JSON-LD blocks and rewritten sections that the customer applies themselves.

**Phase two:** publish to WordPress through its REST API, and add Shopify later.

Every publish follows the same steps:

1. Generate the fix.
2. Validate it in code: valid HTML, valid schema, length limits, and no claims that are not on the page.
3. Show the customer a diff.
4. Require approval, at least at first.
5. Publish as a draft or live, with the previous version stored.
6. Re-crawl the page to confirm the change appears.
7. Log the event and start the measurement window.

Provide a one-click rollback, an audit log of who approved what, and per-site permissions. Store WordPress credentials encrypted.

## Auth, billing and agency accounts

Design accounts around agencies from day one, because agencies are your best first customer and they manage many client sites.

**Roles:** owner, admin, editor and viewer, plus a read-only client portal that shows white-label reports.

**Hierarchy:** agency organization, client workspace, site. Invites work at the agency and workspace level.

**Auth:** Django allauth with sessions for the web app, and API keys for agencies that want to integrate.

**Plans and quotas:** meter by sites, prompts per month and runs per month. Enforce limits in code and keep a usage table.

**Billing:** mirror the subscription state in your database and handle payment webhooks idempotently. Confirm that your payment provider supports your country and your customers' countries before you commit.

**Free audit tool:** rate limit it and add a captcha, since it will attract bots.

**Data deletion:** build a delete-everything path for a site and for an organization early.

## Testing and proving results

Test the code in layers, and test the product claim separately with controlled experiments, because the claim that your fixes raise citations is what customers pay for.

### Code tests

- **Rust crawler:** cargo tests and snapshot tests on saved HTML fixtures with known expected scores.
- **Django:** pytest with a real Postgres, including the test that no endpoint leaks another organization's data.
- **API contract:** regenerate the TypeScript client from the OpenAPI schema in CI so a breaking change fails the build.
- **End to end:** Playwright flows for sign-up, adding a site, running an audit and approving a fix.
- **Load:** simulate your expected traffic. For example, crawl 10,000 pages and run the weekly query volume from the capacity example, then check queue delay and database load.
- **Decision-layer tests:** keep a golden set of about 200 labeled examples. CI fails if accuracy drops below the agreed threshold when you change a model or prompt.

### Product experiments

Run them on your own sites first.

- Split pages into treated and untreated control groups, because AI answers drift on their own.
- Fix the metric before you start, run at least four weeks, and report intervals, not single numbers.
- Publish pilot results only with the customer's permission.

## Deployment, cost and security

Run everything as Docker containers on one cheap server with managed Postgres at first, and move to larger infrastructure only when load requires it.

**Containers:** Next.js web app, Django API (gunicorn), Celery worker, Celery beat scheduler, Rust crawler, Playwright worker. Use Docker Compose in development and CI on GitHub Actions. *(Amended: see ADR-0001 — development runs without Docker; Docker Compose applies from the production stage onward.)*

**Main variable cost:** AI engine queries. Set a monthly AI budget per organization, cache repeat calls, and batch where the provider allows it.

**Secrets:** keep API keys in environment variables or a secret manager, and encrypt customers' site credentials at rest. *(Amended by [ADR-0004](decisions/ADR-0004-tenant-isolation-and-security-hardening.md): the at-rest vault is Fernet wrapped in MultiFernet so key rotation is a configuration event from day one.)*

**Tenant isolation:** automated tests, plus rate limiting on every public endpoint.

**Observability:** Sentry for errors, structured logs, and an alert when a crawl or measurement job fails repeatedly.

**Compliance:** respect robots.txt and each provider's API terms, publish a privacy policy, and support data deletion.

