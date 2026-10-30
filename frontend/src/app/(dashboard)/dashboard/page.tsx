"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/api/auth";
import { OrgSwitcher } from "@/components/app/org-switcher";
import { WorkspaceForm } from "@/components/app/workspace-form";
import { HealthBadge } from "@/components/app/health-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { LogOutIcon, InfoIcon, XIcon } from "lucide-react";

export default function DashboardPage() {
  const router = useRouter();
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const handleOrgChange = useCallback((orgId: string | null) => {
    setSelectedOrgId(orgId);
  }, []);

  const handleResetNotice = useCallback((msg: string | null) => {
    setNotice(msg);
  }, []);

  const handleOrg404Reset = useCallback((fallbackOrgId: string | null, resetNotice: string) => {
    setSelectedOrgId(fallbackOrgId);
    setNotice(resetNotice);
  }, []);

  const handleLogout = async () => {
    await logout();
    router.push("/login");
    router.refresh();
  };

  return (
    <div className="min-h-screen">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-30 border-b border-neutral-200 bg-white/95 backdrop-blur-xs">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-4">
            <span className="text-base font-semibold tracking-tight text-neutral-900">
              AEO Suite
            </span>
            <div className="h-4 w-px bg-neutral-200" />
            <OrgSwitcher
              selectedOrgId={selectedOrgId}
              onOrgChange={handleOrgChange}
              onResetNotice={handleResetNotice}
            />
          </div>
          <div className="flex items-center gap-3">
            <HealthBadge />
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="gap-1.5 text-xs text-neutral-600 hover:text-neutral-900"
            >
              <LogOutIcon className="h-3.5 w-3.5" />
              Sign Out
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        {/* 404 Clean-Reset Notice Banner (using pinned primitives, no toast lib) */}
        {notice && (
          <Card className="mb-6 border-amber-200 bg-amber-50 shadow-2xs">
            <CardContent className="flex items-start justify-between gap-3 p-4">
              <div className="flex items-start gap-2.5">
                <InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                <div className="text-xs text-amber-800">
                  <p className="font-medium">Organization Reset Notice</p>
                  <p className="mt-0.5">{notice}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setNotice(null)}
                className="cursor-pointer text-amber-600 transition hover:text-amber-800"
                aria-label="Dismiss notice"
              >
                <XIcon className="h-4 w-4" />
              </button>
            </CardContent>
          </Card>
        )}

        <div className="space-y-6">
          <div className="border-b border-neutral-200 pb-4">
            <h1 className="text-xl font-semibold tracking-tight text-neutral-900">
              Workspaces Overview
            </h1>
            <p className="mt-1 text-xs text-neutral-500">
              Manage your project workspaces scoped to the currently selected organization.
            </p>
          </div>

          <WorkspaceForm
            selectedOrgId={selectedOrgId}
            onOrg404Reset={handleOrg404Reset}
          />
        </div>
      </main>
    </div>
  );
}
