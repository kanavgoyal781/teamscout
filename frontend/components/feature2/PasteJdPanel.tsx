"use client";

import { FormEvent } from "react";

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
}: PasteJdPanelProps) {
  const disabled = resumeCount === 0 || matching;

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

      <form className="field-grid paste-form" onSubmit={onSubmit}>
        <label className="field">
          <span className="field-label">
            Title <span className="field-optional">optional</span>
          </span>
          <input
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="e.g. Senior Data Scientist"
            disabled={disabled}
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span className="field-label">
            Company <span className="field-optional">optional</span>
          </span>
          <input
            value={company}
            onChange={(e) => onCompanyChange(e.target.value)}
            placeholder="e.g. Acme Corp"
            disabled={disabled}
            autoComplete="organization"
          />
        </label>
        <label className="field">
          <span className="field-label">
            Location <span className="field-optional">optional</span>
          </span>
          <input
            value={location}
            onChange={(e) => onLocationChange(e.target.value)}
            placeholder="City / Remote"
            disabled={disabled}
            autoComplete="off"
          />
        </label>
        <label className="field field-span-all">
          <span className="field-label">Job description</span>
          <textarea
            className="paste-textarea"
            value={jdText}
            onChange={(e) => onJdTextChange(e.target.value)}
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
