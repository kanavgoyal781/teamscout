"use client";

import { FormEvent, useMemo } from "react";

import { useJdMetadataPrefill } from "../../hooks/useJdMetadataPrefill";
import AutoDetectedChip from "../ui/AutoDetectedChip";

type PasteJdPanelProps = {
  resumeCount: number;
  jdText: string;
  title: string;
  company: string;
  location: string;
  matching: boolean;
  onJdTextChange: (v: string) => void;
  onTitleChange: (v: string) => void;
  onCompanyChange: (v: string) => void;
  onLocationChange: (v: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  /** Optional intent hints from metadata for parent (remote/seniority/salary) */
  onMetadataHints?: (hints: {
    remote_mode: string | null;
    seniority: string | null;
    salary_min: number | null;
    salary_max: number | null;
    salary_currency: string | null;
  }) => void;
};

export default function PasteJdPanel({
  resumeCount,
  jdText,
  title,
  company,
  location,
  matching,
  onJdTextChange,
  onTitleChange,
  onCompanyChange,
  onLocationChange,
  onSubmit,
  onMetadataHints,
}: PasteJdPanelProps) {
  const disabled = resumeCount === 0 || matching;
  const setters = useMemo(
    () => ({
      setTitle: onTitleChange,
      setCompany: onCompanyChange,
      setLocation: onLocationChange,
    }),
    [onTitleChange, onCompanyChange, onLocationChange],
  );
  const prefill = useJdMetadataPrefill(jdText, setters);

  return (
    <section className="panel" data-testid="paste-jd-panel">
      <h2>2. Paste a job description</h2>
      <p className="meta" style={{ marginTop: 0, marginBottom: "var(--space-4)" }}>
        Copy a LinkedIn or careers-page posting. We rank every resume in your library and pick the
        best fit — no live job search.
      </p>
      {resumeCount === 0 ? (
        <p className="meta" style={{ marginBottom: "var(--space-4)" }}>
          Add resumes above first.
        </p>
      ) : (
        <p className="meta" style={{ marginBottom: "var(--space-4)" }}>
          Matching against <span className="font-num">{resumeCount}</span> library resume
          {resumeCount === 1 ? "" : "s"}.
        </p>
      )}

      {prefill.detecting ? (
        <p className="detecting-shimmer" data-testid="jd-detecting">
          Detecting job details…
        </p>
      ) : null}

      <form className="field-grid paste-form" onSubmit={onSubmit}>
        <label className="field">
          <span className="field-label">
            Title <span className="field-optional">optional</span>
            {prefill.autoFields.title ? (
              <AutoDetectedChip confidence={prefill.confidence("title")} />
            ) : null}
          </span>
          <input
            value={title}
            onChange={(e) => prefill.setTitle(e.target.value)}
            placeholder="e.g. Senior Data Scientist"
            disabled={disabled}
            autoComplete="off"
            data-testid="jd-title"
          />
        </label>
        <label className="field">
          <span className="field-label">
            Company <span className="field-optional">optional</span>
            {prefill.autoFields.company ? (
              <AutoDetectedChip confidence={prefill.confidence("company")} />
            ) : null}
          </span>
          <input
            value={company}
            onChange={(e) => prefill.setCompany(e.target.value)}
            placeholder="e.g. Acme Corp"
            disabled={disabled}
            autoComplete="organization"
            data-testid="jd-company"
          />
        </label>
        <label className="field">
          <span className="field-label">
            Location <span className="field-optional">optional</span>
            {prefill.autoFields.location ? (
              <AutoDetectedChip confidence={prefill.confidence("location")} />
            ) : null}
          </span>
          <input
            value={location}
            onChange={(e) => prefill.setLocation(e.target.value)}
            placeholder="City / Remote"
            disabled={disabled}
            autoComplete="off"
            data-testid="jd-location"
          />
        </label>
        <label className="field field-span-all">
          <span className="field-label">Job description</span>
          <textarea
            className="paste-textarea"
            value={jdText}
            onChange={(e) => onJdTextChange(e.target.value)}
            onPaste={(e) => {
              const pasted = e.clipboardData.getData("text");
              if (pasted) prefill.onDescriptionPaste(pasted);
            }}
            rows={14}
            placeholder="Paste the full job description here…"
            required
            disabled={disabled}
            data-testid="jd-paste"
          />
        </label>
        <div className="field-span-all paste-actions">
          <button type="submit" className="primary" disabled={disabled || !jdText.trim()}>
            {matching ? "Ranking library…" : "Find best resume for this job"}
          </button>
        </div>
      </form>
    </section>
  );
}
