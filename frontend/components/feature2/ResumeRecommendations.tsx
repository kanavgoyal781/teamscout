"use client";

import { motion, useReducedMotion } from "framer-motion";

import type { AdversarialCritique, RankedResumeRecommendation } from "../../lib/types";
import { middleTruncate } from "../../lib/format";
import { easeOut, shouldSkipEntrance, staggerContainer, staggerItem } from "../../lib/motion";
import EmptyState from "../ui/EmptyState";
import { JobCardSkeleton } from "../ui/Skeleton";
import ScoreBars from "../ui/ScoreBars";
import ScoreRing from "../ui/ScoreRing";
import FeedbackButtons from "../feedback/FeedbackButtons";

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
  judgeAgreementLabel?: string | null;
  adversarialCritique?: AdversarialCritique | null;
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

function evidenceCell(status: string, evidence: string | null | undefined): string {
  if (status === "miss" || !evidence || evidence === "No clear evidence") {
    return "No clear evidence";
  }
  return evidence;
}

function strengthFromScore(score: number | undefined, status: string): "none" | "weak" | "solid" | "strong" {
  if (status === "miss" || score == null || score <= 0) return "none";
  if (score < 0.35) return "weak";
  if (score < 0.7) return "solid";
  return "strong";
}

function StrengthBar({ strength }: { strength: "none" | "weak" | "solid" | "strong" }) {
  const fill = { none: 0, weak: 33, solid: 66, strong: 100 }[strength];
  return (
    <span className="strength-bar" data-strength={strength} title={strength} aria-label={`Strength ${strength}`}>
      <span className="strength-bar-track" aria-hidden>
        <span className="strength-bar-fill" style={{ width: `${fill}%` }} />
      </span>
      <span className="strength-bar-label meta">{strength}</span>
    </span>
  );
}

function coverageLabel(item: RankedResumeRecommendation): string {
  if (typeof item.must_haves_total === "number" && item.must_haves_total > 0) {
    const hit = item.must_haves_hit ?? 0;
    return `${hit} of ${item.must_haves_total} must-haves evidenced`;
  }
  if (typeof item.coverage_score === "number") {
    // Fallback only when must-have counts absent
    return `Coverage ${Math.round(item.coverage_score * 100)}%`;
  }
  return "";
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

export default function ResumeRecommendations({
  searched = false,
  recommending,
  recommendations,
  jdTitle = "",
  jdCompany = "",
  jdHash = null,
  tournamentRan = false,
  tournamentComparisons = 0,
  judgeAgreementLabel = null,
  adversarialCritique = null,
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
            {judgeAgreementLabel ? (
              <span data-testid="judge-agreement"> · {judgeAgreementLabel}</span>
            ) : null}
          </p>
        ) : null}
        {tournamentOverrode ? (
          <p className="meta" data-testid="tournament-override-badge" style={{ marginTop: 4 }}>
            <span
              className="chip"
              title="Coverage scores were close; a pairwise LLM tournament reordered the list. Overall match is always the weighted final blend (not adjusted to force non-increasing rings). Must-haves show as X of N evidenced."
            >
              Ranked by close-call tournament
            </span>
          </p>
        ) : null}
        {adversarialCritique ? (
          <section
            className="card head-to-head"
            data-testid="head-to-head"
            aria-labelledby="head-to-head-title"
            tabIndex={0}
          >
            <h3 id="head-to-head-title" className="section-title" style={{ marginTop: 0 }}>
              Head-to-head
            </h3>
            <p className="meta" style={{ marginTop: 0 }}>
              Adversarial advocates for the final top-2 (grounded in alignment evidence only).
            </p>
            <div className="head-to-head-columns" role="group" aria-label="Advocate arguments">
              <article className="head-to-head-col" data-testid="advocate-a">
                <h4 className="label-caps">{adversarialCritique.side_a_filename}</h4>
                <p className="meta font-num">{adversarialCritique.side_a_model}</p>
                <p>{adversarialCritique.side_a_argument}</p>
              </article>
              <article className="head-to-head-col" data-testid="advocate-b">
                <h4 className="label-caps">{adversarialCritique.side_b_filename}</h4>
                <p className="meta font-num">{adversarialCritique.side_b_model}</p>
                <p>{adversarialCritique.side_b_argument}</p>
              </article>
            </div>
            <div
              className="head-to-head-verdict"
              data-testid="head-to-head-verdict"
              role="status"
              aria-live="polite"
            >
              <strong>Verdict: {adversarialCritique.verdict_winner_filename}</strong>
              <span className="meta font-num"> · judge {adversarialCritique.verdict_model}</span>
              <p style={{ margin: "6px 0 0" }}>{adversarialCritique.verdict_reason}</p>
            </div>
          </section>
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
                  <div className="job-card-copy">
                    <h3 style={{ margin: 0 }}>
                      <span className="rank-badge font-num" aria-label={`Rank ${index + 1}`}>
                        #{index + 1}
                      </span>
                      <span className="filename-trunc" title={item.filename}>
                        {middleTruncate(item.filename)}
                      </span>
                    </h3>
                    {/* One quiet metadata line: coverage + cluster + tournament — score ring is sole hero */}
                    <p className="meta card-meta-line font-num" data-testid={`card-meta-${index}`}>
                      <span data-testid={`coverage-label-${index}`}>
                        {[
                          coverageLabel(item) || null,
                          item.cluster_label
                            ? `${item.cluster_label}${item.cluster_size && item.cluster_size > 1 ? ` · cluster of ${item.cluster_size}` : ""}`
                            : null,
                          item.tournament?.ran && item.tournament.contested
                            ? `Tournament ${item.tournament.wins} win${item.tournament.wins === 1 ? "" : "s"}${reasonRaw ? ` — ${reasonRaw}` : ""}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                      {item.tournament?.ran && item.tournament.contested ? (
                        <span className="sr-only" data-testid={`tournament-${index}`}>
                          Tournament: {item.tournament.wins} wins
                        </span>
                      ) : null}
                    </p>
                  </div>
                  <ScoreRing score={item.match_score} size={52} />
                </div>
                <p className="rationale line-clamp-2">
                  {highlightCited(item.score_breakdown.rationale, citePhrases)}
                </p>
                <ScoreBars
                  breakdown={item.score_breakdown}
                  variant="resumes"
                  coverageScore={item.coverage_score ?? null}
                  mustHavesHit={item.must_haves_hit}
                  mustHavesTotal={item.must_haves_total}
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
                  <div className="coverage-table-scroll">
                    <table className="coverage-table" data-testid={`alignment-${index}`}>
                      <thead>
                        <tr>
                          <th className="col-req">Requirement</th>
                          <th className="col-kind">Kind</th>
                          <th className="col-strength">Strength</th>
                          <th className="col-evidence">Best evidence unit</th>
                        </tr>
                      </thead>
                      <tbody>
                        {align.map((row) => {
                          const strength =
                            row.strength ?? strengthFromScore(row.evidence_score, row.status);
                          return (
                            <tr key={`${item.resume_id}-${row.requirement}`}>
                              <td className="col-req">
                                <span className="line-clamp-2" title={row.requirement}>
                                  {row.requirement}
                                </span>
                              </td>
                              <td className="col-kind meta">{row.kind}</td>
                              <td className="col-strength font-num">
                                <StrengthBar strength={strength} />
                              </td>
                              <td className="col-evidence">
                                <span className="line-clamp-2" title={evidenceCell(row.status, row.evidence_unit)}>
                                  {evidenceCell(row.status, row.evidence_unit)}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : item.coverage.length > 0 ? (
                  <div className="coverage-table-scroll">
                    <table className="coverage-table">
                      <thead>
                        <tr>
                          <th className="col-req">Requirement</th>
                          <th className="col-kind">Status</th>
                          <th className="col-evidence">Evidence</th>
                        </tr>
                      </thead>
                      <tbody>
                        {item.coverage.map((row) => (
                          <tr key={`${item.resume_id}-${row.requirement}`}>
                            <td className="col-req">
                              <span className="line-clamp-2" title={row.requirement}>
                                {row.requirement}
                              </span>
                            </td>
                            <td className={`col-kind font-num ${row.status === "hit" ? "coverage-hit" : "coverage-miss"}`}>
                              {row.status === "hit" ? "✓" : "✗"}
                            </td>
                            <td className="col-evidence">
                              <span className="line-clamp-2">{row.evidence ?? "—"}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
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
