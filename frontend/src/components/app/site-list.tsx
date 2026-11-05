"use client";

import { useEffect, useState, useMemo } from "react";
import client from "@/lib/api/client";
import { handleOrg404Reset, type OrgSummary } from "@/lib/org";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SiteForm } from "@/components/app/site-form";
import {
  GlobeIcon,
  Trash2Icon,
  AlertCircleIcon,
  CheckCircle2Icon,
  ClockIcon,
  ExternalLinkIcon,
  ShieldCheckIcon,
  CopyIcon,
  ChevronDownIcon,
} from "lucide-react";
import {
  buildMetaSnippet,
  buildWellKnownUrl,
  describeVerificationError,
} from "@/lib/verification";

export interface SiteItem {
  id: string;
  name: string;
  domain: string;
  workspace: string;
  organization: string;
  verification_status: "pending" | "verified" | "failed";
  verification_token: string;
  verified_at?: string | null;
  verification_checked_at?: string | null;
  verification_error?: string;
  created_at?: string;
}

interface WorkspaceOption {
  id: string;
  name: string;
}

interface SiteListProps {
  selectedOrgId: string | null;
  workspaces: WorkspaceOption[];
  onOrg404Reset?: (newOrgId: string | null, notice: string) => void;
}

export function SiteList({
  selectedOrgId,
  workspaces,
  onOrg404Reset,
}: SiteListProps) {
  const [sites, setSites] = useState<SiteItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedWorkspaceFilter, setSelectedWorkspaceFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [tokenPanelId, setTokenPanelId] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let ignore = false;

    if (!selectedOrgId) {
      return;
    }

    async function fetchSites(orgId: string) {
      setLoading(true);
      setError(null);

      try {
        const { data, response } = await client.GET("/api/v1/sites/", {
          headers: {
            "X-Organization-ID": orgId,
          },
        });

        if (ignore) return;

        if (response.status === 404) {
          try {
            const { data: orgsData } = await client.GET("/api/v1/organizations/");
            const orgList: OrgSummary[] =
              orgsData?.map((o) => ({ id: o.id, name: o.name })) ?? [];
            const { selectedId: fallbackId, resetNotice } = handleOrg404Reset(
              orgList,
              orgId
            );
            if (onOrg404Reset && resetNotice) {
              onOrg404Reset(fallbackId, resetNotice);
            }
          } catch {
            // ignore fallback fetch error
          }
          if (!ignore) setSites([]);
          return;
        }

        if (response.ok && data) {
          if (!ignore) setSites(data as unknown as SiteItem[]);
        } else {
          if (!ignore) setSites([]);
        }
      } catch {
        if (!ignore) {
          setError("Failed to load sites for the active organization.");
          setSites([]);
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    fetchSites(selectedOrgId);

    return () => {
      ignore = true;
    };
  }, [selectedOrgId, reloadKey, onOrg404Reset]);

  const handleDelete = async (siteId: string) => {
    if (!selectedOrgId) return;
    setDeletingId(siteId);

    try {
      const { response } = await client.DELETE("/api/v1/sites/{id}/", {
        headers: {
          "X-Organization-ID": selectedOrgId,
        },
        params: {
          path: { id: siteId },
        },
      });

      if (response.ok) {
        setSites((prev) => prev.filter((s) => s.id !== siteId));
      } else {
        setError("Failed to delete site.");
      }
    } catch {
      setError("An unexpected error occurred while deleting the site.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleVerify = async (siteId: string) => {
    if (!selectedOrgId) return;
    setVerifyingId(siteId);
    setError(null);

    try {
      const { data, response } = await client.POST("/api/v1/sites/{id}/verify/", {
        headers: {
          "X-Organization-ID": selectedOrgId,
        },
        params: {
          path: { id: siteId },
        },
      });

      if (response.ok && data) {
        const updated = data as unknown as SiteItem;
        setSites((prev) => prev.map((s) => (s.id === siteId ? updated : s)));
      } else if (response.status === 429) {
        setError("Too many verification attempts. Please try again later.");
      } else {
        setError("Failed to run verification.");
      }
    } catch {
      setError("An unexpected error occurred while verifying the site.");
    } finally {
      setVerifyingId(null);
    }
  };

  const getWorkspaceName = (wsId: string) => {
    return workspaces.find((w) => w.id === wsId)?.name ?? "Unknown Workspace";
  };

  const visibleSites = useMemo(() => {
    if (selectedWorkspaceFilter === "all") {
      return sites;
    }
    return sites.filter((s) => s.workspace === selectedWorkspaceFilter);
  }, [sites, selectedWorkspaceFilter]);

  return (
    <Card className="bg-white">
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <div className="space-y-1">
          <CardTitle className="text-sm font-medium text-neutral-900">
            Tracked Sites ({visibleSites.length})
          </CardTitle>
          <p className="text-2xs text-neutral-500">
            Client sites registered under the active organization.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {workspaces.length > 0 && (
            <select
              aria-label="Filter by workspace"
              value={selectedWorkspaceFilter}
              onChange={(e) => setSelectedWorkspaceFilter(e.target.value)}
              className="rounded-md border border-neutral-300 bg-white px-2.5 py-1 text-2xs shadow-2xs outline-none focus:border-neutral-900"
            >
              <option value="all">All Workspaces</option>
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
          )}

          {workspaces.length > 0 && (
            <SiteForm
              selectedOrgId={selectedOrgId}
              workspaces={workspaces}
              defaultWorkspaceId={
                selectedWorkspaceFilter !== "all" ? selectedWorkspaceFilter : undefined
              }
              onSuccess={() => setReloadKey((k) => k + 1)}
            />
          )}
        </div>
      </CardHeader>

      <CardContent>
        {error && (
          <div
            role="alert"
            className="mb-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-2.5 text-xs text-red-700"
          >
            <AlertCircleIcon className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="py-8 text-center text-xs text-neutral-500">
            Loading sites...
          </div>
        ) : workspaces.length === 0 ? (
          <div className="py-8 text-center text-xs text-neutral-500">
            Create a workspace above before adding client sites.
          </div>
        ) : visibleSites.length === 0 ? (
          <div className="py-8 text-center text-xs text-neutral-500">
            No sites registered yet. Click &quot;Add Site&quot; to begin monitoring domains.
          </div>
        ) : (
          <div className="divide-y divide-neutral-100">
            {visibleSites.map((site) => (
              <div key={site.id}>
                <div className="flex items-center justify-between py-3.5 text-xs">
                  <div className="flex items-start gap-3">
                    <GlobeIcon className="mt-0.5 h-4 w-4 shrink-0 text-neutral-400" />
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-neutral-900">
                          {site.name}
                        </span>
                        <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-2xs font-medium text-neutral-600">
                          {getWorkspaceName(site.workspace)}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-neutral-500">
                        <a
                          href={`https://${site.domain}`}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex items-center gap-1 hover:text-neutral-900 hover:underline"
                        >
                          {site.domain}
                          <ExternalLinkIcon className="h-3 w-3" />
                        </a>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    {site.verification_status === "verified" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-2xs font-medium text-emerald-700">
                        <CheckCircle2Icon className="h-3 w-3" />
                        Verified
                      </span>
                    ) : site.verification_status === "failed" ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-2xs font-medium text-rose-700">
                        <AlertCircleIcon className="h-3 w-3" />
                        Failed
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-2xs font-medium text-amber-700">
                        <ClockIcon className="h-3 w-3" />
                        Pending Verification
                      </span>
                    )}

                    {site.verification_status === "failed" && site.verification_error && (
                      <span
                        className="max-w-48 truncate text-2xs text-rose-600"
                        title={describeVerificationError(site.verification_error)}
                      >
                        {describeVerificationError(site.verification_error)}
                      </span>
                    )}

                    {site.verification_token && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleVerify(site.id)}
                        disabled={verifyingId === site.id}
                        className="h-7 px-2 text-2xs cursor-pointer"
                      >
                        <ShieldCheckIcon className="mr-1 h-3 w-3" />
                        {verifyingId === site.id ? "Verifying..." : "Verify now"}
                      </Button>
                    )}

                    {site.verification_token && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setTokenPanelId((cur) => (cur === site.id ? null : site.id))
                        }
                        className="h-7 w-7 p-0 text-neutral-400 hover:text-neutral-900 cursor-pointer"
                        aria-label={`Toggle verification instructions for ${site.name}`}
                      >
                        <ChevronDownIcon className="h-3.5 w-3.5" />
                      </Button>
                    )}

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(site.id)}
                      disabled={deletingId === site.id}
                      className="h-7 w-7 p-0 text-neutral-400 hover:text-red-600 cursor-pointer"
                      aria-label={`Delete ${site.name}`}
                    >
                      <Trash2Icon className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {tokenPanelId === site.id && site.verification_token && (
                  <div className="space-y-2 rounded-md border border-neutral-200 bg-neutral-50 p-3 text-2xs text-neutral-600">
                    <p className="font-medium text-neutral-700">
                      Prove ownership of {site.domain} with either method, then
                      click Verify now.
                    </p>
                    <div className="space-y-1">
                      <p className="font-medium">Method 1 — meta tag in the homepage head:</p>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 overflow-x-auto rounded bg-white px-2 py-1 font-mono">
                          {buildMetaSnippet(site.verification_token)}
                        </code>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-6 px-2 text-2xs cursor-pointer"
                          onClick={() =>
                            navigator.clipboard?.writeText(
                              buildMetaSnippet(site.verification_token)
                            )
                          }
                        >
                          <CopyIcon className="mr-1 h-3 w-3" />
                          Copy
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-1">
                      <p className="font-medium">Method 2 — host this file:</p>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 overflow-x-auto rounded bg-white px-2 py-1 font-mono">
                          {buildWellKnownUrl(site.domain)}
                        </code>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-6 px-2 text-2xs cursor-pointer"
                          onClick={() =>
                            navigator.clipboard?.writeText(site.verification_token)
                          }
                        >
                          <CopyIcon className="mr-1 h-3 w-3" />
                          Copy token
                        </Button>
                      </div>
                      <p>
                        The file body must contain exactly the token above.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
