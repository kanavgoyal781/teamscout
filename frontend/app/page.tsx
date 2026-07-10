"use client";

import { useMemo, useState } from "react";

import AppShell from "../components/AppShell";
import JobFacetsSidebar, {
  EMPTY_FACET_SELECTION,
  postedAgeBucket,
  salaryBucket,
  type FacetSelection,
} from "../components/JobFacetsSidebar";
import JobPasteTeamPanel from "../components/JobPasteTeamPanel";
import JobResultsList from "../components/JobResultsList";
import ResumeWizard from "../components/ResumeWizard";
import { useJobTeam } from "../hooks/useJobTeam";
import type { JobFacets, RankedJob } from "../lib/types";

export default function HomePage() {
  const [results, setResults] = useState<RankedJob[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [teamStepActive, setTeamStepActive] = useState(false);
  const [facets, setFacets] = useState<JobFacets | null>(null);
  const [droppedCounts, setDroppedCounts] = useState<Record<string, number>>({});
  const [facetSelection, setFacetSelection] = useState<FacetSelection>(EMPTY_FACET_SELECTION);
  const [profileHash, setProfileHash] = useState<string | null>(null);

  const {
    getTeamState,
    hydrateJobTeam,
    handleExtractTeam,
    handleFindTeam,
    handleRevealEmail,
    resetTeams,
  } = useJobTeam(searchId);

  const filteredResults = useMemo(() => {
    return results.filter((item) => {
      const job = item.job;
      if (facetSelection.company && job.company !== facetSelection.company) return false;
      if (facetSelection.seniority && (job.seniority || "unknown") !== facetSelection.seniority) {
        return false;
      }
      if (
        facetSelection.remote_mode &&
        (job.remote_mode || "unknown") !== facetSelection.remote_mode
      ) {
        return false;
      }
      if (
        facetSelection.salary_bucket &&
        (job.salary_bucket ?? salaryBucket(job)) !== facetSelection.salary_bucket
      ) {
        return false;
      }
      if (
        facetSelection.posted_age &&
        (job.posted_age_bucket ?? postedAgeBucket(job.posted_at)) !== facetSelection.posted_age
      ) {
        return false;
      }
      if (facetSelection.source && job.source !== facetSelection.source) {
        return false;
      }
      return true;
    });
  }, [results, facetSelection]);

  return (
    <AppShell
      title="Resume → jobs → team"
      lede="Upload a resume and rank live jobs, or paste a job description to identify the hiring team — no job board required for the team path."
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
          setFacets(null);
          setDroppedCounts({});
          setFacetSelection(EMPTY_FACET_SELECTION);
          resetTeams();
          // Keep profileHash after confirm so job-card feedback still has provenance.
        }}
        onProfileReady={(hash) => setProfileHash(hash || null)}
        onSearchComplete={(nextResults, nextSearchId, meta) => {
          setResults(nextResults);
          setSearchId(nextSearchId);
          setSearching(false);
          setSearched(true);
          setFacets(meta?.facets ?? null);
          setDroppedCounts(meta?.dropped_counts ?? {});
          setFacetSelection(EMPTY_FACET_SELECTION);
        }}
        onSearchError={() => {
          setSearching(false);
          setSearched(false);
        }}
      />

      <div className={facets ? "results-with-facets" : undefined}>
        {facets ? (
          <JobFacetsSidebar
            facets={facets}
            selection={facetSelection}
            onChange={setFacetSelection}
            droppedCounts={droppedCounts}
          />
        ) : null}
        <JobResultsList
          results={filteredResults}
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
          profileHash={profileHash}
        />
      </div>

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
