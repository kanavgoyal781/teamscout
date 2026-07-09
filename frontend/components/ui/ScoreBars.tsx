"use client";

import { motion, useReducedMotion } from "framer-motion";

import type { ScoreBreakdown } from "../../lib/types";
import { formatScoreDecimal, toPercent } from "../../lib/format";
import { easeOut } from "../../lib/motion";

type ScoreBarsProps = {
  breakdown: ScoreBreakdown;
  /**
   * jobs (default): llm_fit / rrf / skill / recency
   * resumes: llm_fit / rrf / skill / experience_fit (backend sets recency=0 for F2)
   */
  variant?: "jobs" | "resumes";
};

type Row = { key: keyof ScoreBreakdown; label: string; isPercent: boolean };

const JOB_ROWS: Row[] = [
  { key: "llm_fit", label: "LLM fit", isPercent: true },
  { key: "rrf_normalized", label: "RRF", isPercent: false },
  { key: "skill_jaccard", label: "Skill", isPercent: false },
  { key: "recency", label: "Recency", isPercent: false },
];

const RESUME_ROWS: Row[] = [
  { key: "llm_fit", label: "LLM fit", isPercent: true },
  { key: "rrf_normalized", label: "RRF", isPercent: false },
  { key: "skill_jaccard", label: "Skill", isPercent: false },
  { key: "experience_fit", label: "Experience", isPercent: false },
];

function resolveRows(breakdown: ScoreBreakdown, variant?: "jobs" | "resumes"): Row[] {
  if (variant === "resumes") return RESUME_ROWS;
  if (variant === "jobs") return JOB_ROWS;
  // Auto: when experience_fit is present and recency is empty, treat as resume ranking
  const exp = breakdown.experience_fit;
  if (exp != null && Number.isFinite(exp) && (!breakdown.recency || breakdown.recency === 0)) {
    return RESUME_ROWS;
  }
  return JOB_ROWS;
}

export default function ScoreBars({ breakdown, variant }: ScoreBarsProps) {
  const reduced = useReducedMotion();
  const rows = resolveRows(breakdown, variant);

  return (
    <div className="breakdown-bars" role="list" aria-label="Score breakdown">
      {rows.map((row) => {
        const raw = breakdown[row.key];
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
    </div>
  );
}
