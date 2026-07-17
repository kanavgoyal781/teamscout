"use client";

import { useMutation } from "@tanstack/react-query";
import { FileText, Upload } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { confirmResume, createSearch, formatApiError, uploadResume } from "../../lib/api";
import type { JobFacets, RankedJob, ResumeUploadResponse, SearchParams } from "../../lib/types";
import SearchFilters, { defaultSearchParams, sanitizeSearchParams } from "./SearchFilters";
import Stepper from "../ui/Stepper";

type ConfirmedSnapshot = {
  title: string;
  location: string;
  skills: string[];
};

export type SearchCompleteMeta = {
  facets?: JobFacets;
  dropped_counts?: Record<string, number>;
  queries?: string[];
  per_source_counts?: Record<string, import("../../lib/types").SourceCounts>;
  source_errors?: string[];
  pool_notices?: string[];
  pool_empty_reason?: string | null;
};

type ResumeWizardProps = {
  onSearchComplete: (results: RankedJob[], searchId: string, meta?: SearchCompleteMeta) => void;
  onSearchStart: () => void;
  onSearchError?: () => void;
  searching?: boolean;
  hasResults?: boolean;
  /** Parent sets true when any job team panel is open. */
  teamStepActive?: boolean;
  /** Stable profile content hash for feedback provenance. */
  onProfileReady?: (profileHash: string) => void;
};

const STEPS = [
  { id: "upload", label: "Upload" },
  { id: "profile", label: "Profile" },
  { id: "matches", label: "Matches" },
  { id: "team", label: "Team" },
];

export default function ResumeWizard({
  onSearchComplete,
  onSearchStart,
  onSearchError,
  searching = false,
  hasResults = false,
  teamStepActive = false,
  onProfileReady,
}: ResumeWizardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [resume, setResume] = useState<ResumeUploadResponse | null>(null);
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [skillDraft, setSkillDraft] = useState("");
  const [confirmedSnapshot, setConfirmedSnapshot] = useState<ConfirmedSnapshot | null>(null);
  const [searchParams, setSearchParams] = useState<SearchParams>(() => defaultSearchParams());

  const profileDirty =
    confirmedSnapshot !== null &&
    (title !== confirmedSnapshot.title ||
      location !== confirmedSnapshot.location ||
      skills.length !== confirmedSnapshot.skills.length ||
      skills.some((skill, index) => skill !== confirmedSnapshot.skills[index]));

  const canSearch = Boolean(
    resume?.confirmed && confirmedSnapshot && !profileDirty && title && skills.length > 0,
  );

  const stepIndex = useMemo(() => {
    if (teamStepActive) return 3;
    if (hasResults || searching) return 2;
    if (resume) return 1;
    return 0;
  }, [teamStepActive, hasResults, searching, resume]);

  const uploadMutation = useMutation({
    mutationFn: (f: File) => uploadResume(f),
    retry: false,
    onSuccess: (uploaded) => {
      setResume(uploaded);
      setTitle(uploaded.profile.title);
      setLocation(uploaded.profile.location);
      setSkills(uploaded.profile.skills);
      setConfirmedSnapshot(null);
      // Clear prior profile provenance until this resume is confirmed.
      onProfileReady?.("");
      toast.success(`Parsed ${uploaded.filename}. Review and confirm before searching.`);
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const confirmMutation = useMutation({
    mutationFn: () => {
      if (!resume) throw new Error("No resume");
      return confirmResume(resume.id, { title, location, skills });
    },
    retry: false,
    onSuccess: (confirmed) => {
      if (!resume) return;
      setResume({ ...resume, confirmed: confirmed.confirmed, profile: confirmed.profile });
      {
        const hash = resume?.content_hash;
        if (hash) onProfileReady?.(hash);
      }
      setConfirmedSnapshot({
        title: confirmed.profile.title,
        location: confirmed.profile.location,
        skills: confirmed.profile.skills,
      });
      // Re-seed filters from profile location; seniority always Any (never sticky Intern).
      setSearchParams(defaultSearchParams(confirmed.profile.location));
      toast.success("Profile confirmed. Ready to search.");
    },
    onError: (error) => toast.error(formatApiError(error)),
  });

  const searchMutation = useMutation({
    mutationFn: () => {
      if (!resume) throw new Error("No resume");
      // Last-line sanitize so Full-time + Intern never hits the API
      return createSearch(resume.id, sanitizeSearchParams(searchParams));
    },
    retry: false,
    onMutate: () => {
      onSearchStart();
    },
    onSuccess: (response) => {
      // Zero-pool is a results state — never toast.error; strip shows notices.
      onSearchComplete(response.results, response.search_id, {
        facets: response.facets,
        dropped_counts: response.dropped_counts,
        queries: response.queries,
        per_source_counts: response.per_source_counts,
        source_errors: response.source_errors,
        pool_notices: response.pool_notices,
        pool_empty_reason: response.pool_empty_reason,
      });
      if (response.results.length > 0) {
        toast.success(`Found top ${response.results.length} matches.`);
      }
      // Empty success: JobResultsList warning strip carries the story (no blocking toast).
    },
    onError: (error) => {
      // Reserved for true failures (e.g. all sources errored → service_failing).
      onSearchError?.();
      toast.error(formatApiError(error));
    },
  });

  function pickFile(next: File | null) {
    if (!next) return;
    const ok =
      next.type === "application/pdf" ||
      next.name.toLowerCase().endsWith(".pdf") ||
      next.name.toLowerCase().endsWith(".docx");
    if (!ok) {
      toast.error("Choose a PDF or DOCX resume.");
      return;
    }
    setFile(next);
  }

  function onDrop(event: React.DragEvent) {
    event.preventDefault();
    setDragging(false);
    const next = event.dataTransfer.files?.[0] ?? null;
    pickFile(next);
  }

  function addSkill() {
    const value = skillDraft.trim();
    if (!value) return;
    if (!skills.includes(value)) {
      setSkills((s) => [...s, value]);
    }
    setSkillDraft("");
  }

  function removeSkill(skill: string) {
    setSkills((s) => s.filter((x) => x !== skill));
  }

  const parsed = Boolean(resume);

  return (
    <section className="panel" data-testid="resume-wizard" data-tour="resume-wizard">
      <div data-tour="wizard-stepper" data-testid="wizard-stepper">
        <Stepper steps={STEPS} current={stepIndex} />
        <p className="meta" data-tour="credit-confirm" data-testid="credit-confirm" style={{ marginTop: 8 }}>
          Team lookup and email reveal are confirm-gated (real credits). This tour never auto-spends.
        </p>
      </div>

      <h2>Upload resume</h2>
      <div
        className={`dropzone${dragging ? " is-dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="Upload resume PDF or DOCX"
      >
        <Upload size={28} strokeWidth={1.5} aria-hidden style={{ color: "var(--accent)", marginBottom: 8 }} />
        <p className="dropzone-title">Drag & drop resume</p>
        <p className="meta" style={{ margin: 0 }}>
          PDF or DOCX · click to browse
        </p>
        <input
          ref={inputRef}
          name="resume"
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {file ? (
        <div className="file-preview" data-testid="file-preview">
          <FileText size={20} aria-hidden />
          <div style={{ flex: 1, minWidth: 0 }}>
            <strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis" }}>
              {file.name}
            </strong>
            <span className="meta font-num" style={{ margin: 0 }}>
              {(file.size / 1024).toFixed(1)} KB
              {parsed ? " · parsed" : ""}
            </span>
          </div>
          <button
            type="button"
            className={parsed ? "ghost" : "primary"}
            disabled={uploadMutation.isPending}
            onClick={() => {
              uploadMutation.mutate(file);
            }}
          >
            {uploadMutation.isPending ? "Parsing…" : parsed ? "Re-parse" : "Upload & parse"}
          </button>
        </div>
      ) : null}

      {resume ? (
        <div style={{ marginTop: 24 }} data-testid="profile-confirm" data-tour="profile-confirm">
          <h2>Confirm profile</h2>
          <p className="meta">
            Parsed from <strong>{resume.filename}</strong>
            {resume.confirmed ? " · confirmed" : " · not confirmed"}
            {profileDirty ? " · edits pending re-confirm" : ""}
          </p>
          <div className="field-grid">
            <label>
              Title
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                aria-label="Job title"
              />
            </label>
            <label>
              Location
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                aria-label="Location"
              />
            </label>
            <div className="full-width">
              <span className="meta" style={{ display: "block", marginBottom: 8 }}>
                Skills
              </span>
              <div className="chip-row" style={{ marginTop: 0, marginBottom: 10 }}>
                {skills.map((skill) => (
                  <span key={skill} className="chip chip-removable">
                    {skill}
                    <button
                      type="button"
                      onClick={() => removeSkill(skill)}
                      aria-label={`Remove skill ${skill}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <div className="actions">
                <input
                  value={skillDraft}
                  onChange={(e) => setSkillDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addSkill();
                    }
                  }}
                  placeholder="Add skill"
                  aria-label="Add skill"
                  style={{ minWidth: 160 }}
                />
                <button type="button" onClick={addSkill}>
                  Add
                </button>
              </div>
            </div>
          </div>
          <SearchFilters
            params={searchParams}
            onChange={setSearchParams}
            disabled={searchMutation.isPending || searching}
            profileLocation={location}
            profileTitle={title}
          />
          <div className="search-filters-actions actions" data-testid="search-actions">
            <button
              type="button"
              onClick={() => confirmMutation.mutate()}
              disabled={confirmMutation.isPending || !title || skills.length === 0}
            >
              {confirmMutation.isPending ? "Saving…" : "Confirm profile"}
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => searchMutation.mutate()}
              disabled={searchMutation.isPending || searching || !canSearch}
              data-testid="search-jobs"
              data-tour="search-jobs"
            >
              {searchMutation.isPending || searching ? "Searching & ranking…" : "Search jobs"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
