"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { verifyEmail } from "@/lib/api/auth";

function VerifyEmailForm() {
  const searchParams = useSearchParams();
  const urlKey = searchParams.get("key") ?? "";

  const [customKey, setCustomKey] = useState<string | null>(null);
  const key = customKey !== null ? customKey : urlKey;

  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleVerify = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!key.trim()) {
      setError("Please provide a verification key.");
      return;
    }

    setError(null);
    setSubmitting(true);

    try {
      const res = await verifyEmail(key.trim());
      if (res.success) {
        setSuccess(true);
      } else {
        const errorMsg =
          res.errors && res.errors.length > 0
            ? res.errors.map((err) => err.message).join(" ")
            : "Invalid or expired verification key.";
        setError(errorMsg);
      }
    } catch {
      setError("An unexpected error occurred during verification.");
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="rounded-lg border border-neutral-200 bg-white p-6 text-center shadow-xs">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-700">
          ✓
        </div>
        <h2 className="mt-4 text-xl font-semibold text-neutral-900">
          Email verified
        </h2>
        <p className="mt-2 text-sm text-neutral-600">
          Your email address has been successfully verified. You can now sign in to your account.
        </p>
        <div className="mt-6">
          <Link
            href="/login"
            className="block w-full rounded-md bg-neutral-900 py-2.5 text-center text-sm font-medium text-white transition hover:bg-neutral-800"
          >
            Proceed to Sign In
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-6 shadow-xs">
      <form onSubmit={handleVerify} className="space-y-4">
        {error && (
          <div
            role="alert"
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        <div>
          <label
            htmlFor="key"
            className="block text-sm font-medium text-neutral-700"
          >
            Verification key
          </label>
          <input
            id="key"
            name="key"
            type="text"
            required
            value={key}
            onChange={(e) => setCustomKey(e.target.value)}
            className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900 placeholder-neutral-400 focus:border-neutral-900 focus:outline-none"
            placeholder="Paste verification key from email"
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:opacity-50"
        >
          {submitting ? "Verifying..." : "Confirm Verification"}
        </button>
      </form>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Verify your email
        </h1>
        <p className="mt-2 text-sm text-neutral-600">
          Enter the verification key sent to your email address.
        </p>
      </div>

      <Suspense
        fallback={
          <div className="rounded-lg border border-neutral-200 bg-white p-6 text-center text-sm text-neutral-500">
            Loading verification form...
          </div>
        }
      >
        <VerifyEmailForm />
      </Suspense>
    </main>
  );
}
