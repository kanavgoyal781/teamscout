"use client";

import { QueryClient } from "@tanstack/react-query";

/**
 * Credit-spending and irreversible mutations must never auto-retry.
 * Queries may retry once on transient network blips.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export const queryKeys = {
  health: ["health"] as const,
  stats: ["stats"] as const,
  library: ["library", "resumes"] as const,
  jobTeam: (jobId: string) => ["job-team", jobId] as const,
};
