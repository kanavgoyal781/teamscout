import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactElement } from "react";

const fetchPublicStats = vi.fn();

vi.mock("../../lib/api", () => ({
  fetchPublicStats: (...args: unknown[]) => fetchPublicStats(...args),
}));

vi.mock("framer-motion", async () => {
  const actual = await vi.importActual<typeof import("framer-motion")>("framer-motion");
  return { ...actual, useReducedMotion: () => true };
});

import AboutStats from "./AboutStats";

function wrap(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("AboutStats", () => {
  beforeEach(() => {
    fetchPublicStats.mockReset();
  });

  it("shows loading skeletons with aria-busy", () => {
    fetchPublicStats.mockReturnValue(new Promise(() => {}));
    wrap(<AboutStats />);
    expect(screen.getByTestId("about-stats")).toHaveAttribute("aria-busy", "true");
  });

  it("shows error empty state", async () => {
    fetchPublicStats.mockRejectedValue(new Error("network"));
    wrap(<AboutStats />);
    expect(await screen.findByRole("status", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText(/Live stats unavailable/i)).toBeInTheDocument();
  });

  it("renders all chips including null median dash and cost decimals", async () => {
    fetchPublicStats.mockResolvedValue({
      jobs_ranked_total: 42,
      resumes_parsed_total: 17,
      teams_discovered_total: 9,
      median_rank_latency_ms: null,
      total_llm_cost_usd: 1.2345,
    });
    wrap(<AboutStats />);
    await waitFor(() => {
      expect(screen.getByTestId("stat-jobs-ranked")).toHaveTextContent("42");
    });
    expect(screen.getByTestId("stat-resumes-parsed")).toHaveTextContent("17");
    expect(screen.getByTestId("stat-teams-found")).toHaveTextContent("9");
    expect(screen.getByTestId("stat-median-rank-ms")).toHaveTextContent("—");
    expect(screen.getByTestId("stat-llm-cost")).toHaveTextContent("1.2345");
    expect(screen.getByText(/median rerank ms/i)).toBeInTheDocument();
  });
});
