import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SearchFilters, {
  buildSearchSummary,
  defaultSearchParams,
  employmentSeniorityConflict,
  parseCountryFromProfile,
  sanitizeSearchParams,
} from "./SearchFilters";
import type { SearchParams } from "../../lib/types";

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

vi.mock("../../lib/api", () => ({
  fetchWorkspace: vi.fn(async () => ({
    workspace_id: "w",
    ttl_days: 7,
    prefs: { filter_hint_dismissed: true },
  })),
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
    const params = {
      ...defaultSearchParams(),
      employment_type: "any" as const,
      seniority: "intern" as const,
      seniority_pref: "soft" as const,
    };
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

  it("sanitizeSearchParams clears Full-time + Intern conflict", () => {
    expect(employmentSeniorityConflict({ employment_type: "fulltime", seniority: "intern" })).toBe(true);
    const cleaned = sanitizeSearchParams({
      ...defaultSearchParams(),
      employment_type: "fulltime",
      employment_type_pref: "hard",
      seniority: "intern",
      seniority_pref: "soft",
    });
    expect(cleaned.seniority).toBe("any");
    expect(cleaned.employment_type).toBe("fulltime");
    expect(buildSearchSummary(cleaned, { title: "Data Scientist" })).not.toMatch(/intern/i);
  });

  it("selecting Intern clears Full-time employment", () => {
    const onChange = vi.fn();
    wrap(
      <SearchFilters
        params={{
          ...defaultSearchParams(),
          employment_type: "fulltime",
          employment_type_pref: "hard",
          seniority: "any",
        }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByTestId("filter-seniority-value"), { target: { value: "intern" } });
    const next = onChange.mock.calls.at(-1)[0] as SearchParams;
    expect(next.seniority).toBe("intern");
    expect(next.employment_type).toBe("any");
  });

  it("selecting Full-time clears Intern seniority", () => {
    const onChange = vi.fn();
    wrap(
      <SearchFilters
        params={{
          ...defaultSearchParams(),
          employment_type: "any",
          seniority: "intern",
          seniority_pref: "soft",
        }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByTestId("filter-employment-value"), { target: { value: "fulltime" } });
    const next = onChange.mock.calls.at(-1)[0] as SearchParams;
    expect(next.employment_type).toBe("fulltime");
    expect(next.seniority).toBe("any");
  });

  it("summary never shows intern with fulltime after sanitize", () => {
    const s = buildSearchSummary(
      {
        employment_type: "fulltime",
        employment_type_pref: "hard",
        seniority: "intern",
        seniority_pref: "soft",
        location_country: "US",
        location_country_pref: "hard",
        date_window: "month",
      },
      { title: "Data Scientist" },
    );
    expect(s).toMatch(/Full-time \(require\)/);
    expect(s).not.toMatch(/intern/i);
  });

  it("layout: worldwide nests under location; expand and summary present", () => {
    wrap(
      <SearchFilters
        params={{
          ...defaultSearchParams("United States"),
          location_country: "US",
          location_country_pref: "hard",
          include_worldwide_remote: true,
          use_expand: true,
        }}
        onChange={vi.fn()}
        profileTitle="Data Scientist"
      />,
    );
    expect(screen.getByTestId("filter-location")).toBeTruthy();
    expect(screen.getByTestId("filter-worldwide-row")).toBeTruthy();
    expect(screen.getByTestId("filter-expand-row")).toBeTruthy();
    expect(screen.getByTestId("filter-expand")).toBeChecked();
    expect(screen.getByTestId("search-summary").textContent).toMatch(/Searching: Data Scientist/);
    expect(screen.getByTestId("search-summary").textContent).toMatch(/United States \(require\)/);
    expect(screen.getByTestId("filter-location-mode")).toBeTruthy();
    expect(screen.queryByTestId("filter-seniority-mode")).toBeNull();
  });
});
