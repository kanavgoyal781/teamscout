"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { toast } from "sonner";

import {
  formatApiError,
  listLibraryResumes,
  recommendFromJd,
  syncDrive,
  uploadLibrary,
} from "../lib/api";
import { contentHashHex } from "../lib/hash";
import type { IngestFileResult, RankedResumeRecommendation } from "../lib/types";
import { queryKeys } from "../lib/query";

export function useLibraryPage() {
  const queryClient = useQueryClient();
  const [driveUrl, setDriveUrl] = useState("");
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [lastIngestResults, setLastIngestResults] = useState<IngestFileResult[] | null>(null);
  const [newlyParsedIds, setNewlyParsedIds] = useState<string[]>([]);
  const [cachedCount, setCachedCount] = useState(0);
  const [parsedCount, setParsedCount] = useState(0);
  const [jdText, setJdText] = useState("");
  const [jdTitle, setJdTitle] = useState("");
  const [jdCompany, setJdCompany] = useState("");
  const [jdLocation, setJdLocation] = useState("");
  const [matchedJobTitle, setMatchedJobTitle] = useState<string>("");
  const [matchedJobCompany, setMatchedJobCompany] = useState<string>("");
  const [recommendations, setRecommendations] = useState<RankedResumeRecommendation[]>([]);
  const [jdHash, setJdHash] = useState<string | null>(null);
  const [matched, setMatched] = useState(false);
  const [tournamentRan, setTournamentRan] = useState(false);
  const [tournamentComparisons, setTournamentComparisons] = useState(0);

  const libraryQuery = useQuery({
    queryKey: queryKeys.library,
    queryFn: listLibraryResumes,
    retry: 1,
  });

  const uploadMutation = useMutation({
    mutationFn: (files: File[]) => uploadLibrary(files),
    retry: false,
    onSuccess: async (response) => {
      const ignoredNote =
        response.files_ignored > 0
          ? `, ${response.files_ignored} ignored (unsupported type)`
          : "";
      const unitsNote =
        response.units_indexed === false
          ? " Units not indexed (embeddings unavailable)."
          : response.units_indexed
            ? " Units indexed for MaxSim ranking."
            : "";
      const results = response.file_results ?? [];
      setLastIngestResults(results);
      setCachedCount(response.files_skipped);
      setParsedCount(response.files_parsed);
      setNewlyParsedIds(
        results.filter((r) => r.status === "parsed" && r.resume_id).map((r) => r.resume_id as string),
      );
      toast.success(
        `Uploaded ${response.files_received} file(s): ${response.files_parsed} parsed, ${response.files_skipped} cached${ignoredNote}.${unitsNote}`,
      );
      if (response.units_index_warning) {
        toast.message(response.units_index_warning);
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.library });
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const syncMutation = useMutation({
    mutationFn: (url: string) => syncDrive(url),
    retry: false,
    onSuccess: async (response) => {
      const failed = response.files_failed ?? 0;
      const ignoredNote =
        response.files_ignored > 0
          ? `, ${response.files_ignored} ignored (non-PDF/DOCX)`
          : "";
      const failedNote = failed > 0 ? `, ${failed} failed` : "";
      const unitsNote =
        response.units_indexed === false
          ? " Units not indexed (embeddings unavailable)."
          : response.units_indexed
            ? " Units indexed for MaxSim ranking."
            : "";
      const results = response.file_results ?? [];
      setLastIngestResults(results);
      setCachedCount(response.files_skipped);
      setParsedCount(response.files_parsed);
      setNewlyParsedIds(
        results.filter((r) => r.status === "parsed" && r.resume_id).map((r) => r.resume_id as string),
      );
      // Per-file failures are listed in results — never a global scary toast.
      setSyncStatus(
        `Synced ${response.files_parsed} parsed · ${response.files_skipped} skipped (cached)${failedNote}${ignoredNote}.${unitsNote}`,
      );
      const summary = `Drive sync: ${response.files_parsed} parsed, ${response.files_skipped} skipped${failedNote}${ignoredNote}.${unitsNote}`;
      if (failed > 0 && response.files_parsed === 0 && response.files_skipped === 0) {
        toast.message(summary);
      } else {
        toast.success(summary);
      }
      const failedRows = results.filter((r) => r.status === "failed" && r.reason);
      for (const row of failedRows.slice(0, 5)) {
        toast.message(`${row.filename}: ${row.reason}`);
      }
      if (response.units_index_warning) {
        toast.message(response.units_index_warning);
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.library });
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const matchMutation = useMutation({
    mutationFn: () =>
      recommendFromJd({
        job_description: jdText.trim(),
        title: jdTitle.trim() || undefined,
        company: jdCompany.trim() || undefined,
        location: jdLocation.trim() || undefined,
      }),
    retry: false,
    onSuccess: (response) => {
      setMatchedJobTitle(response.job_title);
      setMatchedJobCompany(response.job_company);
      setRecommendations(response.recommendations);
      setJdHash(contentHashHex([jdTitle, jdCompany, jdLocation, jdText].join("\n")));
      setTournamentRan(Boolean(response.tournament_ran));
      setTournamentComparisons(response.tournament_comparisons ?? 0);
      setMatched(true);
      toast.success(
        response.recommendations.length > 0
          ? `Ranked ${response.recommendations.length} resume(s) for this job.`
          : "No recommendations returned.",
      );
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("library-files") as HTMLInputElement;
    const files = Array.from(fileInput.files ?? []);
    if (files.length === 0) {
      toast.error("Choose one or more PDF/DOCX files or a ZIP archive.");
      return;
    }
    uploadMutation.mutate(files);
  }

  function handleDriveSync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!driveUrl.trim()) {
      toast.error("Enter a Google Drive folder URL.");
      return;
    }
    syncMutation.mutate(driveUrl.trim());
  }

  function handleMatchJd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (jdText.trim().length < 40) {
      toast.error("Paste a fuller job description (at least ~40 characters).");
      return;
    }
    if ((libraryQuery.data?.resumes.length ?? 0) === 0) {
      toast.error("Upload or sync resumes into the library first.");
      return;
    }
    setRecommendations([]);
    setMatched(false);
    setTournamentRan(false);
    setTournamentComparisons(0);
    matchMutation.mutate();
  }

  return {
    resumes: libraryQuery.data?.resumes ?? [],
    distinctVersions: libraryQuery.data?.distinct_versions ?? 0,
    loadingLibrary: libraryQuery.isPending,
    libraryError: libraryQuery.isError ? formatApiError(libraryQuery.error) : null,
    uploading: uploadMutation.isPending,
    syncing: syncMutation.isPending,
    driveUrl,
    syncStatus,
    lastIngestResults,
    newlyParsedIds,
    cachedCount,
    parsedCount,
    jdText,
    jdTitle,
    jdCompany,
    jdLocation,
    matching: matchMutation.isPending,
    matched,
    matchedJobTitle,
    matchedJobCompany,
    recommendations,
    jdHash,
    tournamentRan,
    tournamentComparisons,
    setDriveUrl,
    setJdText,
    setJdTitle,
    setJdCompany,
    setJdLocation,
    handleUpload,
    handleDriveSync,
    handleMatchJd,
  };
}
