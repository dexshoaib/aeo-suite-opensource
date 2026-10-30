"use client";

import { useEffect, useState, useCallback } from "react";
import client from "@/lib/api/client";
import { handleOrg404Reset, type OrgSummary } from "@/lib/org";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { FolderIcon, PlusIcon, AlertCircleIcon, LayersIcon } from "lucide-react";

interface WorkspaceItem {
  id: string;
  name: string;
  created_at?: string;
}

interface WorkspaceFormProps {
  selectedOrgId: string | null;
  onOrg404Reset?: (newOrgId: string | null, notice: string) => void;
}

export function WorkspaceForm({
  selectedOrgId,
  onOrg404Reset,
}: WorkspaceFormProps) {
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    if (!selectedOrgId) {
      return;
    }

    async function loadWorkspaces(orgId: string) {
      setLoading(true);
      setError(null);

      try {
        const { data, response } = await client.GET("/api/v1/workspaces/", {
          headers: {
            "X-Organization-ID": orgId,
          },
        });

        if (ignore) return;

        if (response.status === 404) {
          // Org was deleted or revoked — trigger clean reset
          try {
            const { data: orgsData } = await client.GET("/api/v1/organizations/");
            const orgList: OrgSummary[] = orgsData?.map((o) => ({ id: o.id, name: o.name })) ?? [];
            const { selectedId: fallbackId, resetNotice } = handleOrg404Reset(orgList, orgId);
            if (onOrg404Reset && resetNotice) {
              onOrg404Reset(fallbackId, resetNotice);
            }
          } catch {
            // ignore fallback fetch error
          }
          if (!ignore) setWorkspaces([]);
          return;
        }

        if (response.ok && data) {
          if (!ignore) setWorkspaces(data as unknown as WorkspaceItem[]);
        } else {
          if (!ignore) setWorkspaces([]);
        }
      } catch {
        if (!ignore) {
          setError("Failed to load workspaces for the selected organization.");
          setWorkspaces([]);
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    }

    loadWorkspaces(selectedOrgId);

    return () => {
      ignore = true;
    };
  }, [selectedOrgId, onOrg404Reset]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !selectedOrgId) return;

    setCreating(true);
    setError(null);

    try {
      const { data, response, error: err } = await client.POST("/api/v1/workspaces/", {
        headers: {
          "X-Organization-ID": selectedOrgId,
        },
        body: {
          name: name.trim(),
        } as unknown as { name: string; readonly id: string; readonly organization: string; readonly created_at: string; readonly updated_at: string },
      });

      if (response.status === 404) {
        // Org was deleted or revoked
        const { data: orgsData } = await client.GET("/api/v1/organizations/");
        const orgList: OrgSummary[] = orgsData?.map((o) => ({ id: o.id, name: o.name })) ?? [];
        const { selectedId: fallbackId, resetNotice } = handleOrg404Reset(orgList, selectedOrgId);
        if (onOrg404Reset && resetNotice) {
          onOrg404Reset(fallbackId, resetNotice);
        }
        return;
      }

      if (response.ok && data) {
        setName("");
        setWorkspaces((prev) => [...prev, data as unknown as WorkspaceItem]);
      } else {
        const errObj = err as unknown as { name?: string[] } | undefined;
        const msg = errObj?.name?.[0] ?? "Failed to create workspace.";
        setError(msg);
      }
    } catch {
      setError("An unexpected error occurred while creating the workspace.");
    } finally {
      setCreating(false);
    }
  };

  if (!selectedOrgId) {
    return (
      <Card className="border-dashed border-neutral-300 bg-white">
        <CardContent className="flex flex-col items-center justify-center py-12 text-center">
          <LayersIcon className="h-10 w-10 text-neutral-300" />
          <h3 className="mt-3 text-sm font-medium text-neutral-800">
            No Organization Selected
          </h3>
          <p className="mt-1 text-xs text-neutral-500">
            Select or create an organization above to view and manage workspaces.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Create Workspace Card */}
      <Card className="bg-white">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-neutral-900">
            Create Workspace
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="flex gap-2">
            <Input
              type="text"
              required
              placeholder="e.g. Production Environment"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={creating}
              className="max-w-md text-xs"
            />
            <Button
              type="submit"
              size="sm"
              disabled={creating || !name.trim()}
              className="gap-1.5 text-xs"
            >
              <PlusIcon className="h-3.5 w-3.5" />
              {creating ? "Creating..." : "Add Workspace"}
            </Button>
          </form>
          {error && (
            <div
              role="alert"
              className="mt-3 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-2.5 text-xs text-red-700"
            >
              <AlertCircleIcon className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Workspaces List Card */}
      <Card className="bg-white">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium text-neutral-900">
            Workspaces ({workspaces.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-6 text-center text-xs text-neutral-500">
              Loading workspaces...
            </div>
          ) : workspaces.length === 0 ? (
            <div className="py-8 text-center text-xs text-neutral-500">
              No workspaces created yet for this organization.
            </div>
          ) : (
            <div className="divide-y divide-neutral-100">
              {workspaces.map((ws) => (
                <div
                  key={ws.id}
                  className="flex items-center justify-between py-3 text-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <FolderIcon className="h-4 w-4 text-neutral-400" />
                    <span className="font-medium text-neutral-800">
                      {ws.name}
                    </span>
                  </div>
                  <span className="font-mono text-2xs text-neutral-400">
                    {ws.id.slice(0, 8)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
