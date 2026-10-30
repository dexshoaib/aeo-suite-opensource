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
import { PlusIcon } from "lucide-react";

export interface CreatedOrg {
  id: string;
  name: string;
}

interface OrgFormProps {
  onSuccess: (org: CreatedOrg) => void;
  triggerLabel?: string;
  className?: string;
}

export function OrgForm({
  onSuccess,
  triggerLabel = "New Organization",
  className,
}: OrgFormProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const { data, response, error: err } = await client.POST(
        "/api/v1/organizations/",
        {
          body: { name: name.trim() } as unknown as { name: string; readonly id: string; readonly created_at: string; readonly updated_at: string },
        }
      );

      if (response.ok && data) {
        setName("");
        setOpen(false);
        onSuccess({ id: (data as { id: string; name: string }).id, name: (data as { id: string; name: string }).name });
      } else {
        const errObj = err as unknown as { name?: string[] } | undefined;
        const msg = errObj?.name?.[0] ?? "Failed to create organization.";
        setError(msg);
      }
    } catch {
      setError("An unexpected error occurred while creating the organization.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        className={
          className ??
          "inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-800 shadow-2xs transition hover:bg-neutral-50"
        }
      >
        <PlusIcon className="h-3.5 w-3.5" />
        {triggerLabel}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create Organization</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          {error && (
            <div
              role="alert"
              className="rounded-md border border-red-200 bg-red-50 p-2.5 text-xs text-red-700"
            >
              {error}
            </div>
          )}
          <div className="space-y-1.5">
            <label
              htmlFor="org-name"
              className="text-xs font-medium text-neutral-700"
            >
              Organization Name
            </label>
            <Input
              id="org-name"
              type="text"
              required
              placeholder="e.g. Acme Corp"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={submitting}
              autoFocus
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={submitting || !name.trim()}>
              {submitting ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
