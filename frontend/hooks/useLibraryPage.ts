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
import type { RankedResumeRecommendation } from "../lib/types";
import { queryKeys } from "../lib/query";

export function useLibraryPage() {
  const queryClient = useQueryClient();
  const [driveUrl, setDriveUrl] = useState("");
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [jdText, setJdText] = useState("");
  const [jdTitle, setJdTitle] = useState("");
  const [jdCompany, setJdCompany] = useState("");
  const [jdLocation, setJdLocation] = useState("");
  const [matchedJobTitle, setMatchedJobTitle] = useState<string>("");
  const [matchedJobCompany, setMatchedJobCompany] = useState<string>("");
  const [recommendations, setRecommendations] = useState<RankedResumeRecommendation[]>([]);
  const [matched, setMatched] = useState(false);

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
    matchMutation.mutate();
  }

  return {
    resumes: libraryQuery.data?.resumes ?? [],
    loadingLibrary: libraryQuery.isPending,
    libraryError: libraryQuery.isError ? formatApiError(libraryQuery.error) : null,
    uploading: uploadMutation.isPending,
    syncing: syncMutation.isPending,
    driveUrl,
    syncStatus,
    jdText,
    jdTitle,
    jdCompany,
    jdLocation,
    matching: matchMutation.isPending,
    matched,
    matchedJobTitle,
    matchedJobCompany,
    recommendations,
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
