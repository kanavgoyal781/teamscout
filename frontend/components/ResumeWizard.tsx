"use client";

import { FormEvent, useMemo, useState } from "react";

import { ResumeUploadResponse, confirmResume, createSearch, uploadResume } from "../lib/api";
import type { RankedJob } from "../lib/api";

type Toast = { kind: "error" | "info"; message: string } | null;

type ConfirmedSnapshot = {
  title: string;
  location: string;
  skills: string[];
};

type ResumeWizardProps = {
  onToast: (toast: Toast) => void;
  onSearchComplete: (results: RankedJob[], searchId: string) => void;
  onSearchStart: () => void;
};

export default function ResumeWizard({ onToast, onSearchComplete, onSearchStart }: ResumeWizardProps) {
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [searching, setSearching] = useState(false);
  const [resume, setResume] = useState<ResumeUploadResponse | null>(null);
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [confirmedSnapshot, setConfirmedSnapshot] = useState<ConfirmedSnapshot | null>(null);

  const skills = useMemo(
    () =>
      skillsText
        .split(",")
        .map((skill) => skill.trim())
        .filter(Boolean),
    [skillsText],
  );

  const profileDirty =
    confirmedSnapshot !== null &&
    (title !== confirmedSnapshot.title ||
      location !== confirmedSnapshot.location ||
      skills.length !== confirmedSnapshot.skills.length ||
      skills.some((skill, index) => skill !== confirmedSnapshot.skills[index]));

  const canSearch = Boolean(resume?.confirmed && confirmedSnapshot && !profileDirty && title && skills.length > 0);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("resume") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) {
      onToast({ kind: "error", message: "Choose a PDF or DOCX resume to upload." });
      return;
    }

    setUploading(true);
    onToast(null);
    onSearchStart();
    try {
      const uploaded = await uploadResume(file);
      setResume(uploaded);
      setTitle(uploaded.profile.title);
      setLocation(uploaded.profile.location);
      setSkillsText(uploaded.profile.skills.join(", "));
      setConfirmedSnapshot(null);
      onToast({ kind: "info", message: `Parsed ${uploaded.filename}. Review and confirm before searching.` });
    } catch (error) {
      onToast({ kind: "error", message: error instanceof Error ? error.message : "Upload failed" });
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm() {
    if (!resume) return;
    setConfirming(true);
    onToast(null);
    try {
      const confirmed = await confirmResume(resume.id, { title, location, skills });
      setResume({ ...resume, confirmed: confirmed.confirmed, profile: confirmed.profile });
      setConfirmedSnapshot({
        title: confirmed.profile.title,
        location: confirmed.profile.location,
        skills: confirmed.profile.skills,
      });
      onToast({ kind: "info", message: "Profile confirmed. Ready to search." });
    } catch (error) {
      onToast({ kind: "error", message: error instanceof Error ? error.message : "Confirm failed" });
    } finally {
      setConfirming(false);
    }
  }

  async function handleSearch() {
    if (!resume || !canSearch) return;
    setSearching(true);
    onToast(null);
    onSearchStart();
    try {
      const response = await createSearch(resume.id);
      onSearchComplete(response.results, response.search_id);
      onToast({ kind: "info", message: `Found top ${response.results.length} matches.` });
    } catch (error) {
      onToast({ kind: "error", message: error instanceof Error ? error.message : "Search failed" });
    } finally {
      setSearching(false);
    }
  }

  return (
    <>
      <section className="panel">
        <h2>1. Upload resume</h2>
        <form className="upload-form" onSubmit={handleUpload}>
          <input
            name="resume"
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          />
          <button type="submit" disabled={uploading}>
            {uploading ? "Parsing…" : "Upload & parse"}
          </button>
        </form>
      </section>

      {resume ? (
        <section className="panel">
          <h2>2. Confirm profile</h2>
          <p className="meta">
            Parsed from <strong>{resume.filename}</strong>
            {resume.confirmed ? " · confirmed" : " · not confirmed"}
            {profileDirty ? " · edits pending re-confirm" : ""}
          </p>
          <div className="field-grid">
            <label>
              Title
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label>
              Location
              <input value={location} onChange={(event) => setLocation(event.target.value)} />
            </label>
            <label className="full-width">
              Skills (comma-separated)
              <textarea value={skillsText} onChange={(event) => setSkillsText(event.target.value)} rows={3} />
            </label>
          </div>
          <div className="actions">
            <button type="button" onClick={handleConfirm} disabled={confirming}>
              {confirming ? "Saving…" : "Confirm profile"}
            </button>
            <button type="button" className="primary" onClick={handleSearch} disabled={searching || !canSearch}>
              {searching ? "Searching & ranking…" : "Search jobs"}
            </button>
          </div>
        </section>
      ) : null}
    </>
  );
}