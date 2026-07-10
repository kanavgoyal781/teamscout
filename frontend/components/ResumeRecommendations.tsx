"use client";

import { motion, useReducedMotion } from "framer-motion";

import type { RankedResumeRecommendation } from "../lib/types";
import { easeOut, shouldSkipEntrance, staggerContainer, staggerItem } from "../lib/motion";
import EmptyState from "./ui/EmptyState";
import { JobCardSkeleton } from "./ui/Skeleton";
import ScoreBars from "./ui/ScoreBars";
import ScoreRing from "./ui/ScoreRing";
import FeedbackButtons from "./FeedbackButtons";

type ResumeRecommendationsProps = {
  /** True after paste-JD match completed (including zero results). */
  searched?: boolean;
  recommending: boolean;
  recommendations: RankedResumeRecommendation[];
  jdTitle?: string;
  jdCompany?: string;
  jdHash?: string | null;
  tournamentRan?: boolean;
  tournamentComparisons?: number;
};

/** Strip internal weight markers like (w=2.0) from tournament reasons. */
export function stripWeightNotation(text: string): string {
  return text.replace(/\s*\(w=\d+(?:\.\d+)?\)/g, "").trim();
}

/**
 * Display hygiene for tournament reasons.
 * Backend already materializes pair-local A/B → filenames (with random flip);
 * do NOT remap A/B by final rank order — that would mislabel flip-local pairs.
 * Only strip internal weight notation for residual display cleanliness.
 */
export function materializeTournamentReason(reason: string): string {
  return stripWeightNotation(reason || "");
}

function highlightCited(text: string, phrases: string[]): React.ReactNode {
  if (!text || phrases.length === 0) return text;
  const escaped = phrases
    .filter(Boolean)
    .map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .filter((p) => p.length > 2);
  if (escaped.length === 0) return text;
  const splitRe = new RegExp(`(${escaped.join("|")})`, "i");
  const parts = text.split(splitRe);
  return parts.map((part, i) => {
    const isMatch = escaped.some((p) => new RegExp(`^${p}$`, "i").test(part));
    return isMatch ? (
      <mark key={i} className="cited">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    );
  });
}

function evidenceCell(status: string, evidence: string | null | undefined): string {
  if (status === "miss" || !evidence || evidence === "No clear evidence") {
    return "No clear evidence";
  }
  return evidence;
}

export default function ResumeRecommendations({
  searched = false,
  recommending,
  recommendations,
  jdTitle = "",
  jdCompany = "",
  jdHash = null,
  tournamentRan = false,
  tournamentComparisons = 0,
}: ResumeRecommendationsProps) {
  const reduced = useReducedMotion();
  const skipEntrance = shouldSkipEntrance(reduced);
  const recsHeading = "3. Best resumes for this job";
  const showRecs = searched || recommending || recommendations.length > 0;
  const tournamentOverrode = recommendations.some(
    (r) => r.tournament?.ran && r.tournament.overrode_coverage,
  );

  if (showRecs && recommending) {
    return (
      <section className="panel" data-testid="recommendations-loading">
        <h2>{recsHeading}</h2>
        <div className="recommendation-list">
          <JobCardSkeleton />
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      </section>
    );
  }

  if (showRecs && recommendations.length > 0) {
    return (
      <section className="panel" data-testid="recommendations">
        <h2>{recsHeading}</h2>
        {jdTitle || jdCompany ? (
          <p className="meta" style={{ marginTop: 0 }}>
            For <strong>{jdTitle || "pasted job"}</strong>
            {jdCompany ? ` · ${jdCompany}` : ""}
          </p>
        ) : null}
        {tournamentRan ? (
          <p className="meta font-num" data-testid="tournament-cost">
            Close-call tournament: {tournamentComparisons} pairwise comparison
            {tournamentComparisons === 1 ? "" : "s"} (logged to ops traces)
          </p>
        ) : null}
        {tournamentOverrode ? (
          <p className="meta" data-testid="tournament-override-badge" style={{ marginTop: 4 }}>
            <span
              className="chip"
              title="Coverage scores were close; a pairwise LLM tournament reordered the card list. Coverage and the Overall match ring both remain MaxSim requirement coverage (the #1 contested winner may get a +1 ring nudge). Tournament does not recompute a separate overall score."
            >
              Ranked by close-call tournament
            </span>
          </p>
        ) : null}
        <motion.div
          className="recommendation-list"
          variants={skipEntrance ? undefined : staggerContainer}
          initial={skipEntrance ? undefined : "hidden"}
          animate={skipEntrance ? undefined : "show"}
        >
          {recommendations.slice(0, 3).map((item, index) => {
            const isWinner = index === 0;
            const align = item.alignment?.length ? item.alignment : null;
            const citePhrases = (
              align
                ? align
                    .filter((c) => c.status === "hit" && c.evidence_unit && c.evidence_unit !== "No clear evidence")
                    .map((c) => c.evidence_unit as string)
                : item.coverage
                    .filter((c) => c.status === "hit" && c.evidence && c.evidence !== "No clear evidence")
                    .map((c) => c.evidence as string)
            ).slice(0, 6);
            const reasonRaw = item.tournament?.reasons?.[0]
              ? materializeTournamentReason(item.tournament.reasons[0])
              : "";
            return (
              <motion.article
                key={item.resume_id}
                className={`recommendation-card${isWinner ? " winner" : ""}`}
                variants={skipEntrance ? undefined : staggerItem}
                transition={easeOut}
                data-testid={`recommendation-${index}`}
              >
                {isWinner ? <span className="winner-label">Best match</span> : null}
                <div className="job-card-header">
                  <div>
                    <h3 style={{ margin: 0 }}>
                      <span className="rank-badge font-num">#{index + 1}</span>
                      {item.filename}
                    </h3>
                    {item.cluster_label ? (
                      <p className="meta" style={{ margin: "4px 0 0" }} data-testid={`cluster-${index}`}>
                        {item.cluster_label}
                        {item.cluster_size && item.cluster_size > 1
                          ? ` · cluster of ${item.cluster_size}`
                          : ""}
                      </p>
                    ) : null}
                    {typeof item.coverage_score === "number" ? (
                      <p className="meta font-num" style={{ margin: "4px 0 0" }} data-testid={`coverage-label-${index}`}>
                        Coverage {(item.coverage_score * 100).toFixed(0)}%
                      </p>
                    ) : null}
                  </div>
                  <ScoreRing score={item.match_score} size={48} label="Overall match" />
                </div>
                <p className="rationale">
                  {highlightCited(item.score_breakdown.rationale, citePhrases)}
                </p>
                {item.tournament?.ran && item.tournament.contested ? (
                  <p className="meta font-num" data-testid={`tournament-${index}`}>
                    Tournament: {item.tournament.wins} win
                    {item.tournament.wins === 1 ? "" : "s"}
                    {reasonRaw ? ` — ${reasonRaw}` : ""}
                  </p>
                ) : null}
                <ScoreBars
                  breakdown={item.score_breakdown}
                  variant="resumes"
                  coverageScore={item.coverage_score ?? null}
                />
                <div className="actions" style={{ marginTop: 10 }}>
                  <FeedbackButtons
                    targetType="resume_pick"
                    targetId={item.resume_id}
                    profileHash={item.content_hash ?? null}
                    secondaryId={item.content_hash ?? null}
                    jdHash={jdHash}
                    scoreShown={item.match_score}
                    testIdPrefix={`resume-feedback-${index}`}
                  />
                </div>
                <div className="chip-row">
                  {item.score_breakdown.matched_skills.map((skill) => (
                    <span key={`m-${item.resume_id}-${skill}`} className="chip chip-match">
                      {skill}
                    </span>
                  ))}
                  {item.score_breakdown.missing_skills.map((skill) => (
                    <span key={`x-${item.resume_id}-${skill}`} className="chip chip-gap">
                      {skill}
                    </span>
                  ))}
                </div>
                {align ? (
                  <table className="coverage-table" data-testid={`alignment-${index}`}>
                    <thead>
                      <tr>
                        <th>Requirement</th>
                        <th>Kind</th>
                        <th>Score</th>
                        <th>Best evidence unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {align.map((row) => (
                        <tr key={`${item.resume_id}-${row.requirement}`}>
                          <td>{row.requirement}</td>
                          <td className="meta">{row.kind}</td>
                          <td
                            className={
                              row.status === "hit" ? "coverage-hit font-num" : "coverage-miss font-num"
                            }
                          >
                            {(row.evidence_score * 100).toFixed(0)}%
                          </td>
                          <td className={row.status === "miss" ? "coverage-miss" : undefined}>
                            {evidenceCell(row.status, row.evidence_unit)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : item.coverage.length > 0 ? (
                  <table className="coverage-table">
                    <thead>
                      <tr>
                        <th>Requirement</th>
                        <th>Status</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {item.coverage.map((row) => (
                        <tr key={`${item.resume_id}-${row.requirement}`}>
                          <td>{row.requirement}</td>
                          <td className={row.status === "hit" ? "coverage-hit" : "coverage-miss"}>
                            {row.status === "hit" ? "✓" : "✗"}
                          </td>
                          <td className={row.status === "miss" ? "coverage-miss" : undefined}>
                            {evidenceCell(row.status, row.evidence)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : null}
              </motion.article>
            );
          })}
        </motion.div>
      </section>
    );
  }

  if (searched && !recommending && recommendations.length === 0) {
    return (
      <section className="panel" data-testid="recommendations-empty">
        <EmptyState instruction="No resume recommendations for this job. Add more resumes to the library." />
      </section>
    );
  }

  return null;
}
