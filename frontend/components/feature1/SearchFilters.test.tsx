import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchFilters, {
  buildSearchSummary,
  defaultSearchParams,
  parseCountryFromProfile,
} from "./SearchFilters";
import type { SearchParams } from "../../lib/types";

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

vi.mock("../../lib/api", () => ({
  fetchWorkspace: vi.fn(async () => ({ workspace_id: "w", ttl_days: 7, prefs: { filter_hint_dismissed: true } })),
  patchWorkspacePrefs: vi.fn(),
}));

describe("M29 SearchFilters", () => {
  it("defaults seniority to Any never Intern", () => {
    const d = defaultSearchParams("Seattle, WA");
    expect(d.seniority).toBe("any");
    expect(d.location_country).toBe("US");
    expect(d.location_country_pref).toBe("hard");
    expect(d.employment_type).toBe("fulltime");
    expect(d.employment_type_pref).toBe("hard");
  });

  it("parseCountryFromProfile handles US states and India cities", () => {
    expect(parseCountryFromProfile("Austin, TX")).toBe("US");
    expect(parseCountryFromProfile("Gurugram, India")).toBe("IN");
  });

  it("hides Require|Prefer when value is Any; shows when set", () => {
    const onChange = vi.fn();
    const params: SearchParams = {
      ...defaultSearchParams(),
      location_country: "US",
      location_country_pref: "hard",
      remote_mode: "any",
      seniority: "any",
    };
    wrap(<SearchFilters params={params} onChange={onChange} />);
    expect(screen.queryByTestId("filter-remote-mode")).toBeNull();
    expect(screen.queryByTestId("filter-seniority-mode")).toBeNull();
    // Location set → mode visible
    expect(screen.getByTestId("filter-location-mode")).toBeTruthy();
    expect(screen.getByTestId("filter-location-mode-require")).toBeTruthy();
  });

  it("summary line reflects require/prefer toggles", () => {
    const s = buildSearchSummary(
      {
        ...defaultSearchParams("United States"),
        employment_type: "fulltime",
        employment_type_pref: "hard",
        location_country: "US",
        location_country_pref: "hard",
        date_window: "month",
      },
      { title: "Data Scientist" },
    );
    expect(s).toMatch(/Searching: Data Scientist/);
    expect(s).toMatch(/United States \(require\)/);
    expect(s).toMatch(/Full-time \(require\)/);
    expect(s).toMatch(/posted this month/);
  });

  it("copy uses Require not Must have", () => {
    wrap(
      <SearchFilters
        params={{ ...defaultSearchParams(), location_country: "US", location_country_pref: "hard" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Must have/i)).toBeNull();
    expect(screen.getByTestId("filter-location-mode-require").textContent).toMatch(/Require/);
  });

  it("setting seniority to Any hides mode toggle", () => {
    const onChange = vi.fn();
    const params = { ...defaultSearchParams(), seniority: "intern" as const, seniority_pref: "hard" as const };
    const { rerender } = wrap(<SearchFilters params={params} onChange={onChange} />);
    expect(screen.getByTestId("filter-seniority-mode")).toBeTruthy();
    fireEvent.change(screen.getByTestId("filter-seniority-value"), { target: { value: "any" } });
    expect(onChange).toHaveBeenCalled();
    const next = onChange.mock.calls.at(-1)[0] as SearchParams;
    expect(next.seniority).toBe("any");
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SearchFilters params={next} onChange={onChange} />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("filter-seniority-mode")).toBeNull();
  });
});
