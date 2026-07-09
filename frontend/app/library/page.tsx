"use client";

import AppShell from "../../components/AppShell";
import LibraryIngestPanel from "../../components/LibraryIngestPanel";
import PasteJdPanel from "../../components/PasteJdPanel";
import ResumeRecommendations from "../../components/ResumeRecommendations";
import { useLibraryPage } from "../../hooks/useLibraryPage";

export default function LibraryPage() {
  const state = useLibraryPage();

  return (
    <AppShell
      title="Resume library → best pick"
      lede="Load many resumes (upload or Drive), paste a job description, and we pick the best resume for that posting — close calls included."
    >
      <LibraryIngestPanel
        resumes={state.resumes}
        loadingLibrary={state.loadingLibrary}
        libraryError={state.libraryError}
        uploading={state.uploading}
        syncing={state.syncing}
        driveUrl={state.driveUrl}
        syncStatus={state.syncStatus}
        onDriveUrlChange={state.setDriveUrl}
        onUpload={state.handleUpload}
        onDriveSync={state.handleDriveSync}
      />
      <PasteJdPanel
        resumeCount={state.resumes.length}
        jdText={state.jdText}
        title={state.jdTitle}
        company={state.jdCompany}
        location={state.jdLocation}
        matching={state.matching}
        onJdTextChange={state.setJdText}
        onTitleChange={state.setJdTitle}
        onCompanyChange={state.setJdCompany}
        onLocationChange={state.setJdLocation}
        onSubmit={state.handleMatchJd}
      />
      <ResumeRecommendations
        jobResults={[]}
        searching={state.matching}
        searched={state.matched}
        selectedJobId={state.matchedJobId}
        recommending={state.matching}
        recommendations={state.recommendations}
        onPickJob={() => {}}
        jdMode
        jdTitle={state.matchedJobTitle}
        jdCompany={state.matchedJobCompany}
      />
    </AppShell>
  );
}
