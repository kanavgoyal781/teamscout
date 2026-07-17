"use client";

import { useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchWorkspace, patchWorkspacePrefs } from "../../lib/api";
import type { PrefMode, SearchParams } from "../../lib/types";

type SearchFiltersProps = {
  params: SearchParams;
  onChange: (next: SearchParams) => void;
  disabled?: boolean;
  /** Profile location free-text — used to prefill country once. */
  profileLocation?: string;
  profileTitle?: string;
};

const COUNTRIES: { code: string; label: string }[] = [
  { code: "", label: "Any" },
  { code: "US", label: "United States" },
  { code: "CA", label: "Canada" },
  { code: "GB", label: "United Kingdom" },
  { code: "IN", label: "India" },
  { code: "DE", label: "Germany" },
  { code: "FR", label: "France" },
  { code: "NL", label: "Netherlands" },
  { code: "IE", label: "Ireland" },
  { code: "AU", label: "Australia" },
  { code: "SG", label: "Singapore" },
  { code: "IL", label: "Israel" },
  { code: "BR", label: "Brazil" },
  { code: "MX", label: "Mexico" },
  { code: "ES", label: "Spain" },
  { code: "PT", label: "Portugal" },
  { code: "PL", label: "Poland" },
  { code: "SE", label: "Sweden" },
  { code: "CH", label: "Switzerland" },
  { code: "JP", label: "Japan" },
  { code: "KR", label: "South Korea" },
];

/** Client-side mirror of backend geo.parse_country for prefill only. */
export function parseCountryFromProfile(text: string | undefined | null): string {
  const raw = (text || "").trim();
  if (!raw) return "";
  const low = raw.toLowerCase();
  const codes: Record<string, string> = {
    us: "US", usa: "US", "u.s.": "US", "u.s.a.": "US",
    uk: "GB", gb: "GB", ca: "CA", in: "IN", de: "DE", fr: "FR",
  };
  if (codes[low]) return codes[low];
  if (/\b(united states|u\.s\.a\.?|usa|\bu\.s\b)\b/i.test(raw)) return "US";
  if (/\b(united kingdom|great britain|\buk\b|england)\b/i.test(raw)) return "GB";
  if (/\b(canada)\b/i.test(low)) return "CA";
  if (/\b(india|bangalore|bengaluru|hyderabad|gurugram|gurgaon|mumbai|delhi|pune)\b/i.test(low))
    return "IN";
  if (/\b(germany|berlin|munich)\b/i.test(low)) return "DE";
  if (/\b(remote\s*us|us\s*remote)\b/i.test(low)) return "US";
  if (/,\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b/i.test(raw))
    return "US";
  if (/\b(new york|san francisco|seattle|austin|boston|chicago|denver|atlanta|los angeles|bay area|silicon valley)\b/i.test(low))
    return "US";
  return "";
}

const DEFAULTS: Required<
  Pick<
    SearchParams,
    | "remote_mode"
    | "remote_mode_pref"
    | "employment_type"
    | "employment_type_pref"
    | "date_window"
    | "seniority"
    | "seniority_pref"
    | "min_salary_pref"
    | "use_expand"
    | "location_country_pref"
    | "include_worldwide_remote"
  >
> = {
  remote_mode: "any",
  remote_mode_pref: "soft",
  employment_type: "fulltime",
  employment_type_pref: "hard",
  date_window: "month",
  seniority: "any",
  seniority_pref: "soft",
  min_salary_pref: "soft",
  use_expand: true,
  location_country_pref: "hard",
  include_worldwide_remote: true,
};

export function defaultSearchParams(profileLocation?: string): SearchParams {
  const country = parseCountryFromProfile(profileLocation);
  return {
    ...DEFAULTS,
    min_salary: null,
    location_country: country || null,
    // Seniority must never default to Intern or any level — always Any unless user sets it.
    seniority: "any",
    seniority_pref: "soft",
  };
}

function ModeToggle({
  value,
  onChange,
  disabled,
  testId,
}: {
  value: PrefMode;
  onChange: (v: PrefMode) => void;
  disabled?: boolean;
  testId?: string;
}) {
  return (
    <div className="mode-seg" role="group" aria-label="Filter strength" data-testid={testId}>
      <button
        type="button"
        className={value === "hard" ? "mode-seg-active" : ""}
        disabled={disabled}
        onClick={() => onChange("hard")}
        data-testid={testId ? `${testId}-require` : undefined}
      >
        Require
      </button>
      <button
        type="button"
        className={value === "soft" ? "mode-seg-active" : ""}
        disabled={disabled}
        onClick={() => onChange("soft")}
        data-testid={testId ? `${testId}-prefer` : undefined}
      >
        Prefer
      </button>
    </div>
  );
}

const COUNTRY_LABEL: Record<string, string> = Object.fromEntries(
  COUNTRIES.filter((c) => c.code).map((c) => [c.code, c.label]),
);

export function buildSearchSummary(
  params: SearchParams,
  opts?: { title?: string },
): string {
  const p = { ...DEFAULTS, ...params };
  const bits: string[] = [];
  const title = (opts?.title || "").trim();
  if (title) bits.push(title);
  const loc = (p.location_country || "").trim().toUpperCase();
  if (loc) {
    const mode = p.location_country_pref === "hard" ? "require" : "prefer";
    bits.push(`${COUNTRY_LABEL[loc] || loc} (${mode})`);
    if (p.include_worldwide_remote) bits.push("worldwide remote ok");
  }
  if (p.remote_mode && p.remote_mode !== "any") {
    bits.push(`${p.remote_mode} (${p.remote_mode_pref === "hard" ? "require" : "prefer"})`);
  }
  if (p.employment_type && p.employment_type !== "any") {
    const emp = p.employment_type === "fulltime" ? "Full-time" : "Contractor";
    bits.push(`${emp} (${p.employment_type_pref === "hard" ? "require" : "prefer"})`);
  }
  if (p.seniority && p.seniority !== "any") {
    bits.push(`${p.seniority} (${p.seniority_pref === "hard" ? "require" : "prefer"})`);
  }
  if (p.min_salary != null && p.min_salary > 0) {
    bits.push(`≥$${p.min_salary.toLocaleString()} (${p.min_salary_pref === "hard" ? "require" : "prefer"})`);
  }
  const windowLabel: Record<string, string> = {
    day: "posted last 24h",
    "3days": "posted last 3 days",
    week: "posted this week",
    month: "posted this month",
  };
  bits.push(windowLabel[p.date_window] || "posted this month");
  return `Searching: ${bits.join(" · ")}`;
}

export default function SearchFilters({
  params,
  onChange,
  disabled,
  profileLocation,
  profileTitle,
}: SearchFiltersProps) {
  const p = { ...DEFAULTS, min_salary: null as number | null, location_country: null as string | null, ...params };
  // Force seniority any if somehow corrupted (never silently Intern)
  if (!p.seniority || !["any", "intern", "junior", "mid", "senior", "lead"].includes(p.seniority)) {
    p.seniority = "any";
  }
  const qc = useQueryClient();
  const { data: workspace } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
    staleTime: 60_000,
  });
  const dismissMut = useMutation({
    mutationFn: () => patchWorkspacePrefs({ filter_hint_dismissed: true }),
    onSuccess: (data) => qc.setQueryData(["workspace"], data),
  });
  const showHint = workspace && workspace.prefs?.filter_hint_dismissed !== true;

  // Prefill country once from profile when empty
  useEffect(() => {
    if (params.location_country) return;
    const c = parseCountryFromProfile(profileLocation);
    if (c) onChange({ ...DEFAULTS, ...params, location_country: c, location_country_pref: "hard" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when profile location arrives
  }, [profileLocation]);

  function set<K extends keyof SearchParams>(key: K, value: SearchParams[K]) {
    const next = { ...p, [key]: value };
    // Setting value to Any hides mode — normalize prefs to soft defaults (irrelevant)
    if (key === "remote_mode" && value === "any") next.remote_mode_pref = "soft";
    if (key === "employment_type" && value === "any") next.employment_type_pref = "soft";
    if (key === "seniority" && value === "any") next.seniority_pref = "soft";
    if (key === "min_salary" && (value === null || value === undefined)) next.min_salary_pref = "soft";
    if (key === "location_country" && !value) next.location_country_pref = "hard";
    onChange(next);
  }

  const summary = useMemo(
    () => buildSearchSummary(p, { title: profileTitle }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [p.remote_mode, p.remote_mode_pref, p.employment_type, p.employment_type_pref, p.date_window, p.seniority, p.seniority_pref, p.min_salary, p.min_salary_pref, p.location_country, p.location_country_pref, p.include_worldwide_remote, profileTitle],
  );

  return (
    <div className="search-filters" data-testid="search-filters">
      <h3 style={{ margin: "16px 0 8px", fontSize: "0.95rem" }}>Search options</h3>
      {showHint ? (
        <div className="filter-hint" data-testid="filter-prefer-hint" role="note">
          <p>
            <strong>Require</strong> removes jobs that do not match. <strong>Prefer</strong> keeps
            all jobs and ranks matching ones higher. Mode toggles only appear when a value is set.
          </p>
          <button
            type="button"
            className="meta"
            onClick={() => dismissMut.mutate()}
            data-testid="filter-prefer-hint-dismiss"
          >
            Got it
          </button>
        </div>
      ) : null}

      <div className="filter-rows">
        <div className="filter-row" data-testid="filter-location">
          <label className="filter-value">
            Location
            <select
              value={p.location_country || ""}
              disabled={disabled}
              onChange={(e) => set("location_country", e.target.value || null)}
              aria-label="Location country"
              data-testid="filter-location-country"
            >
              {COUNTRIES.map((c) => (
                <option key={c.code || "any"} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          {p.location_country ? (
            <ModeToggle
              value={p.location_country_pref || "hard"}
              onChange={(v) => set("location_country_pref", v)}
              disabled={disabled}
              testId="filter-location-mode"
            />
          ) : null}
        </div>
        {p.location_country ? (
          <label className="checkbox-row filter-worldwide">
            <input
              type="checkbox"
              checked={Boolean(p.include_worldwide_remote)}
              disabled={disabled}
              onChange={(e) => set("include_worldwide_remote", e.target.checked)}
              data-testid="filter-worldwide"
            />
            Include worldwide remote
          </label>
        ) : null}

        <div className="filter-row" data-testid="filter-remote">
          <label className="filter-value">
            Remote
            <select
              value={p.remote_mode}
              disabled={disabled}
              onChange={(e) => set("remote_mode", e.target.value as SearchParams["remote_mode"])}
              aria-label="Remote mode"
              data-testid="filter-remote-value"
            >
              <option value="any">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">Onsite</option>
            </select>
          </label>
          {p.remote_mode !== "any" ? (
            <ModeToggle
              value={p.remote_mode_pref}
              onChange={(v) => set("remote_mode_pref", v)}
              disabled={disabled}
              testId="filter-remote-mode"
            />
          ) : null}
        </div>

        <div className="filter-row" data-testid="filter-employment">
          <label className="filter-value">
            Employment
            <select
              value={p.employment_type}
              disabled={disabled}
              onChange={(e) =>
                set("employment_type", e.target.value as SearchParams["employment_type"])
              }
              aria-label="Employment type"
              data-testid="filter-employment-value"
            >
              <option value="any">Any</option>
              <option value="fulltime">Full-time</option>
              <option value="contractor">Contractor</option>
            </select>
          </label>
          {p.employment_type !== "any" ? (
            <ModeToggle
              value={p.employment_type_pref}
              onChange={(v) => set("employment_type_pref", v)}
              disabled={disabled}
              testId="filter-employment-mode"
            />
          ) : null}
        </div>

        <div className="filter-row" data-testid="filter-date">
          <label className="filter-value">
            Posted within
            <select
              value={p.date_window}
              disabled={disabled}
              onChange={(e) => set("date_window", e.target.value as SearchParams["date_window"])}
              aria-label="Date window"
              data-testid="filter-date-value"
            >
              <option value="day">24 hours</option>
              <option value="3days">3 days</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
            </select>
          </label>
        </div>

        <div className="filter-row" data-testid="filter-seniority">
          <label className="filter-value">
            Seniority
            <select
              value={p.seniority === "any" || !p.seniority ? "any" : p.seniority}
              disabled={disabled}
              onChange={(e) => set("seniority", e.target.value as SearchParams["seniority"])}
              aria-label="Seniority"
              data-testid="filter-seniority-value"
            >
              <option value="any">Any</option>
              <option value="intern">Intern</option>
              <option value="junior">Junior</option>
              <option value="mid">Mid</option>
              <option value="senior">Senior</option>
              <option value="lead">Lead+</option>
            </select>
          </label>
          {p.seniority && p.seniority !== "any" ? (
            <ModeToggle
              value={p.seniority_pref}
              onChange={(v) => set("seniority_pref", v)}
              disabled={disabled}
              testId="filter-seniority-mode"
            />
          ) : null}
        </div>

        <div className="filter-row" data-testid="filter-salary">
          <label className="filter-value">
            Min salary (USD)
            <input
              type="number"
              min={0}
              step={1000}
              disabled={disabled}
              value={p.min_salary ?? ""}
              onChange={(e) =>
                set("min_salary", e.target.value === "" ? null : Number(e.target.value))
              }
              aria-label="Minimum salary"
              data-testid="filter-salary-value"
            />
          </label>
          {p.min_salary != null && p.min_salary > 0 ? (
            <ModeToggle
              value={p.min_salary_pref}
              onChange={(v) => set("min_salary_pref", v)}
              disabled={disabled}
              testId="filter-salary-mode"
            />
          ) : null}
        </div>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={Boolean(p.use_expand)}
            disabled={disabled}
            onChange={(e) => set("use_expand", e.target.checked)}
          />
          Expand search queries with AI
        </label>
      </div>

      <p className="search-summary" data-testid="search-summary" role="status">
        {summary}
      </p>
    </div>
  );
}
