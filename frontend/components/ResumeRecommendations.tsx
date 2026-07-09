"use client";

import { motion, useReducedMotion } from "framer-motion";

import type { RankedResumeRecommendation } from "../lib/types";
import { easeOut, shouldSkipEntrance, staggerContainer, staggerItem } from "../lib/motion";
import EmptyState from "./ui/EmptyState";
import { JobCardSkeleton } from "./ui/Skeleton";
import ScoreBars from "./ui/ScoreBars";
import ScoreRing from "./ui/ScoreRing";

type ResumeRecommendationsProps = {
  /** True after paste-JD match completed (including zero results). */
  searched?: boolean;
  recommending: boolean;
  recommendations: RankedResumeRecommendation[];
  jdTitle?: string;
  jdCompany?: string;
};

function highlightCited(text: string, phrases: string[]): React.ReactNode {
  if (!text || phrases.length === 0) return text;
  const escaped = phrases
    .filter(Boolean)
    .map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .filter((p) => p.length > 2);
  if (escaped.length === 0) return text;
  // Case-insensitive split without /g so lastIndex cannot skip marks
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

export default function ResumeRecommendations({
  searched = false,
  recommending,
  recommendations,
  jdTitle = "",
  jdCompany = "",
}: ResumeRecommendationsProps) {
  const reduced = useReducedMotion();
  const skipEntrance = shouldSkipEntrance(reduced);
  const recsHeading = "3. Best resumes for this job";
  const showRecs = searched || recommending || recommendations.length > 0;

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
        <motion.div
          className="recommendation-list"
          variants={skipEntrance ? undefined : staggerContainer}
          initial={skipEntrance ? undefined : "hidden"}
          animate={skipEntrance ? undefined : "show"}
        >
          {recommendations.slice(0, 3).map((item, index) => {
            const isWinner = index === 0;
            const citePhrases = item.coverage
              .filter((c) => c.status === "hit" && c.evidence)
              .map((c) => c.evidence as string)
              .slice(0, 6);
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
                  </div>
                  <ScoreRing score={item.match_score} size={48} />
                </div>
                <p className="rationale">
                  {highlightCited(item.score_breakdown.rationale, citePhrases)}
                </p>
                <ScoreBars breakdown={item.score_breakdown} variant="resumes" />
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
                {item.coverage.length > 0 ? (
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
                          <td>{row.evidence ?? "—"}</td>
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
