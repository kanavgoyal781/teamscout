"use client";

import { FormEvent } from "react";

import type { IntentSearchRequest, LibraryResume } from "../lib/types";
import EmptyState from "./ui/EmptyState";

type IntentSearchPanelProps = {
  resumes: LibraryResume[];
  role: string;
  years: string;
  location: string;
  remotePreference: IntentSearchRequest["remote_preference"];
  searching: boolean;
  onRoleChange: (value: string) => void;
  onYearsChange: (value: string) => void;
  onLocationChange: (value: string) => void;
  onRemotePreferenceChange: (value: IntentSearchRequest["remote_preference"]) => void;
  onSearch: (event: FormEvent<HTMLFormElement>) => void;
};

export default function IntentSearchPanel({
  resumes,
  role,
  years,
  location,
  remotePreference,
  searching,
  onRoleChange,
  onYearsChange,
  onLocationChange,
  onRemotePreferenceChange,
  onSearch,
}: IntentSearchPanelProps) {
  return (
    <section className="panel" data-testid="intent-search">
      <h2>2. Job intent search</h2>
      <form className="field-grid" onSubmit={onSearch}>
        <label>
          Desired role
          <input
            value={role}
            onChange={(event) => onRoleChange(event.target.value)}
            required
            aria-label="Desired role"
            placeholder="e.g. Staff Backend Engineer"
          />
        </label>
        <label>
          Years of experience
          <input
            value={years}
            onChange={(event) => onYearsChange(event.target.value)}
            type="number"
            min="0"
            step="0.5"
            className="font-num"
            aria-label="Years of experience"
          />
        </label>
        <label>
          Location
          <input
            value={location}
            onChange={(event) => onLocationChange(event.target.value)}
            aria-label="Location"
            placeholder="City or region"
          />
        </label>
        <label>
          Remote preference
          <select
            value={remotePreference}
            onChange={(event) =>
              onRemotePreferenceChange(event.target.value as IntentSearchRequest["remote_preference"])
            }
            aria-label="Remote preference"
          >
            <option value="any">Any</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </select>
        </label>
        <div className="actions full-width">
          <button
            type="submit"
            className="primary"
            disabled={searching || resumes.length === 0}
            data-testid="intent-search-submit"
          >
            {searching ? "Searching & ranking…" : "Search jobs by intent"}
          </button>
        </div>
      </form>
      {resumes.length === 0 ? (
        <div style={{ marginTop: 12 }}>
          <EmptyState instruction="Add resumes to the library before searching by intent." />
        </div>
      ) : null}
    </section>
  );
}
