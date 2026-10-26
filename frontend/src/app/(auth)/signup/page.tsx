"use client";

import { useState } from "react";
import Link from "next/link";
import { signup } from "@/lib/api/auth";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const res = await signup({ email, password });
      if (res.success) {
        setSuccess(true);
        setSubmitting(false);
      } else {
        const errorMsg =
          res.errors && res.errors.length > 0
            ? res.errors.map((err) => err.message).join(" ")
            : "Sign up failed. Please check your information.";
        setError(errorMsg);
        setSubmitting(false);
      }
    } catch {
      setError("An unexpected error occurred. Please try again.");
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
        <div className="rounded-lg border border-neutral-200 bg-white p-6 text-center shadow-xs">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-700">
            ✓
          </div>
          <h2 className="mt-4 text-xl font-semibold text-neutral-900">
            Account created
          </h2>
          <p className="mt-2 text-sm text-neutral-600">
            If email verification is required, please check your terminal or email for the verification key.
          </p>
          <div className="mt-6 flex flex-col gap-3">
            <Link
              href="/verify-email"
              className="rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800"
            >
              Enter Verification Key
            </Link>
            <Link
              href="/login"
              className="rounded-md border border-neutral-300 py-2 text-sm font-medium text-neutral-700 transition hover:bg-neutral-50"
            >
              Sign In
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">
          Create your account
        </h1>
        <p className="mt-2 text-sm text-neutral-600">
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-medium text-neutral-900 underline underline-offset-4 hover:text-neutral-700"
          >
            Sign in
          </Link>
        </p>
      </div>

      <div className="mt-8 rounded-lg border border-neutral-200 bg-white p-6 shadow-xs">
        <form onSubmit={handleSubmit} className="space-y-4">
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
              htmlFor="email"
              className="block text-sm font-medium text-neutral-700"
            >
              Email address
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900 placeholder-neutral-400 focus:border-neutral-900 focus:outline-none"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-neutral-700"
            >
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900 placeholder-neutral-400 focus:border-neutral-900 focus:outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-neutral-900 py-2.5 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:opacity-50"
          >
            {submitting ? "Creating account..." : "Create Account"}
          </button>
        </form>
      </div>
    </main>
  );
}
