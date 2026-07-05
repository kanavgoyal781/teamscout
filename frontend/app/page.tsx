"use client";

import { useState } from "react";

import AppShell from "../components/AppShell";
import JobResultsList from "../components/JobResultsList";
import ResumeWizard from "../components/ResumeWizard";
import { useJobTeam } from "../hooks/useJobTeam";
import type { RankedJob } from "../lib/api";

type Toast = { kind: "error" | "info"; message: string } | null;

export default function HomePage() {
  const [results, setResults] = useState<RankedJob[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast>(null);

  const {
    getTeamState,
    hydrateJobTeam,
    handleExtractTeam,
    handleFindTeam,
    handleRevealEmail,
    resetTeams,
  } = useJobTeam(searchId);

  function onToast(next: Toast) {
    setToast(next);
  }

  return (
    <AppShell
      title="Resume upload, job search, and team discovery"
      lede="Upload a resume, confirm your searchable profile, rank live jobs, then extract hiring teams and reveal contact emails via Sumble."
      toast={toast}
    >
      <ResumeWizard
        onToast={onToast}
        onSearchStart={() => {
          setResults([]);
          setSearchId(null);
          resetTeams();
        }}
        onSearchComplete={(nextResults, nextSearchId) => {
          setResults(nextResults);
          setSearchId(nextSearchId);
        }}
      />

      <JobResultsList
        results={results}
        getTeamState={getTeamState}
        onHydrate={(jobId) =>
          hydrateJobTeam(jobId, (kind, message) => onToast({ kind, message }))
        }
        onExtract={(jobId) => handleExtractTeam(jobId, (kind, message) => onToast({ kind, message }))}
        onFindTeam={(jobId) => handleFindTeam(jobId, (kind, message) => onToast({ kind, message }))}
        onRevealEmail={(jobId, contact, confirm) =>
          handleRevealEmail(jobId, contact, confirm, (kind, message) => onToast({ kind, message }))
        }
      />
    </AppShell>
  );
}