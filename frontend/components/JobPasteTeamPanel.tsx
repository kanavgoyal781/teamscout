"use client";

import { FormEvent, useState } from "react";
import { toast } from "sonner";

import { formatApiError, ingestJobFromText } from "../lib/api";
import type { JobTeamState } from "../hooks/useJobTeam";
import type { Contact } from "../lib/types";
import TeamDiscoveryPanel from "./TeamDiscoveryPanel";

type JobPasteTeamPanelProps = {
  getTeamState: (jobId: string) => JobTeamState;
  onHydrate: (jobId: string) => void;
  onExtract: (jobId: string) => void;
  onFindTeam: (jobId: string) => void;
  onRevealEmail: (jobId: string, contact: Contact, confirm: boolean) => void;
  onTeamPanelOpenChange?: (open: boolean) => void;
};

export default function JobPasteTeamPanel({
  getTeamState,
  onHydrate,
  onExtract,
  onFindTeam,
  onRevealEmail,
  onTeamPanelOpenChange,
}: JobPasteTeamPanelProps) {
  const [description, setDescription] = useState("");
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobMeta, setJobMeta] = useState<{ title: string; company: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (description.trim().length < 40) {
      toast.error("Paste a fuller job description (at least ~40 characters).");
      return;
    }
    setSubmitting(true);
    try {
      const res = await ingestJobFromText({
        description: description.trim(),
        title: title.trim() || undefined,
        company: company.trim() || undefined,
        location: location.trim() || undefined,
      });
      setJobId(res.job_id);
      setJobMeta({ title: res.title, company: res.company });
      onTeamPanelOpenChange?.(true);
      toast.success("Job saved — extract the hiring team below.");
      onHydrate(res.job_id);
    } catch (error) {
      toast.error(formatApiError(error));
    } finally {
      setSubmitting(false);
    }
  }

  const teamState = jobId ? getTeamState(jobId) : null;

  return (
    <section className="panel" data-testid="job-paste-team">
      <h2>Paste a job → extract hiring team</h2>
      <p className="meta" style={{ marginTop: 0, marginBottom: "var(--space-4)" }}>
        Skip resume job-search. Paste a posting, extract who likely owns the hire, then look up the
        hiring team and reveal emails.
      </p>

      <form className="field-grid paste-form" onSubmit={handleSubmit}>
        <label className="field">
          <span className="field-label">
            Title <span className="field-optional">optional</span>
          </span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Role title"
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span className="field-label">
            Company{" "}
            <span className="field-optional" title="Optional — improves hiring-team match">
              optional
            </span>
          </span>
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Company name"
            autoComplete="organization"
            title="Optional — improves hiring-team match"
          />
        </label>
        <label className="field">
          <span className="field-label">
            Location <span className="field-optional">optional</span>
          </span>
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="City / Remote"
            autoComplete="off"
          />
        </label>
        <label className="field field-span-all">
          <span className="field-label">Job description</span>
          <textarea
            className="paste-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={12}
            placeholder="Paste the full job description…"
            required
            data-testid="job-paste-description"
          />
        </label>
        <div className="field-span-all paste-actions">
          <button type="submit" className="primary" disabled={submitting || !description.trim()}>
            {submitting ? "Saving job…" : "Save job & prepare team extract"}
          </button>
        </div>
      </form>

      {jobId && teamState && jobMeta ? (
        <div className="paste-team-followup">
          <p className="meta">
            Working on <strong>{jobMeta.title}</strong>
            {jobMeta.company ? ` · ${jobMeta.company}` : ""}{" "}
            <span className="font-num">({jobId.slice(0, 8)}…)</span>
          </p>
          <TeamDiscoveryPanel
            teamState={teamState}
            roleHint={jobMeta.title}
            onExtract={() => onExtract(jobId)}
            onFindTeam={() => onFindTeam(jobId)}
            onRevealEmail={(contact, confirm) => onRevealEmail(jobId, contact, confirm)}
          />
        </div>
      ) : null}
    </section>
  );
}
