"use client";

import { useCallback, useState } from "react";

import {
  Contact,
  TeamExtraction,
  extractTeam,
  findTeam,
  getJobTeam,
  revealEmail,
} from "../lib/api";

export type JobTeamState = {
  extracting: boolean;
  finding: boolean;
  hydrating: boolean;
  teamSearched: boolean;
  extractionId: string | null;
  extraction: TeamExtraction | null;
  contacts: Contact[];
  revealLoading: Record<string, boolean>;
  pendingReveal: Record<string, number | null>;
  searchPath: string | null;
};

function emptyTeamState(): JobTeamState {
  return {
    extracting: false,
    finding: false,
    hydrating: false,
    teamSearched: false,
    extractionId: null,
    extraction: null,
    contacts: [],
    revealLoading: {},
    pendingReveal: {},
    searchPath: null,
  };
}

export function useJobTeam(searchId: string | null) {
  const [teamByJob, setTeamByJob] = useState<Record<string, JobTeamState>>({});

  const updateJobTeam = useCallback((jobId: string, patch: Partial<JobTeamState>) => {
    setTeamByJob((current) => ({
      ...current,
      [jobId]: { ...(current[jobId] ?? emptyTeamState()), ...patch },
    }));
  }, []);

  const resetTeams = useCallback(() => {
    setTeamByJob({});
  }, []);

  const hydrateJobTeam = useCallback(
    async (
      jobId: string,
      onToast?: (kind: "error" | "info", message: string) => void,
    ) => {
      updateJobTeam(jobId, { hydrating: true });
      try {
        const cached = await getJobTeam(jobId);
        updateJobTeam(jobId, {
          contacts: cached.contacts,
          extractionId: cached.extraction_id,
          extraction: cached.extraction,
          teamSearched: cached.team_searched,
          searchPath: cached.search_path ?? null,
          hydrating: false,
        });
      } catch (error) {
        updateJobTeam(jobId, { hydrating: false });
        onToast?.("error", error instanceof Error ? error.message : "Failed to load team");
      }
    },
    [updateJobTeam],
  );

  const handleExtractTeam = useCallback(
    async (jobId: string, onToast: (kind: "error" | "info", message: string) => void) => {
      updateJobTeam(jobId, { extracting: true, teamSearched: false });
      try {
        const response = await extractTeam(jobId);
        updateJobTeam(jobId, {
          extractionId: response.extraction_id,
          extraction: response.extraction,
          extracting: false,
        });
        onToast(
          "info",
          "Team extracted from job description. Review and confirm before Sumble lookup.",
        );
      } catch (error) {
        updateJobTeam(jobId, { extracting: false });
        onToast("error", error instanceof Error ? error.message : "Team extraction failed");
      }
    },
    [updateJobTeam],
  );

  const handleFindTeam = useCallback(
    async (jobId: string, onToast: (kind: "error" | "info", message: string) => void) => {
      const state = teamByJob[jobId];
      if (!state?.extractionId) return;

      updateJobTeam(jobId, { finding: true });
      try {
        await findTeam(jobId, {
          extraction_id: state.extractionId,
          search_id: searchId,
        });
        const cached = await getJobTeam(jobId);
        updateJobTeam(jobId, {
          contacts: cached.contacts,
          extractionId: cached.extraction_id ?? state.extractionId,
          extraction: cached.extraction ?? state.extraction,
          teamSearched: cached.team_searched,
          searchPath: cached.search_path ?? null,
          finding: false,
        });
        onToast(
          "info",
          cached.contacts.length > 0
            ? `Found ${cached.contacts.length} people.`
            : "No people matched. Try broadening team or title filters.",
        );
      } catch (error) {
        updateJobTeam(jobId, { finding: false });
        onToast("error", error instanceof Error ? error.message : "Find team failed");
      }
    },
    [searchId, teamByJob, updateJobTeam],
  );

  const handleRevealEmail = useCallback(
    async (
      jobId: string,
      contact: Contact,
      confirm: boolean,
      onToast: (kind: "error" | "info", message: string) => void,
    ) => {
      updateJobTeam(jobId, {
        revealLoading: { ...teamByJob[jobId]?.revealLoading, [contact.id]: true },
      });
      try {
        const response = await revealEmail(contact.id, confirm);
        if (!confirm && response.status === "preview" && response.cost_credits !== null) {
          updateJobTeam(jobId, {
            revealLoading: { ...teamByJob[jobId]?.revealLoading, [contact.id]: false },
            pendingReveal: { ...teamByJob[jobId]?.pendingReveal, [contact.id]: response.cost_credits },
          });
          return;
        }

        const contacts = (teamByJob[jobId]?.contacts ?? []).map((row) =>
          row.id === contact.id
            ? { ...row, email: response.email, email_revealed: Boolean(response.email) }
            : row,
        );
        updateJobTeam(jobId, {
          contacts,
          revealLoading: { ...teamByJob[jobId]?.revealLoading, [contact.id]: false },
          pendingReveal: { ...teamByJob[jobId]?.pendingReveal, [contact.id]: null },
        });
        if (response.email) {
          onToast("info", `Email revealed for ${contact.full_name}.`);
        }
      } catch (error) {
        updateJobTeam(jobId, {
          revealLoading: { ...teamByJob[jobId]?.revealLoading, [contact.id]: false },
          pendingReveal: { ...teamByJob[jobId]?.pendingReveal, [contact.id]: null },
        });
        onToast("error", error instanceof Error ? error.message : "Email reveal failed");
      }
    },
    [teamByJob, updateJobTeam],
  );

  const getTeamState = useCallback(
    (jobId: string) => teamByJob[jobId] ?? emptyTeamState(),
    [teamByJob],
  );

  return {
    getTeamState,
    hydrateJobTeam,
    handleExtractTeam,
    handleFindTeam,
    handleRevealEmail,
    resetTeams,
  };
}