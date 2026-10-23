/**
 * Organization selection state and helpers.
 *
 * Selection and Tenancy Contract:
 * 1. Stored in localStorage as the org ID only (string UUID).
 * 2. Read client-side after mount (never during SSR — avoids hydration mismatches).
 * 3. Stored ID validated on load against the user's memberships; falls back to the first membership if invalid.
 * 4. Cleared on logout.
 * 5. Clean 404-reset helper: when an org-scoped fetch returns 404, stale selection is reset
 *    to a valid membership and returns a visible notice string (never an error wall).
 * 6. Header helper: emits { "X-Organization-ID": id } per request.
 */

export const ORG_STORAGE_KEY = "aeo_selected_org_id";

export interface OrgSummary {
  id: string;
  name?: string;
}

/**
 * Read the selected organization ID from localStorage (client-side only).
 */
export function getSelectedOrgId(): string | null {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }
  return window.localStorage.getItem(ORG_STORAGE_KEY);
}

/**
 * Save the selected organization ID to localStorage (client-side only).
 * If null is passed, removes the stored value.
 */
export function setSelectedOrgId(orgId: string | null): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }
  if (orgId) {
    window.localStorage.setItem(ORG_STORAGE_KEY, orgId);
  } else {
    window.localStorage.removeItem(ORG_STORAGE_KEY);
  }
}

/**
 * Clear the selected organization ID from localStorage (on logout or account switch).
 */
export function clearSelectedOrgId(): void {
  setSelectedOrgId(null);
}

/**
 * Generate request headers for org-scoped API calls.
 */
export function getOrgHeaders(orgId?: string | null): Record<string, string> {
  const effectiveId = orgId ?? getSelectedOrgId();
  if (!effectiveId) {
    return {};
  }
  return { "X-Organization-ID": effectiveId };
}

export interface ResolveOrgResult {
  selectedId: string | null;
  resetNotice: string | null;
}

/**
 * Validate the stored organization ID against current active memberships.
 * - If storedId matches an existing membership, it remains selected.
 * - If storedId is stale (not in memberships) or absent, it falls back to the first membership.
 * - If user has zero memberships, selectedId is null.
 * - When a stale ID is replaced, a visible notice is returned.
 */
export function resolveSelectedOrgId(
  memberships: OrgSummary[],
  storedId: string | null = getSelectedOrgId()
): ResolveOrgResult {
  if (!memberships || memberships.length === 0) {
    clearSelectedOrgId();
    return { selectedId: null, resetNotice: null };
  }

  if (storedId) {
    const match = memberships.find((org) => org.id === storedId);
    if (match) {
      return { selectedId: match.id, resetNotice: null };
    }
  }

  // Fallback to first membership
  const fallback = memberships[0];
  setSelectedOrgId(fallback.id);

  const resetNotice = storedId
    ? `The previously selected organization is no longer accessible. Switched to ${fallback.name ?? fallback.id}.`
    : null;

  return { selectedId: fallback.id, resetNotice };
}

/**
 * 404 clean-reset helper.
 * When an org-scoped call returns 404 (e.g. org deleted, membership revoked),
 * resets the selection to a valid membership and returns a user-facing notice.
 */
export function handleOrg404Reset(
  memberships: OrgSummary[],
  failedOrgId?: string | null
): ResolveOrgResult {
  const remaining = memberships.filter((org) => org.id !== failedOrgId);
  if (remaining.length > 0) {
    const fallback = remaining[0];
    setSelectedOrgId(fallback.id);
    return {
      selectedId: fallback.id,
      resetNotice: `Organization not found or accessible. Switched to ${fallback.name ?? fallback.id}.`,
    };
  }

  clearSelectedOrgId();
  return {
    selectedId: null,
    resetNotice: "Organization not found. You do not belong to any other organizations.",
  };
}
