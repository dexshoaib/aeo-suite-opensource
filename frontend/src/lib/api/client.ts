import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { getSelectedOrgId } from "../org";

/**
 * Retrieve CSRF token from document.cookie for mutating requests.
 */
export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

let csrfPromise: Promise<string | null> | null = null;

/**
 * Ensure a CSRF token is available in document.cookie.
 * If missing, primes it by fetching allauth headless config.
 */
export async function ensureCsrfToken(): Promise<string | null> {
  if (typeof document === "undefined") return null;
  const existing = getCsrfToken();
  if (existing) return existing;

  if (!csrfPromise) {
    csrfPromise = fetch("/api/auth/browser/v1/config", {
      method: "GET",
      credentials: "include",
    })
      .then(() => getCsrfToken())
      .catch(() => null)
      .finally(() => {
        csrfPromise = null;
      });
  }
  return csrfPromise;
}

const csrfAndOrgMiddleware: Middleware = {
  async onRequest({ request }) {
    // 1. Attach CSRF token on mutating requests
    if (
      typeof document !== "undefined" &&
      !["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())
    ) {
      const csrfToken = await ensureCsrfToken();
      if (csrfToken && !request.headers.has("X-CSRFToken")) {
        request.headers.set("X-CSRFToken", csrfToken);
      }
    }

    // 2. Attach X-Organization-ID header if present in client storage and not explicitly set
    if (typeof window !== "undefined" && !request.headers.has("X-Organization-ID")) {
      const orgId = getSelectedOrgId();
      if (orgId) {
        request.headers.set("X-Organization-ID", orgId);
      }
    }

    return request;
  },
};

export const client = createClient<paths>({
  baseUrl: "", // Same-origin proxy via Next.js rewrites: /api/v1/* -> backend
  credentials: "include",
});

client.use(csrfAndOrgMiddleware);

export default client;
