"use client";

import { useEffect, useState } from "react";
import client from "@/lib/api/client";
import {
  getSelectedOrgId,
  setSelectedOrgId,
  resolveSelectedOrgId,
  type OrgSummary,
} from "@/lib/org";
import { OrgForm, type CreatedOrg } from "./org-form";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Building2Icon, CheckIcon, ChevronsUpDownIcon } from "lucide-react";

interface OrgSwitcherProps {
  selectedOrgId?: string | null;
  onOrgChange?: (orgId: string | null) => void;
  onResetNotice?: (notice: string | null) => void;
}

export function OrgSwitcher({
  selectedOrgId: externalSelectedId,
  onOrgChange,
  onResetNotice,
}: OrgSwitcherProps) {
  const [orgs, setOrgs] = useState<OrgSummary[]>([]);
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const activeOrgId =
    externalSelectedId !== undefined ? externalSelectedId : internalSelectedId;

  // 1. After mount: read client storage and fetch active memberships
  useEffect(() => {
    let mounted = true;

    async function loadOrgs() {
      try {
        const { data, response } = await client.GET("/api/v1/organizations/");
        if (!mounted) return;

        if (response.ok && data) {
          const list: OrgSummary[] = data.map((o) => ({ id: o.id, name: o.name }));
          setOrgs(list);

          const stored = getSelectedOrgId();
          const { selectedId: validId, resetNotice } = resolveSelectedOrgId(list, stored);
          setInternalSelectedId(validId);
          if (onOrgChange) onOrgChange(validId);
          if (onResetNotice && resetNotice) onResetNotice(resetNotice);
        } else {
          setOrgs([]);
          setInternalSelectedId(null);
          if (onOrgChange) onOrgChange(null);
        }
      } catch {
        if (mounted) {
          setOrgs([]);
          setInternalSelectedId(null);
          if (onOrgChange) onOrgChange(null);
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadOrgs();

    return () => {
      mounted = false;
    };
  }, [onOrgChange, onResetNotice]);

  const handleSelect = (orgId: string) => {
    setSelectedOrgId(orgId);
    setInternalSelectedId(orgId);
    if (onOrgChange) onOrgChange(orgId);
    if (onResetNotice) onResetNotice(null);
  };

  const handleCreated = (newOrg: CreatedOrg) => {
    const updated = [...orgs, { id: newOrg.id, name: newOrg.name }];
    setOrgs(updated);
    handleSelect(newOrg.id);
  };

  const currentOrg = orgs.find((o) => o.id === activeOrgId);

  if (loading) {
    return (
      <div className="flex h-9 items-center gap-2 rounded-md border border-neutral-200 bg-white px-3 text-xs text-neutral-500">
        <Building2Icon className="h-4 w-4 animate-pulse text-neutral-400" />
        <span>Loading organizations...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <DropdownMenu>
        <DropdownMenuTrigger className="flex h-9 min-w-[200px] cursor-pointer items-center justify-between gap-2 rounded-md border border-neutral-300 bg-white px-3 text-xs font-medium text-neutral-900 shadow-2xs transition hover:bg-neutral-50 focus:outline-none">
          <div className="flex items-center gap-2 truncate">
            <Building2Icon className="h-4 w-4 shrink-0 text-neutral-500" />
            <span className="truncate">
              {currentOrg?.name ?? "No organization selected"}
            </span>
          </div>
          <ChevronsUpDownIcon className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56 p-1">
          <DropdownMenuLabel className="px-2 py-1.5 text-2xs font-semibold uppercase tracking-wider text-neutral-500">
            Organizations
          </DropdownMenuLabel>
          {orgs.length === 0 ? (
            <div className="px-2 py-3 text-center text-xs text-neutral-500">
              No organizations found.
            </div>
          ) : (
            orgs.map((org) => (
              <DropdownMenuItem
                key={org.id}
                onClick={() => handleSelect(org.id)}
                className="flex cursor-pointer items-center justify-between rounded px-2 py-1.5 text-xs text-neutral-800 hover:bg-neutral-100"
              >
                <span className="truncate">{org.name}</span>
                {org.id === activeOrgId && (
                  <CheckIcon className="h-3.5 w-3.5 text-neutral-900" />
                )}
              </DropdownMenuItem>
            ))
          )}
          <DropdownMenuSeparator className="my-1 border-neutral-200" />
          <div className="p-1">
            <OrgForm
              onSuccess={handleCreated}
              triggerLabel="Create Organization"
              className="w-full justify-center text-xs"
            />
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
