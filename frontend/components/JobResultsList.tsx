"use client";

import type { Contact, RankedJob } from "../lib/api";
import type { JobTeamState } from "../hooks/useJobTeam";
import { formatPostedAt } from "../lib/format";
import TeamDiscoveryPanel from "./TeamDiscoveryPanel";

type JobResultsListProps = {
  results: RankedJob[];
  getTeamState: (jobId: string) => JobTeamState;
  onHydrate: (jobId: string) => void;
  onExtract: (jobId: string) => void;
  onFindTeam: (jobId: string) => void;
  onRevealEmail: (jobId: string, contact: Contact, confirm: boolean) => void;
};

export default function JobResultsList({
  results,
  getTeamState,
  onHydrate,
  onExtract,
  onFindTeam,
  onRevealEmail,
}: JobResultsListProps) {
  if (results.length === 0) {
    return null;
  }

  return (
    <section className="panel">
      <h2>3. Top matches &amp; team discovery</h2>
      <div className="job-list">
        {results.map((item) => {
          const teamState = getTeamState(item.job.id);
          return (
            <article key={item.job.id} className="job-card">
              <div className="job-card-header">
                <div>
                  <h3>{item.job.title}</h3>
                  <p className="meta">
                    {item.job.company} · {item.job.location} · Posted {formatPostedAt(item.job.posted_at)}
                  </p>
                </div>
                <div className="score-pill">{item.match_score}</div>
              </div>
              <p className="job-description">{item.job.description.slice(0, 280)}…</p>
              <div className="chip-row">
                {item.score_breakdown.matched_skills.map((skill) => (
                  <span key={`m-${item.job.id}-${skill}`} className="chip chip-match">
                    {skill}
                  </span>
                ))}
                {item.score_breakdown.missing_skills.map((skill) => (
                  <span key={`x-${item.job.id}-${skill}`} className="chip chip-miss">
                    {skill}
                  </span>
                ))}
              </div>
              <p className="rationale">{item.score_breakdown.rationale}</p>
              <details
                onToggle={(event) => {
                  if ((event.currentTarget as HTMLDetailsElement).open) {
                    onHydrate(item.job.id);
                  }
                }}
              >
                <summary>Score breakdown</summary>
                <ul className="breakdown-list">
                  <li>LLM fit: {item.score_breakdown.llm_fit}</li>
                  <li>RRF normalized: {item.score_breakdown.rrf_normalized.toFixed(3)}</li>
                  {item.score_breakdown.dense_rank_score ? (
                    <li>Dense rank score: {item.score_breakdown.dense_rank_score}</li>
                  ) : null}
                  <li>Skill Jaccard: {item.score_breakdown.skill_jaccard.toFixed(3)}</li>
                  <li>Recency: {item.score_breakdown.recency.toFixed(3)}</li>
                </ul>
              </details>
              <a href={item.job.apply_url} target="_blank" rel="noreferrer" className="apply-link">
                Apply
              </a>

              <TeamDiscoveryPanel
                teamState={teamState}
                onExtract={() => onExtract(item.job.id)}
                onFindTeam={() => onFindTeam(item.job.id)}
                onRevealEmail={(contact, confirm) => onRevealEmail(item.job.id, contact, confirm)}
              />
            </article>
          );
        })}
      </div>
    </section>
  );
}