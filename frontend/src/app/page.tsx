"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSession, logout, type AuthUser } from "@/lib/api/auth";

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let mounted = true;
    getSession()
      .then((session) => {
        if (mounted) {
          setUser(session.isAuthenticated ? session.user : null);
          setLoading(false);
        }
      })
      .catch(() => {
        if (mounted) {
          setUser(null);
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleLogout = async () => {
    await logout();
    setUser(null);
  };

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">AEO Suite</h1>
        <p className="text-neutral-500">Checking session...</p>
      </main>
    );
  }

  if (user) {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">AEO Suite</h1>
          <p className="text-neutral-600">
            Signed in as <span className="font-medium text-neutral-900">{user.email}</span>
          </p>
        </div>
        <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-6 text-sm text-neutral-600">
          <p className="font-medium text-neutral-800">Session active</p>
          <p className="mt-1">
            The full dashboard shell with organizations and workspaces arrives in the next milestone.
          </p>
        </div>
        <div className="flex gap-4">
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-neutral-800"
          >
            Sign Out
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">AEO Suite</h1>
        <p className="text-neutral-600">
          AI answer engine optimization: audit, measure, fix, publish.
        </p>
      </div>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="rounded-md bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800"
        >
          Sign In
        </Link>
        <Link
          href="/signup"
          className="rounded-md border border-neutral-300 px-5 py-2.5 text-sm font-medium text-neutral-700 transition hover:bg-neutral-50"
        >
          Create Account
        </Link>
      </div>
    </main>
  );
}
