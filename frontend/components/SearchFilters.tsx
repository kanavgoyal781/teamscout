"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchWorkspace, patchWorkspacePrefs } from "../lib/api";
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
    <label className="pref-toggle" title={`${label}: Must have removes non-matches; Prefer ranks matches higher`}>
      <span className="meta" style={{ margin: 0 }}>
        {label}
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as PrefMode)}
        aria-label={`${label} mode`}
      >
        <option value="soft">Prefer</option>
        <option value="hard">Must have</option>
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

  function set<K extends keyof SearchParams>(key: K, value: SearchParams[K]) {
    onChange({ ...p, [key]: value });
  }

  return (
    <div className="search-filters" data-testid="search-filters">
      <h3 style={{ margin: "16px 0 8px", fontSize: "0.95rem" }}>Search options</h3>
      {showHint ? (
        <div className="filter-hint" data-testid="filter-prefer-hint" role="note">
          <p>
            <strong>Must have</strong> removes jobs that do not match. <strong>Prefer</strong> keeps
            all jobs and ranks matching ones higher. Example: set Remote to Remote + Prefer to boost
            remote roles without hiding hybrid or onsite.
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
      <p className="meta" style={{ marginBottom: 8 }}>
        Must have removes jobs that don&apos;t match. Prefer keeps all jobs and ranks matching ones
        higher.
      </p>
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
          label="Remote mode"
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
          label="Employment mode"
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
          label="Seniority mode"
          value={p.seniority_pref}
          disabled={disabled}
          onChange={(v) => set("seniority_pref", v)}
        />

        <label>
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
          />
        </label>
        <PrefToggle
          label="Salary mode"
          value={p.min_salary_pref}
          disabled={disabled}
          onChange={(v) => set("min_salary_pref", v)}
        />

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
    </div>
  );
}
