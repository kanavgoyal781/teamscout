"use client";

import { useState } from "react";

import AppShell from "../components/AppShell";
import JobPasteTeamPanel from "../components/JobPasteTeamPanel";
import JobResultsList from "../components/JobResultsList";
import ResumeWizard from "../components/ResumeWizard";
import { useJobTeam } from "../hooks/useJobTeam";
import type { RankedJob } from "../lib/types";

export default function HomePage() {
  const [results, setResults] = useState<RankedJob[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [teamStepActive, setTeamStepActive] = useState(false);

  const {
    getTeamState,
    hydrateJobTeam,
    handleExtractTeam,
    handleFindTeam,
    handleRevealEmail,
    resetTeams,
  } = useJobTeam(searchId);

  return (
    <AppShell
      title="Resume → jobs → team"
      lede="Upload a resume and rank live jobs, or paste a job description to extract the hiring team and run Sumble — no job board required for the team path."
    >
      <ResumeWizard
        searching={searching}
        hasResults={results.length > 0}
        teamStepActive={teamStepActive}
        onSearchStart={() => {
          setResults([]);
          setSearchId(null);
          setSearching(true);
          setSearched(false);
          setTeamStepActive(false);
          resetTeams();
        }}
        onSearchComplete={(nextResults, nextSearchId) => {
          setResults(nextResults);
          setSearchId(nextSearchId);
          setSearching(false);
          setSearched(true);
        }}
        onSearchError={() => {
          setSearching(false);
          setSearched(false);
        }}
      />

      <JobResultsList
        results={results}
        loading={searching}
        searched={searched}
        getTeamState={getTeamState}
        onHydrate={(jobId) => hydrateJobTeam(jobId)}
        onExtract={(jobId) => handleExtractTeam(jobId)}
        onFindTeam={(jobId) => handleFindTeam(jobId)}
        onRevealEmail={(jobId, contact, confirm) =>
          handleRevealEmail(jobId, contact, confirm)
        }
        onTeamPanelOpenChange={setTeamStepActive}
      />

      <JobPasteTeamPanel
        getTeamState={getTeamState}
        onHydrate={(jobId) => hydrateJobTeam(jobId)}
        onExtract={(jobId) => handleExtractTeam(jobId)}
        onFindTeam={(jobId) => handleFindTeam(jobId)}
        onRevealEmail={(jobId, contact, confirm) =>
          handleRevealEmail(jobId, contact, confirm)
        }
        onTeamPanelOpenChange={setTeamStepActive}
      />
    </AppShell>
  );
}
