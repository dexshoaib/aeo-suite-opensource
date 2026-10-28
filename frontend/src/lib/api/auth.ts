import { ensureCsrfToken } from "./client";
import { clearSelectedOrgId } from "../org";

export interface AuthUser {
  id: string;
  email: string;
  display?: string;
  has_usable_password?: boolean;
}

export interface AuthError {
  code: string;
  message: string;
  param?: string;
}

interface AllauthResponse<T = unknown> {
  status?: number;
  data?: T;
  errors?: AuthError[];
  message?: string;
  meta?: {
    is_authenticated?: boolean;
  };
}

async function authFetch<T>(
  url: string,
  options: RequestInit = {}
): Promise<{ status: number; ok: boolean; data?: T; errors?: AuthError[] }> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }

  if (
    typeof document !== "undefined" &&
    !["GET", "HEAD", "OPTIONS"].includes(method)
  ) {
    const csrf = await ensureCsrfToken();
    if (csrf && !headers.has("X-CSRFToken")) {
      headers.set("X-CSRFToken", csrf);
    }
  }

  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers,
  });

  let json: AllauthResponse<T> | null = null;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    try {
      json = (await response.json()) as AllauthResponse<T>;
    } catch {
      json = null;
    }
  }

  if (!response.ok) {
    const errors: AuthError[] =
      json?.errors ??
      (json?.message ? [{ code: "error", message: json.message }] : []);
    return {
      status: response.status,
      ok: false,
      data: json?.data,
      errors,
    };
  }

  return {
    status: response.status,
    ok: true,
    data: json?.data ?? (json as unknown as T),
  };
}

/**
 * Probe current authentication status.
 * GET /api/auth/browser/v1/auth/session
 * Returns authenticated user or null.
 */
export async function getSession(): Promise<{
  isAuthenticated: boolean;
  user: AuthUser | null;
}> {
  try {
    const res = await authFetch<{ user: AuthUser }>(
      "/api/auth/browser/v1/auth/session",
      { method: "GET" }
    );
    if (res.ok && res.data?.user) {
      return { isAuthenticated: true, user: res.data.user };
    }
    return { isAuthenticated: false, user: null };
  } catch {
    return { isAuthenticated: false, user: null };
  }
}

export interface AuthCredentials {
  email: string;
  password: string;
}

/**
 * Log in with email + password.
 * POST /api/auth/browser/v1/auth/login
 */
export async function login(credentials: AuthCredentials): Promise<{
  success: boolean;
  user?: AuthUser;
  errors?: AuthError[];
}> {
  const res = await authFetch<{ user: AuthUser }>(
    "/api/auth/browser/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify(credentials),
    }
  );

  if (res.ok && res.data?.user) {
    return { success: true, user: res.data.user };
  }
  return {
    success: false,
    errors:
      res.errors && res.errors.length > 0
        ? res.errors
        : [{ code: "invalid", message: "Invalid email or password." }],
  };
}

/**
 * Sign up with email + password.
 * POST /api/auth/browser/v1/auth/signup
 */
export async function signup(credentials: AuthCredentials): Promise<{
  success: boolean;
  user?: AuthUser;
  errors?: AuthError[];
}> {
  const res = await authFetch<{
    user?: AuthUser;
    flows?: Array<{ id: string; is_pending?: boolean }>;
  }>("/api/auth/browser/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify(credentials),
  });

  // Allauth returns 200 (authenticated) or 401 (created, pending email verification)
  const isPendingVerification =
    res.status === 401 && (!res.errors || res.errors.length === 0);

  if (res.ok || isPendingVerification) {
    return { success: true, user: res.data?.user };
  }
  return {
    success: false,
    errors:
      res.errors && res.errors.length > 0
        ? res.errors
        : [{ code: "invalid", message: "Sign up failed." }],
  };
}

/**
 * Log out current session and clear local organization selection.
 * DELETE /api/auth/browser/v1/auth/session
 */
export async function logout(): Promise<boolean> {
  try {
    const res = await authFetch("/api/auth/browser/v1/auth/session", {
      method: "DELETE",
    });
    // Clear local organization state on logout
    clearSelectedOrgId();
    return res.ok;
  } catch {
    clearSelectedOrgId();
    return false;
  }
}

/**
 * Normalizes a verification key. Handles:
 * - Full URLs or query parameters (e.g. "?key=..." or "/account/verify-email/?key=...")
 * - URL encoding (e.g. %3A -> :) produced by Django's URL renderer
 * - Whitespace, wrapping quotes, or trailing punctuation from console copying
 */
export function normalizeVerificationKey(rawKey: string): string {
  let k = rawKey.trim();

  // If user copied the full URL or query string, extract the key parameter
  if (k.includes("key=")) {
    const match = k.match(/[?&]key=([^&#\s]+)/) || k.match(/^key=([^&#\s]+)/);
    if (match) {
      k = match[1];
    }
  }

  // Strip wrapping quotes
  k = k.replace(/^["']|["']$/g, "");

  // Strip internal whitespace or newlines from terminal line wrapping
  k = k.replace(/\s+/g, "");

  // Repeatedly decode URI components (e.g. %3A -> :)
  while (k.includes("%")) {
    try {
      const decoded = decodeURIComponent(k);
      if (decoded === k) break;
      k = decoded;
    } catch {
      break;
    }
  }

  return k.trim();
}

/**
 * Verify email address with key from verification email.
 * POST /api/auth/browser/v1/auth/email/verify
 */
export async function verifyEmail(key: string): Promise<{
  success: boolean;
  errors?: AuthError[];
}> {
  const normalizedKey = normalizeVerificationKey(key);
  const res = await authFetch<{ user?: AuthUser }>(
    "/api/auth/browser/v1/auth/email/verify",
    {
      method: "POST",
      body: JSON.stringify({ key: normalizedKey }),
    }
  );

  // Allauth returns 200 (authenticated) or 401 (verified but unauthenticated)
  if (res.ok || res.status === 401) {
    return { success: true };
  }
  return {
    success: false,
    errors:
      res.errors && res.errors.length > 0
        ? res.errors
        : [{ code: "invalid_key", message: "Invalid or expired verification key." }],
  };
}

/**
 * Inspect email verification key info.
 * GET /api/auth/browser/v1/auth/email/verify?key=...
 */
export async function getEmailVerificationInfo(key: string): Promise<{
  email?: string;
  user?: AuthUser;
  error?: string;
}> {
  const normalizedKey = normalizeVerificationKey(key);
  const res = await authFetch<{ email?: string; user?: AuthUser }>(
    `/api/auth/browser/v1/auth/email/verify?key=${encodeURIComponent(normalizedKey)}`,
    { method: "GET" }
  );

  if (res.ok && res.data) {
    return { email: res.data.email, user: res.data.user };
  }
  return {
    error:
      res.errors?.[0]?.message ?? "Invalid or expired verification key.",
  };
}
