# AEO Suite

AEO (Answer Engine Optimization) software that gets web pages cited by AI assistants such as ChatGPT, Perplexity and Gemini. Positioning: **"we fix your pages"**, not "we show you a dashboard."

> Built in public. Early development: there is no product to try yet.

## What it will do

- **Audit** pages for AI-answer readiness with rule-based checks.
- **Measure** how often AI assistants cite a site. Every prompt runs many times, and each citation rate comes with a confidence interval, reported separately for informational, comparison and navigational questions.
- **Fix** pages through three paths: a template when the page already has a strong answer, a tightly constrained language-model rewrite when the answer is buried, and a request to the customer when the page has no good answer. Every fix passes one validator before it goes anywhere.
- **Publish** changes with customer approval, a stored previous version and one-click rollback.

## Design principles

- **Code decides, AI assists.** Anything with a right answer (citation matching, schema validation, scoring, statistics) is plain code. AI writes text and makes fuzzy judgments, and every AI output is validated.
- **Measure before claiming.** A fix only counts if the measured numbers move.
- **Safe by default.** Approval and rollback on publishing, and automated tests that fail if one customer's data can leak to another.
- **Play by the rules.** Official APIs only, no scraping of chat interfaces, and the crawler respects robots.txt.

## Status

Repository scaffold, CI and the backend foundation (Django 6, multi-tenancy base, custom user, organizations and workspaces) are in place. See `docs/decisions/` for the decisions made so far.

## Early pilots

I'm looking for a few agencies and site owners to try early versions and shape what gets built. Sign up: [DM on X](https://x.com/dexshoaib) or [LinkedIn](https://www.linkedin.com/in/shoaib-alam-ansari-88b197377).

## Stack

Django + DRF, PostgreSQL, Next.js + TypeScript, Rust crawler.

## Run it locally (Windows)

```powershell
git clone https://github.com/dexshoaib/aeo-suite.git
cd aeo-suite
powershell -ExecutionPolicy Bypass -File scripts\setup-dev.ps1
copy .env.example .env # then edit values; never commit .env
```

`setup-dev.ps1` checks for git, Python 3.12+, Node 20+, PostgreSQL 16+ and Rust, and prints install hints for anything missing. Development runs as local processes, with no Docker.

## How we work

One small piece at a time, each through DEFINE, PLAN, BUILD, VERIFY, REVIEW and SHIP, with owner approval at every step and a short decision record (ADR) for anything expensive to reverse. Specs live in `docs/specs/` and decisions in `docs/decisions/`.

## CI

GitHub Actions runs path-filtered jobs for backend, frontend and crawler. A change that adds real code without wiring its CI stage fails the build: green-with-placeholders is not allowed.

## Follow along

- LinkedIn: https://www.linkedin.com/in/shoaib-alam-ansari-88b197377
- X: https://x.com/dexshoaib
