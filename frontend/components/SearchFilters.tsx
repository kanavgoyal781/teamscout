"use client";

import type { PrefMode, SearchParams } from "../lib/types";

type SearchFiltersProps = {
  params: SearchParams;
  onChange: (next: SearchParams) => void;
  disabled?: boolean;
};

function PrefToggle({
  value,
  onChange,
  disabled,
  label,
}: {
  value: PrefMode;
  onChange: (v: PrefMode) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <label className="pref-toggle" title={`${label}: filter excludes; boost reorders`}>
      <span className="meta" style={{ margin: 0 }}>
        {label}
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as PrefMode)}
        aria-label={`${label} mode`}
      >
        <option value="soft">Boost</option>
        <option value="hard">Filter</option>
      </select>
    </label>
  );
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
  >
> = {
  remote_mode: "any",
  remote_mode_pref: "soft",
  employment_type: "any",
  employment_type_pref: "soft",
  date_window: "month",
  seniority: "any",
  seniority_pref: "soft",
  min_salary_pref: "soft",
  use_expand: true,
};

export function defaultSearchParams(): SearchParams {
  return { ...DEFAULTS, min_salary: null };
}

export default function SearchFilters({ params, onChange, disabled }: SearchFiltersProps) {
  const p = { ...DEFAULTS, ...params };

  function set<K extends keyof SearchParams>(key: K, value: SearchParams[K]) {
    onChange({ ...p, [key]: value });
  }

  return (
    <div className="search-filters" data-testid="search-filters">
      <h3 style={{ margin: "16px 0 8px", fontSize: "0.95rem" }}>Search options</h3>
      <div className="field-grid search-filters-grid">
        <label>
          Remote
          <select
            value={p.remote_mode}
            disabled={disabled}
            onChange={(e) => set("remote_mode", e.target.value as SearchParams["remote_mode"])}
            aria-label="Remote mode"
          >
            <option value="any">Any</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">Onsite</option>
          </select>
        </label>
        <PrefToggle
          label="Remote pref"
          value={p.remote_mode_pref}
          disabled={disabled}
          onChange={(v) => set("remote_mode_pref", v)}
        />

        <label>
          Employment
          <select
            value={p.employment_type}
            disabled={disabled}
            onChange={(e) => set("employment_type", e.target.value as SearchParams["employment_type"])}
            aria-label="Employment type"
          >
            <option value="any">Any</option>
            <option value="fulltime">Full-time</option>
            <option value="contractor">Contractor</option>
          </select>
        </label>
        <PrefToggle
          label="Employment pref"
          value={p.employment_type_pref}
          disabled={disabled}
          onChange={(v) => set("employment_type_pref", v)}
        />

        <label>
          Posted within
          <select
            value={p.date_window}
            disabled={disabled}
            onChange={(e) => set("date_window", e.target.value as SearchParams["date_window"])}
            aria-label="Date window"
          >
            <option value="day">24 hours</option>
            <option value="3days">3 days</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
          </select>
        </label>

        <label>
          Seniority
          <select
            value={p.seniority}
            disabled={disabled}
            onChange={(e) => set("seniority", e.target.value as SearchParams["seniority"])}
            aria-label="Seniority"
          >
            <option value="any">Any</option>
            <option value="intern">Intern</option>
            <option value="junior">Junior</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
            <option value="lead">Lead+</option>
          </select>
        </label>
        <PrefToggle
          label="Seniority pref"
          value={p.seniority_pref}
          disabled={disabled}
          onChange={(v) => set("seniority_pref", v)}
        />

        <label>
          Min salary (USD)
          <input
            type="number"
            min={0}
            step={5000}
            placeholder="e.g. 120000"
            disabled={disabled}
            value={p.min_salary ?? ""}
            onChange={(e) => {
              const raw = e.target.value;
              set("min_salary", raw === "" ? null : Number(raw));
            }}
            aria-label="Minimum salary"
          />
        </label>
        <PrefToggle
          label="Salary pref"
          value={p.min_salary_pref}
          disabled={disabled}
          onChange={(v) => set("min_salary_pref", v)}
        />

        <label className="full-width" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="checkbox"
            checked={p.use_expand !== false}
            disabled={disabled}
            onChange={(e) => set("use_expand", e.target.checked)}
            aria-label="Expand queries with LLM"
          />
          <span>Expand queries (LLM · 3–5 variants)</span>
        </label>
      </div>
      <p className="meta" style={{ marginTop: 8 }}>
        Filter excludes non-matches. Boost reorders matches higher. Jobs without salary are kept and flagged.
      </p>
    </div>
  );
}
