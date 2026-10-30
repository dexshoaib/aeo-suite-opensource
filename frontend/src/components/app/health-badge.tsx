"use client";

import { useEffect, useState } from "react";
import client from "@/lib/api/client";

interface HealthStatus {
  status: string;
  database: string;
}

export function HealthBadge() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function checkHealth() {
      try {
        const { data, response } = await client.GET("/api/v1/health/");
        if (mounted) {
          if (response.ok && data) {
            setHealth(data as unknown as HealthStatus);
          } else {
            setHealth({ status: "error", database: "error" });
          }
          setLoading(false);
        }
      } catch {
        if (mounted) {
          setHealth({ status: "unreachable", database: "unreachable" });
          setLoading(false);
        }
      }
    }

    checkHealth();
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="inline-flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-xs text-neutral-500">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-neutral-400" />
        Checking system...
      </div>
    );
  }

  const isHealthy = health?.status === "ok" && health?.database === "ok";

  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
        isHealthy
          ? "border-green-200 bg-green-50 text-green-700"
          : "border-red-200 bg-red-50 text-red-700"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isHealthy ? "bg-green-600" : "bg-red-600"
        }`}
      />
      {isHealthy ? "System Healthy" : "System Degraded"}
    </div>
  );
}
