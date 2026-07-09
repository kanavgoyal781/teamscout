"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";

import { fetchHealth } from "../lib/api";
import { HEALTH_ENV_HINTS } from "../lib/types";
import { queryKeys } from "../lib/query";

const OPTIONAL_SERVICES = new Set(["google_drive"]);

/** Product labels — never surface vendor names (e.g. Sumble) to operators. */
const SERVICE_LABELS: Record<string, string> = {
  llm: "LLM",
  embeddings: "embeddings",
  jobs_api: "jobs API",
  sumble: "hiring team lookup",
  google_drive: "Google Drive",
};

function formatService(name: string): string {
  return SERVICE_LABELS[name] ?? name.replace(/_/g, " ");
}

function envHint(service: string, status: string): string {
  const keys = HEALTH_ENV_HINTS[service];
  if (status === "missing" && keys?.length) {
    return `${formatService(service)} missing (${keys.join(", ")})`;
  }
  return `${formatService(service)} ${status}`;
}

export default function HealthBanner() {
  const [dismissed, setDismissed] = useState(false);

  const { data: health, error, isFetched, isError, isPending } = useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    // Poll handles blips; avoid multi-second retry delay before degraded banner
    retry: false,
  });

  // No flash while loading — hide until first fetch settles
  if (!isFetched && isPending) {
    return null;
  }
  if (!isFetched && !isError) {
    return null;
  }

  if (dismissed) {
    return null;
  }

  const loadError = error instanceof Error ? error.message : error ? String(error) : null;
  const optional = new Set(health?.optional_checks ?? Array.from(OPTIONAL_SERVICES));
  const degraded =
    loadError !== null ||
    health === null ||
    health === undefined ||
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
      if (optional.has(service)) continue;
      if (status === "missing" || status === "failing") {
        problems.push(envHint(service, status));
      }
    }
  }
  if (!health && !loadError) {
    problems.push("health status unknown");
  }

  return (
    <div role="alert" className="health-banner" data-testid="health-banner">
      <div>
        <strong>TeamScout is degraded.</strong>{" "}
        {problems.length > 0 ? problems.join(" · ") : "Configuration incomplete."}
      </div>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss health banner"
        title="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
}
