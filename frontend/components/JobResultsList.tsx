"use client";

import { motion, useReducedMotion } from "framer-motion";
import { ExternalLink, Users } from "lucide-react";
import { useEffect, useState } from "react";

import type { Contact, RankedJob } from "../lib/types";
import type { JobTeamState } from "../hooks/useJobTeam";
import { formatPostedAgo } from "../lib/format";
import { cardHover, easeOut, shouldSkipEntrance, staggerContainer, staggerItem } from "../lib/motion";
import EmptyState from "./ui/EmptyState";
import { JobCardSkeleton } from "./ui/Skeleton";
import ScoreBars from "./ui/ScoreBars";
import ScoreRing from "./ui/ScoreRing";
import FeedbackButtons, { trackImplicitFeedback } from "./FeedbackButtons";
import TeamDiscoveryPanel from "./TeamDiscoveryPanel";

type JobResultsListProps = {
  results: RankedJob[];
  loading?: boolean;
  /** True after a search attempt completed (success or empty). */
  searched?: boolean;
  /** Optional profile content hash for feedback provenance. */
  profileHash?: string | null;
  getTeamState: (jobId: string) => JobTeamState;
  onHydrate: (jobId: string) => void;
  onExtract: (jobId: string) => void;
  onFindTeam: (jobId: string) => void;
  onRevealEmail: (jobId: string, contact: Contact, confirm: boolean) => void;
  /** Notify parent when any team panel is open (wizard Team step). */
  onTeamPanelOpenChange?: (open: boolean) => void;
};

export default function JobResultsList({
  results,
  loading = false,
  searched = false,
  profileHash = null,
  getTeamState,
  onHydrate,
  onExtract,
  onFindTeam,
  onRevealEmail,
  onTeamPanelOpenChange,
}: JobResultsListProps) {
  const reduced = useReducedMotion();
  const skipEntrance = shouldSkipEntrance(reduced);
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  useEffect(() => {
    onTeamPanelOpenChange?.(expandedTeam !== null);
  }, [expandedTeam, onTeamPanelOpenChange]);

  if (loading) {
    return (
      <section className="panel" data-testid="job-results-loading">
        <h2>Top matches</h2>
        <div className="job-list">
          <JobCardSkeleton />
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      </section>
    );
  }

  if (results.length === 0) {
    if (!searched) return null;
    return <JobResultsEmpty />;
  }

  return (
    <section className="panel" data-testid="job-results" data-tour="job-results">
      <h2>Top matches &amp; team discovery</h2>
      <motion.div
        className="job-list"
        variants={skipEntrance ? undefined : staggerContainer}
        initial={skipEntrance ? undefined : "hidden"}
        animate={skipEntrance ? undefined : "show"}
      >
        {results.map((item, index) => {
          const teamState = getTeamState(item.job.id);
          const teamOpen = expandedTeam === item.job.id;
          return (
            <motion.article
              key={item.job.id}
              className="job-card"
              variants={skipEntrance ? undefined : staggerItem}
              whileHover={skipEntrance ? undefined : cardHover}
              transition={easeOut}
              data-testid={`job-card-${index}`}
            >
              <div className="job-card-header">
                <div>
                  <h3>
                    <span className="rank-badge font-num" aria-label={`Rank ${index + 1}`}>
                      #{index + 1}
                    </span>
                    {item.job.title}
                  </h3>
                  <p className="meta" style={{ margin: 0 }}>
                    <strong>{item.job.company}</strong>
                    {" · "}
                    {item.job.location || "Location n/a"}
                    {" · "}
                    <span className="font-num">{formatPostedAgo(item.job.posted_at)}</span>
                  </p>
                  <div className="chip-row job-flags" style={{ marginTop: 6 }}>
                    {(item.job.duplicates_count ?? 1) > 1 ? (
                      <span className="chip chip-dup" title="Cross-posted listing">
                        Posted on {item.job.duplicates_count} boards
                      </span>
                    ) : null}
                    {item.job.salary_unknown !== false ? (
                      <span className="chip chip-salary-unknown">Salary unknown</span>
                    ) : item.job.salary_min != null ? (
                      <span className="chip chip-salary font-num">
                        From ${Math.round(item.job.salary_min).toLocaleString()}
                      </span>
                    ) : null}
                    {item.job.seniority ? (
                      <span className="chip">{item.job.seniority}</span>
                    ) : null}
                    {item.job.remote_mode && item.job.remote_mode !== "unknown" ? (
                      <span className="chip">{item.job.remote_mode}</span>
                    ) : null}
                  </div>
                </div>
                <ScoreRing score={item.match_score} />
              </div>

              <p className="job-description">
                {item.job.description.length > 280
                  ? `${item.job.description.slice(0, 280)}…`
                  : item.job.description}
              </p>

              <div className="chip-row">
                {item.score_breakdown.matched_skills.map((skill) => (
                  <span key={`m-${item.job.id}-${skill}`} className="chip chip-match">
                    {skill}
                  </span>
                ))}
                {item.score_breakdown.missing_skills.map((skill) => (
                  <span key={`x-${item.job.id}-${skill}`} className="chip chip-gap">
                    {skill}
                  </span>
                ))}
              </div>

              <details className="why-match">
                <summary>Why this match</summary>
                <ScoreBars breakdown={item.score_breakdown} variant="jobs" />
                {item.score_breakdown.rationale ? (
                  <p className="rationale">{item.score_breakdown.rationale}</p>
                ) : null}
              </details>

              <div className="actions" style={{ marginTop: 14 }}>
                <a
                  href={item.job.apply_url}
                  target="_blank"
                  rel="noreferrer"
                  className="apply-link"
                  onClick={() =>
                    trackImplicitFeedback({
                      kind: "apply_click",
                      targetType: "job_match",
                      targetId: item.job.id,
                      profileHash,
                      scoreShown: item.match_score,
                    })
                  }
                >
                  Apply <ExternalLink size={14} aria-hidden />
                </a>
                <button
                  type="button"
                  onClick={() => {
                    setExpandedTeam(teamOpen ? null : item.job.id);
                    if (!teamOpen) {
                      onHydrate(item.job.id);
                      trackImplicitFeedback({
                        kind: "find_team_click",
                        targetType: "job_match",
                        targetId: item.job.id,
                        profileHash,
                        scoreShown: item.match_score,
                      });
                    }
                  }}
                  aria-expanded={teamOpen}
                  data-testid={`find-team-${index}`}
                >
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <Users size={14} aria-hidden />
                    {teamOpen ? "Hide team" : "Find the team"}
                  </span>
                </button>
                <FeedbackButtons
                  targetType="job_match"
                  targetId={item.job.id}
                  profileHash={profileHash}
                  scoreShown={item.match_score}
                  testIdPrefix={`job-feedback-${index}`}
                />
                <span className="meta font-num" style={{ margin: 0 }}>
                  Est. ~20–30 credits before team lookup
                </span>
              </div>

              {teamOpen ? (
                <TeamDiscoveryPanel
                  teamState={teamState}
                  roleHint={item.job.title}
                  onExtract={() => onExtract(item.job.id)}
                  onFindTeam={() => onFindTeam(item.job.id)}
                  onRevealEmail={(contact, confirm) =>
                    onRevealEmail(item.job.id, contact, confirm)
                  }
                />
              ) : null}
            </motion.article>
          );
        })}
      </motion.div>
    </section>
  );
}

export function JobResultsEmpty() {
  return (
    <section className="panel" data-testid="job-results-empty">
      <EmptyState instruction="No ranked jobs matched this search. Try refining title, location, or skills, then search again." />
    </section>
  );
}
