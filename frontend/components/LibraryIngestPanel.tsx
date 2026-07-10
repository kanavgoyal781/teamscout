"use client";

import { FileText, Upload } from "lucide-react";
import { FormEvent, useRef, useState } from "react";
import { toast } from "sonner";

import type { LibraryResume } from "../lib/types";
import EmptyState from "./ui/EmptyState";
import { SkeletonLines } from "./ui/Skeleton";

type LibraryIngestPanelProps = {
  resumes: LibraryResume[];
  loadingLibrary: boolean;
  libraryError?: string | null;
  uploading: boolean;
  syncing: boolean;
  driveUrl: string;
  syncStatus: string | null;
  distinctVersions?: number;
  onDriveUrlChange: (value: string) => void;
  onUpload: (event: FormEvent<HTMLFormElement>) => void;
  onDriveSync: (event: FormEvent<HTMLFormElement>) => void;
};

export default function LibraryIngestPanel({
  resumes,
  loadingLibrary,
  libraryError,
  uploading,
  syncing,
  driveUrl,
  syncStatus,
  distinctVersions,
  onDriveUrlChange,
  onUpload,
  onDriveSync,
}: LibraryIngestPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [picked, setPicked] = useState<File[]>([]);

  function acceptFiles(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (files.length === 0) return;
    setPicked(files);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (picked.length === 0 && !(inputRef.current?.files && inputRef.current.files.length > 0)) {
      toast.error("Choose one or more PDF/DOCX files or a ZIP archive.");
      return;
    }
    // Ensure the form's named input has the files for the parent handler
    onUpload(event);
  }

  return (
    <section className="panel" data-testid="library-ingest">
      <h2>1. Resume library</h2>
      <form className="library-upload-form" onSubmit={handleSubmit}>
        <div
          className={`dropzone${dragging ? " is-dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            acceptFiles(e.dataTransfer.files);
            if (inputRef.current && e.dataTransfer.files) {
              // DataTransfer assignment is limited; parent reads input.files — set via DataTransfer if possible
              try {
                const dt = new DataTransfer();
                Array.from(e.dataTransfer.files).forEach((f) => dt.items.add(f));
                inputRef.current.files = dt.files;
              } catch {
                /* browsers without DataTransfer still use click picker */
              }
            }
          }}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label="Upload library files PDF DOCX or ZIP"
        >
          <Upload size={28} strokeWidth={1.5} aria-hidden style={{ color: "var(--accent)", marginBottom: 8 }} />
          <p className="dropzone-title">Drag & drop resumes</p>
          <p className="meta" style={{ margin: 0 }}>
            PDF, DOCX, or ZIP · multi-file · click to browse
          </p>
          <input
            ref={inputRef}
            name="library-files"
            type="file"
            multiple
            accept=".pdf,.docx,.zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/zip"
            aria-label="Upload library files"
            onChange={(e) => acceptFiles(e.target.files)}
          />
        </div>
        {picked.length > 0 ? (
          <div className="file-preview" style={{ marginTop: 12 }}>
            <FileText size={20} aria-hidden />
            <div style={{ flex: 1 }}>
              <strong>
                {picked.length === 1 ? picked[0].name : `${picked.length} files selected`}
              </strong>
              <span className="meta font-num" style={{ display: "block", margin: 0 }}>
                {picked.length === 1
                  ? `${(picked[0].size / 1024).toFixed(1)} KB`
                  : picked.map((f) => f.name).join(", ").slice(0, 80)}
              </span>
            </div>
            <button type="submit" className="primary" disabled={uploading}>
              {uploading ? "Uploading…" : "Upload files or ZIP"}
            </button>
          </div>
        ) : (
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="submit" className="primary" disabled={uploading}>
              {uploading ? "Uploading…" : "Upload files or ZIP"}
            </button>
          </div>
        )}
      </form>

      <form className="upload-form library-drive-form" onSubmit={onDriveSync}>
        <input
          value={driveUrl}
          onChange={(event) => onDriveUrlChange(event.target.value)}
          placeholder="https://drive.google.com/drive/folders/..."
          className="drive-input"
          aria-label="Google Drive folder URL"
        />
        <button type="submit" disabled={syncing}>
          {syncing ? "Syncing Drive…" : "Sync Drive folder"}
        </button>
      </form>
      {syncStatus ? <p className="meta font-num">{syncStatus}</p> : null}

      {loadingLibrary ? (
        <div style={{ marginTop: 16 }} aria-busy="true" aria-label="Loading library">
          <SkeletonLines lines={4} />
        </div>
      ) : libraryError ? (
        <div style={{ marginTop: 16 }}>
          <EmptyState title="Could not load library" instruction={libraryError} />
        </div>
      ) : resumes.length === 0 ? (
        <div style={{ marginTop: 16 }}>
          <EmptyState instruction="No resumes in library yet. Upload files or sync a Drive folder." />
        </div>
      ) : (
        <>
          <p className="meta font-num" style={{ marginTop: 16 }} data-testid="library-stats">
            Your library: {resumes.length} file{resumes.length === 1 ? "" : "s"},{" "}
            {distinctVersions ??
              new Set(resumes.map((r) => r.cluster_id || r.id)).size}{" "}
            distinct version
            {(distinctVersions ?? new Set(resumes.map((r) => r.cluster_id || r.id)).size) === 1
              ? ""
              : "s"}
          </p>
          <ul className="library-list" data-testid="library-list">
            {(() => {
              // Group near-dup variants under cluster_id (M12).
              const byCluster = new Map<string, typeof resumes>();
              for (const r of resumes) {
                const cid = r.cluster_id || r.id;
                const list = byCluster.get(cid) ?? [];
                list.push(r);
                byCluster.set(cid, list);
              }
              const groups = Array.from(byCluster.entries()).sort((a, b) =>
                a[0].localeCompare(b[0]),
              );
              return groups.map(([cid, members]) => (
                <li key={cid} className="library-cluster">
                  {members.length > 1 ? (
                    <p className="meta" style={{ margin: "0 0 4px" }}>
                      Base version {cid.slice(0, 8)} · {members.length} near-dups
                    </p>
                  ) : null}
                  <ul className="library-cluster-members" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                    {members.map((resume) => (
                      <li key={resume.id} style={{ marginBottom: 6 }}>
                        <strong>{resume.filename}</strong>
                        <span className="meta" style={{ margin: 0, display: "block" }}>
                          {resume.profile.title || "Untitled"} · {resume.source} ·{" "}
                          {resume.profile.skills.slice(0, 4).join(", ")}
                          {resume.cluster_label ? ` · ${resume.cluster_label}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </li>
              ));
            })()}
          </ul>
        </>
      )}
    </section>
  );
}
