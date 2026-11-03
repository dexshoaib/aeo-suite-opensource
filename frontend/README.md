# AEO Suite — Frontend

Next.js 16 (App Router) + React 19 + Tailwind CSS v4 dashboard and auth
skeleton: headless session auth routed through Next.js proxy rewrites
(ADR-0005), pure client-side organization tenancy contract (Decision 5),
shadcn/ui primitives, server-side session guard with on-demand rendering
(`/dashboard` dynamic `ƒ`), and a strictly typed API client generated from the
backend's OpenAPI 3.0 schema.

Runs natively on Windows, macOS, or Linux — no Docker required in
development. Prerequisites: Node.js 22+ LTS, [pnpm](https://pnpm.io/) 10.34.7.

## 1. Prerequisites (one-time)

Node.js 22 LTS or newer (`node -v`). Enable and activate the pinned pnpm
version via Corepack:

    corepack enable
    corepack prepare pnpm@10.34.7 --activate

Verify the toolchain versions:

    node -v   # v22.x.x
    pnpm -v   # 10.34.7

If Corepack is not available in your Node distribution, install the pinned
version globally (`npm install -g pnpm@10.34.7`).

## 2. Environment

**None required.** The Next.js build and standard local development run out
of the box with zero environment variables set.

If your Django backend runs on a non-standard port or remote host, create a
`.env.local` file inside `frontend/` (gitignored, never committed):

    Copy-Item .env.example .env.local

The frontend reads exactly one server-side variable:

| Key | Purpose | Default |
| --- | --- | --- |
| `BACKEND_ORIGIN` | Upstream Django server URL for server-side `/api/*` rewrites. Never prefix with `NEXT_PUBLIC_` — the browser must never know the backend origin. | `http://127.0.0.1:8000` |

## 3. Install and run

Install dependencies using the locked catalog:

    cd frontend
    pnpm install

In CI and automated scripts, always use `--frozen-lockfile` to guarantee
reproducibility:

    pnpm install --frozen-lockfile

Run the Next.js development server:

    pnpm dev

The application boots on `http://localhost:3000`.

## 4. Development loop & backend pairing

To exercise the full authentication and tenancy flows, run the backend and
frontend concurrently in separate terminals:

1. **Terminal 1 (Backend):**
   ```powershell
   cd backend
   uv run python manage.py runserver 127.0.0.1:8000
   ```
2. **Terminal 2 (Frontend):**
   ```powershell
   cd frontend
   pnpm dev
   ```

### Architecture & Proxying (ADR-0005)
The browser talks exclusively to `http://localhost:3000`. All requests to
`/api/*` are forwarded server-side by Next.js rewrites to `BACKEND_ORIGIN`
(`http://127.0.0.1:8000`), preserving cookies as first-party without requiring
CORS middleware on the Django backend.

### Smoke Check
Open `http://localhost:3000` in your browser:
- Anonymous users see the landing hero with links to `/login` and `/signup`.
- Authenticated users are routed to `/dashboard`.
- Verify the live health badge on `/dashboard` displays **System Healthy**
  (polling `/api/v1/health/` through the rewrite proxy).

## 5. Typed API client (`schema.d.ts`)

The typed API client (`src/lib/api/schema.d.ts`) is generated from the DRF
backend's OpenAPI 3.0 schema and committed to the repository.

### Local Client Regeneration (URL-based)
With the backend server running on `127.0.0.1:8000`:

    pnpm generate:client

This calls `openapi-typescript http://127.0.0.1:8000/api/schema/ -o src/lib/api/schema.d.ts`.

### Offline / File-Based Regeneration (CI Drift Gate)
In CI or without a live dev server, the client is regenerated directly from
an exported schema file:

    cd backend
    uv run python manage.py spectacular --file "$env:TEMP\schema.yaml"
    cd ../frontend
    pnpm exec openapi-typescript "$env:TEMP\schema.yaml" -o src/lib/api/schema.d.ts

(on macOS/Linux, substitute `/tmp/schema.yaml` for `"$env:TEMP\schema.yaml"`).

### The Schema Drift Contract
Whenever a backend serializer, view, or URL changes, **regenerate and commit
`schema.d.ts` in the same change**. CI runs `git diff --exit-code -- src/lib/api/schema.d.ts`;
any uncommitted client drift fails the build immediately.

## 6. Quality gates (what CI runs)

From `frontend/`, the same checks CI runs on every push:

    pnpm lint         # eslint .
    pnpm typecheck    # tsc --noEmit
    pnpm test         # vitest run (pure logic & tenancy unit tests)
    pnpm build        # next build (production bundle & dynamic route checks)

Expected results:
- `lint`: 0 errors, 0 warnings.
- `typecheck`: clean exit code 0.
- `test`: 14/14 tests pass (`src/lib/org.test.ts`).
- `build`: production build compiles cleanly; `/dashboard` outputs as dynamic
  `ƒ` (server-side session guard with `cache: "no-store"`), all other routes static `○`.
