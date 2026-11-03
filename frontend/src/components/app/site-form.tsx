"use client";

import { useState } from "react";
import client from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { PlusIcon, AlertCircleIcon, GlobeIcon } from "lucide-react";

interface WorkspaceOption {
  id: string;
  name: string;
}

interface SiteFormProps {
  selectedOrgId: string | null;
  workspaces: WorkspaceOption[];
  defaultWorkspaceId?: string;
  onSuccess: () => void;
  triggerLabel?: string;
}

export function SiteForm({
  selectedOrgId,
  workspaces,
  defaultWorkspaceId,
  onSuccess,
  triggerLabel = "Add Site",
}: SiteFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [workspaceId, setWorkspaceId] = useState(
    defaultWorkspaceId || workspaces[0]?.id || ""
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleOpenChange = (isOpen: boolean) => {
    setOpen(isOpen);
    if (isOpen) {
      // Always resync on open so the form follows the workspace filter
      // the user just picked, instead of a stale selection from mount.
      setWorkspaceId(defaultWorkspaceId || workspaces[0]?.id || "");
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const effectiveWorkspaceId = workspaceId || defaultWorkspaceId || workspaces[0]?.id;
    if (!selectedOrgId || !name.trim() || !domain.trim() || !effectiveWorkspaceId) {
      setError("Please fill out all fields.");
      return;
    }

    // Mirror the server-side normalization, then require a dotted host
    // before anything is sent (SPEC-1.1 criterion 6).
    const host = domain
      .trim()
      .toLowerCase()
      .replace(/^https?:\/\//, "")
      .split("/")[0]
      .split("?")[0]
      .split("#")[0]
      .split(":")[0];
    if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(host)) {
      setError("Enter a valid domain (e.g. example.com).");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const { data, response, error: err } = await client.POST("/api/v1/sites/", {
        headers: {
          "X-Organization-ID": selectedOrgId,
        },
        body: {
          name: name.trim(),
          domain: host,
          workspace: effectiveWorkspaceId,
        } as unknown as {
          name: string;
          domain: string;
          workspace: string;
          readonly id: string;
          readonly organization: string;
          readonly verification_status: "pending" | "verified" | "failed";
          readonly verification_token: string;
          readonly created_at: string;
          readonly updated_at: string;
        },
      });

      if (response.ok && data) {
        setName("");
        setDomain("");
        setOpen(false);
        onSuccess();
      } else {
        const errObj = err as unknown as
          | { name?: string[]; domain?: string[]; workspace?: string[]; detail?: string }
          | undefined;
        const msg =
          errObj?.domain?.[0] ||
          errObj?.workspace?.[0] ||
          errObj?.name?.[0] ||
          errObj?.detail ||
          "Failed to create site.";
        setError(msg);
      }
    } catch {
      setError("An unexpected error occurred while adding the site.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-800 shadow-2xs transition hover:bg-neutral-50">
        <PlusIcon className="h-3.5 w-3.5" />
        {triggerLabel}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <GlobeIcon className="h-4 w-4 text-neutral-600" />
            <DialogTitle className="text-sm font-semibold text-neutral-900">
              Add New Site
            </DialogTitle>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          {error && (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-2.5 text-xs text-red-700"
            >
              <AlertCircleIcon className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="site-workspace" className="block text-xs font-medium text-neutral-700">
              Workspace
            </label>
            <select
              id="site-workspace"
              value={workspaceId || workspaces[0]?.id || ""}
              onChange={(e) => setWorkspaceId(e.target.value)}
              className="w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs shadow-2xs outline-none focus:border-neutral-900"
              disabled={submitting}
              required
            >
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="site-name" className="block text-xs font-medium text-neutral-700">
              Site Name
            </label>
            <Input
              id="site-name"
              placeholder="e.g. Marketing Website"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={submitting}
              className="text-xs"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="site-domain" className="block text-xs font-medium text-neutral-700">
              Domain
            </label>
            <Input
              id="site-domain"
              placeholder="e.g. example.com or docs.example.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              disabled={submitting}
              className="text-xs"
              required
            />
            <p className="text-2xs text-neutral-400">
              Protocol (https://) and trailing paths are automatically normalized.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setOpen(false)}
              disabled={submitting}
              className="text-xs cursor-pointer"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={submitting || !name.trim() || !domain.trim()}
              className="text-xs cursor-pointer"
            >
              {submitting ? "Adding..." : "Add Site"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
