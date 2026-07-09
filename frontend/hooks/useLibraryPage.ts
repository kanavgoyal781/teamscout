"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { toast } from "sonner";

import {
  formatApiError,
  intentSearch,
  listLibraryResumes,
  recommendResumes,
  syncDrive,
  uploadLibrary,
} from "../lib/api";
import type {
  IntentSearchRequest,
  RankedJob,
  RankedResumeRecommendation,
} from "../lib/types";
import { queryKeys } from "../lib/query";

export function useLibraryPage() {
  const queryClient = useQueryClient();
  const [driveUrl, setDriveUrl] = useState("");
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [role, setRole] = useState("");
  const [years, setYears] = useState("5");
  const [location, setLocation] = useState("");
  const [remotePreference, setRemotePreference] =
    useState<IntentSearchRequest["remote_preference"]>("any");
  const [jobResults, setJobResults] = useState<RankedJob[]>([]);
  const [intentSearched, setIntentSearched] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<RankedResumeRecommendation[]>([]);

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
      toast.success(
        `Uploaded ${response.files_received} file(s): ${response.files_parsed} parsed, ${response.files_skipped} skipped (duplicate hash)${ignoredNote}.`,
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.library });
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const syncMutation = useMutation({
    mutationFn: (url: string) => syncDrive(url),
    retry: false,
    onSuccess: async (response) => {
      const ignoredNote =
        response.files_ignored > 0
          ? `, ${response.files_ignored} ignored (non-PDF/DOCX)`
          : "";
      setSyncStatus(
        `Synced folder ${response.folder_id}: ${response.files_seen} resume files seen, ${response.files_parsed} parsed, ${response.files_skipped} skipped${ignoredNote}.`,
      );
      toast.success(
        `Drive sync complete: ${response.files_parsed} parsed, ${response.files_skipped} skipped${ignoredNote}.`,
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.library });
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const searchMutation = useMutation({
    mutationFn: (payload: IntentSearchRequest) => intentSearch(payload),
    retry: false,
    onSuccess: (response) => {
      setJobResults(response.results);
      setSelectedJobId(null);
      setRecommendations([]);
      setIntentSearched(true);
      toast.success(
        response.results.length > 0
          ? `Ranked ${response.results.length} jobs for your intent.`
          : "Search complete — no jobs matched this intent.",
      );
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const recommendMutation = useMutation({
    mutationFn: (jobId: string) => recommendResumes(jobId),
    retry: false,
    onSuccess: (response) => {
      setRecommendations(response.recommendations);
      if (response.recommendations.length === 0) {
        toast.message("No resume recommendations returned.");
      }
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

  function handleIntentSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!role.trim()) {
      toast.error("Desired role is required.");
      return;
    }
    setJobResults([]);
    setSelectedJobId(null);
    setRecommendations([]);
    setIntentSearched(false);
    searchMutation.mutate({
      role: role.trim(),
      years_of_experience: Number(years) || 0,
      location: location.trim(),
      remote_preference: remotePreference,
    });
  }

  function handlePickJob(jobId: string) {
    setSelectedJobId(jobId);
    setRecommendations([]);
    recommendMutation.mutate(jobId);
  }

  return {
    resumes: libraryQuery.data?.resumes ?? [],
    loadingLibrary: libraryQuery.isPending,
    libraryError: libraryQuery.isError ? formatApiError(libraryQuery.error) : null,
    uploading: uploadMutation.isPending,
    syncing: syncMutation.isPending,
    driveUrl,
    syncStatus,
    role,
    years,
    location,
    remotePreference,
    searching: searchMutation.isPending,
    jobResults,
    intentSearched,
    selectedJobId,
    recommending: recommendMutation.isPending,
    recommendations,
    setDriveUrl,
    setRole,
    setYears,
    setLocation,
    setRemotePreference,
    handleUpload,
    handleDriveSync,
    handleIntentSearch,
    handlePickJob,
  };
}
