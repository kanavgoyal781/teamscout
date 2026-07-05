"use client";

import { useEffect, useState } from "react";

type CheckStatus = "configured" | "missing" | "failing";

type HealthResponse = {
  ok: boolean;
  checks: Record<string, CheckStatus>;
  optional_checks?: string[];
  db?: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const OPTIONAL_SERVICES = new Set(["google_drive"]);

function formatService(name: string): string {
  return name.replace(/_/g, " ");
}

export default function HealthBanner() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
        const payload = (await response.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(payload);
          setLoadError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setHealth(null);
          setLoadError(error instanceof Error ? error.message : "Failed to reach backend");
        }
      } finally {
        if (!cancelled) {
          setLoaded(true);
        }
      }
    }

    loadHealth();
    const timer = window.setInterval(loadHealth, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (!loaded) {
    return null;
  }

  const optional = new Set(health?.optional_checks ?? Array.from(OPTIONAL_SERVICES));
  const degraded =
    loadError !== null ||
    health === null ||
    health.ok === false ||
    health.db === false;

  if (!degraded) {
    return null;
  }

  const problems: string[] = [];
  if (loadError) {
    problems.push(`backend unreachable (${loadError})`);
  }
  if (health?.db === false) {
    problems.push("database failing");
  }
  if (health?.checks) {
    for (const [service, status] of Object.entries(health.checks)) {
      if (optional.has(service)) {
        continue;
      }
      if (status === "missing" || status === "failing") {
        problems.push(`${formatService(service)} ${status}`);
      }
    }
  }
  if (health === null && !loadError) {
    problems.push("health status unknown");
  }

  return (
    <div
      role="alert"
      className="health-banner"
      data-testid="health-banner"
    >
      <strong>TeamScout is degraded.</strong>{" "}
      {problems.length > 0 ? problems.join(" · ") : "Configuration incomplete."}
    </div>
  );
}