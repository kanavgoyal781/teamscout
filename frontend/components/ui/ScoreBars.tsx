"use client";

import { motion, useReducedMotion } from "framer-motion";

import type { ScoreBreakdown } from "../../lib/types";
import { formatScoreDecimal, toPercent } from "../../lib/format";
import { easeOut } from "../../lib/motion";

type ScoreBarsProps = {
  breakdown: ScoreBreakdown;
  /**
   * jobs (default): llm / rrf / skill / experience / requirements / recency
   * resumes: coverage (MaxSim) / llm / skill / experience — not RRF
   */
  variant?: "jobs" | "resumes";
  /** MaxSim coverage 0–1 for resume cards (authoritative; not rrf_normalized). */
  coverageScore?: number | null;
  /** Prefer "X of N must-haves" over rescaled coverage % on resume cards. */
  mustHavesHit?: number | null;
  mustHavesTotal?: number | null;
};

type Row = { key: keyof ScoreBreakdown; label: string; isPercent: boolean };

const JOB_ROWS: Row[] = [
  { key: "llm_fit", label: "LLM fit", isPercent: true },
  { key: "cross_encoder", label: "Cross-enc", isPercent: false },
  { key: "rrf_normalized", label: "RRF", isPercent: false },
  { key: "skill_jaccard", label: "Skill", isPercent: false },
  { key: "experience_fit", label: "Experience", isPercent: false },
  { key: "requirements_met", label: "Requirements", isPercent: false },
  { key: "recency", label: "Recency", isPercent: false },
];

const RESUME_ROWS: Row[] = [
  { key: "llm_fit", label: "LLM fit", isPercent: true },
  { key: "skill_jaccard", label: "Skill", isPercent: false },
  { key: "experience_fit", label: "Experience", isPercent: false },
];

function resolveRows(breakdown: ScoreBreakdown, variant?: "jobs" | "resumes"): Row[] {
  if (variant === "resumes") return RESUME_ROWS;
  if (variant === "jobs") return JOB_ROWS;
  const exp = breakdown.experience_fit;
  if (exp != null && Number.isFinite(exp) && (!breakdown.recency || breakdown.recency === 0)) {
    return RESUME_ROWS;
  }
  return JOB_ROWS;
}

export default function ScoreBars({
  breakdown,
  variant,
  coverageScore,
  mustHavesHit,
  mustHavesTotal,
}: ScoreBarsProps) {
  const reduced = useReducedMotion();
  const rows = resolveRows(breakdown, variant);
  const softBoost =
    typeof breakdown.soft_boost === "number" && breakdown.soft_boost > 0
      ? breakdown.soft_boost
      : 0;
  // Soft prefs are absolute points (typically 5–20), not a 0–1 fraction.
  const softPct = Math.min(100, Math.max(0, (softBoost / 20) * 100));
  const showMustHaves =
    variant === "resumes" &&
    typeof mustHavesTotal === "number" &&
    mustHavesTotal > 0 &&
    Number.isFinite(mustHavesTotal);
  const mustPct = showMustHaves
    ? Math.min(100, Math.max(0, ((mustHavesHit ?? 0) / (mustHavesTotal as number)) * 100))
    : 0;
  const showCoverage =
    !showMustHaves &&
    variant === "resumes" &&
    typeof coverageScore === "number" &&
    Number.isFinite(coverageScore);
  const covPct = showCoverage ? toPercent(coverageScore as number, false) : 0;

  return (
    <div className="breakdown-bars" role="list" aria-label="Score breakdown">
      {showMustHaves ? (
        <div key="must-haves" className="breakdown-row" role="listitem">
          <span>Must-haves</span>
          <div className="breakdown-track" aria-hidden>
            <motion.div
              className="breakdown-fill"
              initial={reduced ? { width: `${mustPct}%` } : { width: 0 }}
              animate={{ width: `${mustPct}%` }}
              transition={reduced ? { duration: 0 } : { ...easeOut, duration: 0.22 }}
            />
          </div>
          <span className="breakdown-val font-num">
            {mustHavesHit ?? 0}/{mustHavesTotal}
          </span>
        </div>
      ) : null}
      {showCoverage ? (
        <div key="coverage" className="breakdown-row" role="listitem">
          <span>Coverage</span>
          <div className="breakdown-track" aria-hidden>
            <motion.div
              className="breakdown-fill"
              initial={reduced ? { width: `${covPct}%` } : { width: 0 }}
              animate={{ width: `${covPct}%` }}
              transition={reduced ? { duration: 0 } : { ...easeOut, duration: 0.22 }}
            />
          </div>
          <span className="breakdown-val font-num">
            {formatScoreDecimal(coverageScore as number, 2)}
          </span>
        </div>
      ) : null}
      {rows.map((row) => {
        const raw = breakdown[row.key];
        if (raw == null && row.key !== "llm_fit" && row.key !== "skill_jaccard") return null;
        // Hide unused cross-encoder bar when CE stage is off / score is zero
        if (row.key === "cross_encoder" && (raw == null || raw === 0)) return null;
        // Always show skill on resume cards (0 is a real miss when JD lists skills)
        const value = typeof raw === "number" ? raw : 0;
        const pct = toPercent(value, row.isPercent);
        return (
          <div key={row.key} className="breakdown-row" role="listitem">
            <span>{row.label}</span>
            <div className="breakdown-track" aria-hidden>
              <motion.div
                className="breakdown-fill"
                initial={reduced ? { width: `${pct}%` } : { width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={reduced ? { duration: 0 } : { ...easeOut, duration: 0.22 }}
              />
            </div>
            <span className="breakdown-val font-num">
              {row.isPercent ? Math.round(value) : formatScoreDecimal(value, 2)}
            </span>
          </div>
        );
      })}
      {softBoost > 0 && variant !== "resumes" ? (
        <div key="soft_boost" className="breakdown-row" role="listitem">
          <span>Prefer boost</span>
          <div className="breakdown-track" aria-hidden>
            <motion.div
              className="breakdown-fill"
              initial={reduced ? { width: `${softPct}%` } : { width: 0 }}
              animate={{ width: `${softPct}%` }}
              transition={reduced ? { duration: 0 } : { ...easeOut, duration: 0.22 }}
            />
          </div>
          <span className="breakdown-val font-num">+{formatScoreDecimal(softBoost, 1)}</span>
        </div>
      ) : null}
    </div>
  );
}
