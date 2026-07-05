"use client";

import { FormEvent } from "react";

import { LibraryResume } from "../lib/api";

type LibraryIngestPanelProps = {
  resumes: LibraryResume[];
  loadingLibrary: boolean;
  uploading: boolean;
  syncing: boolean;
  driveUrl: string;
  syncStatus: string | null;
  onDriveUrlChange: (value: string) => void;
  onUpload: (event: FormEvent<HTMLFormElement>) => void;
  onDriveSync: (event: FormEvent<HTMLFormElement>) => void;
};

export default function LibraryIngestPanel({
  resumes,
  loadingLibrary,
  uploading,
  syncing,
  driveUrl,
  syncStatus,
  onDriveUrlChange,
  onUpload,
  onDriveSync,
}: LibraryIngestPanelProps) {
  return (
    <section className="panel">
      <h2>1. Resume library</h2>
      <form className="upload-form" onSubmit={onUpload}>
        <input
          name="library-files"
          type="file"
          multiple
          accept=".pdf,.docx,.zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/zip"
        />
        <button type="submit" disabled={uploading}>
          {uploading ? "Uploading…" : "Upload files or ZIP"}
        </button>
      </form>

      <form className="upload-form library-drive-form" onSubmit={onDriveSync}>
        <input
          value={driveUrl}
          onChange={(event) => onDriveUrlChange(event.target.value)}
          placeholder="https://drive.google.com/drive/folders/..."
          className="drive-input"
        />
        <button type="submit" disabled={syncing}>
          {syncing ? "Syncing Drive…" : "Sync Drive folder"}
        </button>
      </form>
      {syncStatus ? <p className="meta">{syncStatus}</p> : null}

      {loadingLibrary ? (
        <p className="meta empty-hint">Loading library…</p>
      ) : resumes.length === 0 ? (
        <p className="meta empty-hint">No resumes in library yet. Upload files or sync a Drive folder.</p>
      ) : (
        <ul className="library-list">
          {resumes.map((resume) => (
            <li key={resume.id}>
              <strong>{resume.filename}</strong>
              <span className="meta">
                {resume.profile.title || "Untitled"} · {resume.source} ·{" "}
                {resume.profile.skills.slice(0, 4).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}