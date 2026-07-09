"use client";

import { useMutation } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import {
  extractTeam,
  findTeam,
  formatApiError,
  getJobTeam,
  revealEmail,
} from "../lib/api";
import type { Contact, TeamExtraction } from "../lib/types";

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

  const hydrateMutation = useMutation({
    mutationFn: (jobId: string) => getJobTeam(jobId),
    retry: false,
    meta: { silent: true },
  });

  const extractMutation = useMutation({
    mutationFn: (jobId: string) => extractTeam(jobId),
    retry: false,
  });

  const findMutation = useMutation({
    mutationFn: ({
      jobId,
      extractionId,
    }: {
      jobId: string;
      extractionId: string;
    }) =>
      findTeam(jobId, {
        extraction_id: extractionId,
        search_id: searchId,
      }),
    retry: false,
  });

  const revealMutation = useMutation({
    mutationFn: ({ contactId, confirm }: { contactId: string; confirm: boolean }) =>
      revealEmail(contactId, confirm),
    retry: false,
  });

  const hydrateJobTeam = useCallback(
    async (jobId: string) => {
      updateJobTeam(jobId, { hydrating: true });
      try {
        const cached = await hydrateMutation.mutateAsync(jobId);
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
        toast.error(formatApiError(error));
      }
    },
    [hydrateMutation, updateJobTeam],
  );

  const handleExtractTeam = useCallback(
    async (jobId: string) => {
      updateJobTeam(jobId, { extracting: true, teamSearched: false });
      try {
        const response = await extractMutation.mutateAsync(jobId);
        updateJobTeam(jobId, {
          extractionId: response.extraction_id,
          extraction: response.extraction,
          extracting: false,
        });
        toast.success("Hiring team extracted. Review and confirm before looking up people.");
      } catch (error) {
        updateJobTeam(jobId, { extracting: false });
        toast.error(formatApiError(error));
      }
    },
    [extractMutation, updateJobTeam],
  );

  const handleFindTeam = useCallback(
    async (jobId: string) => {
      const state = teamByJob[jobId];
      if (!state?.extractionId) return;

      updateJobTeam(jobId, { finding: true });
      try {
        await findMutation.mutateAsync({
          jobId,
          extractionId: state.extractionId,
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
        toast.success(
          cached.contacts.length > 0
            ? `Found ${cached.contacts.length} people.`
            : "No people matched. Try broadening filters.",
        );
      } catch (error) {
        updateJobTeam(jobId, { finding: false });
        toast.error(formatApiError(error));
      }
    },
    [findMutation, teamByJob, updateJobTeam],
  );

  const handleRevealEmail = useCallback(
    async (jobId: string, contact: Contact, confirm: boolean) => {
      const current = teamByJob[jobId] ?? emptyTeamState();
      updateJobTeam(jobId, {
        revealLoading: { ...current.revealLoading, [contact.id]: true },
      });
      try {
        const response = await revealMutation.mutateAsync({
          contactId: contact.id,
          confirm,
        });
        if (!confirm && response.status === "preview" && response.cost_credits !== null) {
          updateJobTeam(jobId, {
            revealLoading: { ...current.revealLoading, [contact.id]: false },
            pendingReveal: { ...current.pendingReveal, [contact.id]: response.cost_credits },
          });
          return;
        }

        const contacts = (teamByJob[jobId]?.contacts ?? current.contacts).map((row) =>
          row.id === contact.id
            ? { ...row, email: response.email, email_revealed: Boolean(response.email) }
            : row,
        );
        updateJobTeam(jobId, {
          contacts,
          revealLoading: { ...current.revealLoading, [contact.id]: false },
          pendingReveal: { ...current.pendingReveal, [contact.id]: null },
        });
        if (response.email) {
          toast.success(`Email revealed for ${contact.full_name}.`);
        }
      } catch (error) {
        updateJobTeam(jobId, {
          revealLoading: { ...current.revealLoading, [contact.id]: false },
          pendingReveal: { ...current.pendingReveal, [contact.id]: null },
        });
        toast.error(formatApiError(error));
      }
    },
    [revealMutation, teamByJob, updateJobTeam],
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
