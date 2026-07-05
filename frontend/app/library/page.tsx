"use client";

import AppShell from "../../components/AppShell";
import IntentSearchPanel from "../../components/IntentSearchPanel";
import LibraryIngestPanel from "../../components/LibraryIngestPanel";
import ResumeRecommendations from "../../components/ResumeRecommendations";
import { useLibraryPage } from "../../hooks/useLibraryPage";

export default function LibraryPage() {
  const state = useLibraryPage();

  return (
    <AppShell
      title="Resume library and best-resume pick"
      lede="Ingest resumes from Drive or local upload, search jobs by intent, then pick the best resume for a job with coverage and justification."
      toast={state.toast}
    >
      <LibraryIngestPanel
        resumes={state.resumes}
        loadingLibrary={state.loadingLibrary}
        uploading={state.uploading}
        syncing={state.syncing}
        driveUrl={state.driveUrl}
        syncStatus={state.syncStatus}
        onDriveUrlChange={state.setDriveUrl}
        onUpload={state.handleUpload}
        onDriveSync={state.handleDriveSync}
      />
      <IntentSearchPanel
        resumes={state.resumes}
        role={state.role}
        years={state.years}
        location={state.location}
        remotePreference={state.remotePreference}
        searching={state.searching}
        onRoleChange={state.setRole}
        onYearsChange={state.setYears}
        onLocationChange={state.setLocation}
        onRemotePreferenceChange={state.setRemotePreference}
        onSearch={state.handleIntentSearch}
      />
      <ResumeRecommendations
        jobResults={state.jobResults}
        searching={state.searching}
        selectedJobId={state.selectedJobId}
        recommending={state.recommending}
        recommendations={state.recommendations}
        onPickJob={state.handlePickJob}
      />
    </AppShell>
  );
}