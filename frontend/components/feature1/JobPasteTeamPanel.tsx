"use client";

import { FormEvent, useState } from "react";
import { toast } from "sonner";

import { formatApiError, ingestJobFromText } from "../../lib/api";
import type { JobTeamState } from "../../hooks/useJobTeam";
import { useJdMetadataPrefill } from "../../hooks/useJdMetadataPrefill";
import type { Contact } from "../../lib/types";
import AutoDetectedChip from "../ui/AutoDetectedChip";
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
  const [title, setTitleState] = useState("");
  const [company, setCompanyState] = useState("");
  const [location, setLocationState] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobMeta, setJobMeta] = useState<{ title: string; company: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const prefill = useJdMetadataPrefill(description, {
    setTitle: setTitleState,
    setCompany: setCompanyState,
    setLocation: setLocationState,
  });

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
  const displayCompany = jobMeta?.company?.trim() || company.trim() || "Unknown company";

  return (
    <section className="panel" data-testid="job-paste-team">
      <h2>Paste a job → extract hiring team</h2>
      <p className="meta" style={{ marginTop: 0, marginBottom: "var(--space-4)" }}>
        Skip resume job-search. Paste a posting, extract who likely owns the hire, then look up the
        hiring team and reveal emails.
      </p>

      {prefill.detecting ? (
        <p className="detecting-shimmer" data-testid="jd-detecting">
          Detecting job details…
        </p>
      ) : null}

      <form className="field-grid paste-form" onSubmit={handleSubmit}>
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
            placeholder="Role title"
            autoComplete="off"
            data-testid="job-paste-title"
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
            placeholder="Company name"
            autoComplete="organization"
            data-testid="job-paste-company"
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
            autoComplete="off"
            data-testid="job-paste-location"
          />
        </label>
        <label className="field field-span-all">
          <span className="field-label">Job description</span>
          <textarea
            className="paste-textarea"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onPaste={(e) => {
              const pasted = e.clipboardData.getData("text");
              if (pasted) {
                // allow default then effect runs on state update
              }
            }}
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
            Working on <strong>{jobMeta.title || "Role"}</strong>
            {" · "}
            <strong>{displayCompany}</strong>{" "}
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
