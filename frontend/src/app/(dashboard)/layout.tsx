import { headers } from "next/headers";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

interface SessionResponse {
  status?: number;
  data?: {
    user?: {
      id: string;
      email: string;
      display?: string;
    };
  };
  meta?: {
    is_authenticated?: boolean;
  };
}

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const backendOrigin = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
  const incomingHeaders = await headers();
  const cookie = incomingHeaders.get("cookie") ?? "";

  let isAuthenticated = false;

  try {
    const res = await fetch(`${backendOrigin}/api/auth/browser/v1/auth/session`, {
      method: "GET",
      headers: {
        cookie,
        Accept: "application/json",
      },
      cache: "no-store",
    });

    if (res.ok) {
      const data = (await res.json()) as SessionResponse;
      if (data?.meta?.is_authenticated && data?.data?.user) {
        isAuthenticated = true;
      }
    }
  } catch {
    isAuthenticated = false;
  }

  if (!isAuthenticated) {
    redirect("/login");
  }

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      {children}
    </div>
  );
}
