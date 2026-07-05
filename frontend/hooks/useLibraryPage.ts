"use client";

import { FormEvent, useEffect, useState } from "react";

import {
  IntentSearchRequest,
  LibraryResume,
  RankedJob,
  RankedResumeRecommendation,
  intentSearch,
  listLibraryResumes,
  recommendResumes,
  syncDrive,
  uploadLibrary,
} from "../lib/api";

export type LibraryToast = { kind: "error" | "info"; message: string } | null;

export function useLibraryPage() {
  const [toast, setToast] = useState<LibraryToast>(null);
  const [resumes, setResumes] = useState<LibraryResume[]>([]);
  const [loadingLibrary, setLoadingLibrary] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [driveUrl, setDriveUrl] = useState("");
  const [syncStatus, setSyncStatus] = useState<string | null>(null);
  const [role, setRole] = useState("");
  const [years, setYears] = useState("5");
  const [location, setLocation] = useState("");
  const [remotePreference, setRemotePreference] =
    useState<IntentSearchRequest["remote_preference"]>("any");
  const [searching, setSearching] = useState(false);
  const [jobResults, setJobResults] = useState<RankedJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [recommending, setRecommending] = useState(false);
  const [recommendations, setRecommendations] = useState<RankedResumeRecommendation[]>([]);

  async function refreshLibrary() {
    setLoadingLibrary(true);
    try {
      const response = await listLibraryResumes();
      setResumes(response.resumes);
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Failed to load library" });
    } finally {
      setLoadingLibrary(false);
    }
  }

  useEffect(() => {
    void refreshLibrary();
  }, []);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("library-files") as HTMLInputElement;
    const files = Array.from(fileInput.files ?? []);
    if (files.length === 0) {
      setToast({ kind: "error", message: "Choose one or more PDF/DOCX files or a ZIP archive." });
      return;
    }

    setUploading(true);
    setToast(null);
    try {
      const response = await uploadLibrary(files);
      setResumes(response.resumes);
      const ignoredNote =
        response.files_ignored > 0 ? `, ${response.files_ignored} ignored (unsupported type)` : "";
      setToast({
        kind: "info",
        message: `Uploaded ${response.files_received} file(s): ${response.files_parsed} parsed, ${response.files_skipped} skipped (duplicate hash)${ignoredNote}.`,
      });
      await refreshLibrary();
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Upload failed" });
    } finally {
      setUploading(false);
    }
  }

  async function handleDriveSync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!driveUrl.trim()) {
      setToast({ kind: "error", message: "Enter a Google Drive folder URL." });
      return;
    }

    setSyncing(true);
    setToast(null);
    try {
      const response = await syncDrive(driveUrl.trim());
      const ignoredNote =
        response.files_ignored > 0 ? `, ${response.files_ignored} ignored (non-PDF/DOCX)` : "";
      setSyncStatus(
        `Synced folder ${response.folder_id}: ${response.files_seen} resume files seen, ${response.files_parsed} parsed, ${response.files_skipped} skipped${ignoredNote}.`,
      );
      setToast({
        kind: "info",
        message: `Drive sync complete: ${response.files_parsed} parsed, ${response.files_skipped} skipped${ignoredNote}.`,
      });
      await refreshLibrary();
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Drive sync failed" });
    } finally {
      setSyncing(false);
    }
  }

  async function handleIntentSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!role.trim()) {
      setToast({ kind: "error", message: "Desired role is required." });
      return;
    }

    setSearching(true);
    setToast(null);
    setJobResults([]);
    setSelectedJobId(null);
    setRecommendations([]);
    try {
      const response = await intentSearch({
        role: role.trim(),
        years_of_experience: Number(years) || 0,
        location: location.trim(),
        remote_preference: remotePreference,
      });
      setJobResults(response.results);
      setToast({ kind: "info", message: `Ranked ${response.results.length} jobs for your intent.` });
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "Intent search failed" });
    } finally {
      setSearching(false);
    }
  }

  async function handlePickJob(jobId: string) {
    setSelectedJobId(jobId);
    setRecommending(true);
    setRecommendations([]);
    setToast(null);
    try {
      const response = await recommendResumes(jobId);
      setRecommendations(response.recommendations);
      if (response.recommendations.length === 0) {
        setToast({ kind: "info", message: "No resume recommendations returned." });
      }
    } catch (error) {
      setToast({
        kind: "error",
        message: error instanceof Error ? error.message : "Resume recommendation failed",
      });
    } finally {
      setRecommending(false);
    }
  }

  return {
    toast,
    resumes,
    loadingLibrary,
    uploading,
    syncing,
    driveUrl,
    syncStatus,
    role,
    years,
    location,
    remotePreference,
    searching,
    jobResults,
    selectedJobId,
    recommending,
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