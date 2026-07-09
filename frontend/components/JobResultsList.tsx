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
import TeamDiscoveryPanel from "./TeamDiscoveryPanel";

type JobResultsListProps = {
  results: RankedJob[];
  loading?: boolean;
  /** True after a search attempt completed (success or empty). */
  searched?: boolean;
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
    <section className="panel" data-testid="job-results">
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
                >
                  Apply <ExternalLink size={14} aria-hidden />
                </a>
                <button
                  type="button"
                  onClick={() => {
                    setExpandedTeam(teamOpen ? null : item.job.id);
                    if (!teamOpen) onHydrate(item.job.id);
                  }}
                  aria-expanded={teamOpen}
                  data-testid={`find-team-${index}`}
                >
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <Users size={14} aria-hidden />
                    {teamOpen ? "Hide team" : "Find the team"}
                  </span>
                </button>
                <span className="meta font-num" style={{ margin: 0 }}>
                  Est. ~20–30 credits before Sumble spend
                </span>
              </div>

              {teamOpen ? (
                <TeamDiscoveryPanel
                  teamState={teamState}
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
