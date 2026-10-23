import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  ORG_STORAGE_KEY,
  getSelectedOrgId,
  setSelectedOrgId,
  clearSelectedOrgId,
  getOrgHeaders,
  resolveSelectedOrgId,
  handleOrg404Reset,
  type OrgSummary,
} from "./org";

describe("Organization selection contract", () => {
  let mockStorage: Record<string, string> = {};

  const fakeLocalStorage = {
    getItem: (key: string) => mockStorage[key] ?? null,
    setItem: (key: string, value: string) => {
      mockStorage[key] = value;
    },
    removeItem: (key: string) => {
      delete mockStorage[key];
    },
    clear: () => {
      mockStorage = {};
    },
  };

  beforeEach(() => {
    mockStorage = {};
    (globalThis as unknown as { window?: unknown }).window = {
      localStorage: fakeLocalStorage,
    };
  });

  afterEach(() => {
    delete (globalThis as unknown as { window?: unknown }).window;
  });

  describe("After-mount / SSR safety", () => {
    it("returns null safely when window is undefined (SSR)", () => {
      delete (globalThis as unknown as { window?: unknown }).window;
      expect(getSelectedOrgId()).toBeNull();
    });

    it("does not throw on write when window is undefined", () => {
      delete (globalThis as unknown as { window?: unknown }).window;
      expect(() => setSelectedOrgId("any-id")).not.toThrow();
      expect(() => clearSelectedOrgId()).not.toThrow();
    });
  });

  describe("ID-only storage in localStorage", () => {
    it("stores only the string ID without objects or tokens", () => {
      const orgId = "org-uuid-123";
      setSelectedOrgId(orgId);

      expect(mockStorage[ORG_STORAGE_KEY]).toBe("org-uuid-123");
      expect(getSelectedOrgId()).toBe("org-uuid-123");
    });

    it("removes storage key when setting null", () => {
      mockStorage[ORG_STORAGE_KEY] = "org-uuid-123";
      setSelectedOrgId(null);

      expect(mockStorage[ORG_STORAGE_KEY]).toBeUndefined();
      expect(getSelectedOrgId()).toBeNull();
    });
  });

  describe("Clear-on-logout", () => {
    it("clears selected organization from storage", () => {
      mockStorage[ORG_STORAGE_KEY] = "active-org-id";
      clearSelectedOrgId();

      expect(mockStorage[ORG_STORAGE_KEY]).toBeUndefined();
      expect(getSelectedOrgId()).toBeNull();
    });
  });

  describe("Validate-on-load fallback", () => {
    const memberships: OrgSummary[] = [
      { id: "org-alpha", name: "Alpha Corp" },
      { id: "org-beta", name: "Beta LLC" },
    ];

    it("preserves selection when stored ID matches an active membership", () => {
      mockStorage[ORG_STORAGE_KEY] = "org-beta";

      const result = resolveSelectedOrgId(memberships);
      expect(result.selectedId).toBe("org-beta");
      expect(result.resetNotice).toBeNull();
      expect(mockStorage[ORG_STORAGE_KEY]).toBe("org-beta");
    });

    it("falls back to the first membership when stored ID is absent", () => {
      const result = resolveSelectedOrgId(memberships, null);
      expect(result.selectedId).toBe("org-alpha");
      expect(result.resetNotice).toBeNull();
      expect(mockStorage[ORG_STORAGE_KEY]).toBe("org-alpha");
    });

    it("falls back to the first membership and returns notice when stored ID is stale", () => {
      mockStorage[ORG_STORAGE_KEY] = "stale-deleted-org";

      const result = resolveSelectedOrgId(memberships, "stale-deleted-org");
      expect(result.selectedId).toBe("org-alpha");
      expect(result.resetNotice).toContain("Alpha Corp");
      expect(mockStorage[ORG_STORAGE_KEY]).toBe("org-alpha");
    });

    it("clears selection when user belongs to zero organizations", () => {
      mockStorage[ORG_STORAGE_KEY] = "stale-org";

      const result = resolveSelectedOrgId([]);
      expect(result.selectedId).toBeNull();
      expect(result.resetNotice).toBeNull();
      expect(mockStorage[ORG_STORAGE_KEY]).toBeUndefined();
    });
  });

  describe("404 clean-reset path", () => {
    const memberships: OrgSummary[] = [
      { id: "org-alpha", name: "Alpha Corp" },
      { id: "org-beta", name: "Beta LLC" },
    ];

    it("switches to remaining membership with visible notice upon 404", () => {
      const result = handleOrg404Reset(memberships, "org-alpha");

      expect(result.selectedId).toBe("org-beta");
      expect(result.resetNotice).toContain("Beta LLC");
      expect(mockStorage[ORG_STORAGE_KEY]).toBe("org-beta");
    });

    it("clears storage when no remaining memberships exist upon 404", () => {
      const singleMembership: OrgSummary[] = [
        { id: "org-only", name: "Only Corp" },
      ];

      const result = handleOrg404Reset(singleMembership, "org-only");

      expect(result.selectedId).toBeNull();
      expect(result.resetNotice).toContain("do not belong to any other organizations");
      expect(mockStorage[ORG_STORAGE_KEY]).toBeUndefined();
    });
  });

  describe("Request header generation", () => {
    it("returns empty object when no organization is selected", () => {
      expect(getOrgHeaders(null)).toEqual({});
    });

    it("returns X-Organization-ID header when org ID is provided", () => {
      expect(getOrgHeaders("custom-org-uuid")).toEqual({
        "X-Organization-ID": "custom-org-uuid",
      });
    });

    it("reads from storage when no parameter is passed", () => {
      mockStorage[ORG_STORAGE_KEY] = "stored-org-uuid";
      expect(getOrgHeaders()).toEqual({
        "X-Organization-ID": "stored-org-uuid",
      });
    });
  });
});
