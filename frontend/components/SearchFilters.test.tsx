import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchWorkspace: async () => ({
    workspace_id: "w1",
    ttl_days: 7,
    prefs: { filter_hint_dismissed: true },
  }),
  patchWorkspacePrefs: async () => ({
    workspace_id: "w1",
    ttl_days: 7,
    prefs: { filter_hint_dismissed: true },
  }),
}));

import SearchFilters, { defaultSearchParams } from "./SearchFilters";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("SearchFilters labels", () => {
  it("shows Must have and Prefer instead of Filter/Boost", async () => {
    wrap(<SearchFilters params={defaultSearchParams()} onChange={() => {}} />);
    expect(await screen.findByText("Must have removes jobs that don't match", { exact: false })).toBeInTheDocument();
    const options = screen.getAllByRole("option", { name: "Prefer" });
    expect(options.length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "Must have" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("option", { name: "Filter" })).toBeNull();
    expect(screen.queryByRole("option", { name: "Boost" })).toBeNull();
  });
});
