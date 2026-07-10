"use client";

import { useId } from "react";

import { DETAIL_PANEL_ID, FUNNEL_STEPS, SCORE_BARS, SCORE_WEIGHTS, pct, type DetailKey } from "./details";

type Props = {
  selected: DetailKey;
  onSelect: (k: Exclude<DetailKey, null>, el: HTMLElement | null) => void;
};

export default function RankingFunnelDiagram({ selected, onSelect }: Props) {
  const uid = useId();

  const formulaText = `final = 100 × (
  ${SCORE_WEIGHTS.llm.toFixed(2)} × (llm_fit / 100)
+ ${SCORE_WEIGHTS.rrf.toFixed(2)} × rrf_normalized
+ ${SCORE_WEIGHTS.skills.toFixed(2)} × skill_jaccard
+ ${SCORE_WEIGHTS.experience.toFixed(2)} × experience_fit
+ ${SCORE_WEIGHTS.requirements.toFixed(2)} × requirements_met
+ ${SCORE_WEIGHTS.recency.toFixed(2)} × recency
+ optional cross_encoder × ce_normalized  // default weight 0
)`;

  return (
    <div className="about-funnel-diagram" data-testid="ranking-funnel-diagram">
      <svg viewBox="0 0 720 120" className="about-funnel-svg" aria-hidden>
        <defs>
          <linearGradient id={`${uid}-funnel`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#5b8def" stopOpacity="0.35" />
            <stop offset="50%" stopColor="#c084fc" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#3dd68c" stopOpacity="0.35" />
          </linearGradient>
        </defs>
        <polygon
          points="20,20 700,40 700,80 20,100"
          fill={`url(#${uid}-funnel)`}
          stroke="#3a4154"
          strokeWidth="1"
        />
        <text x="40" y="66" fill="#eceef4" fontSize="12" fontFamily="var(--font-mono)">
          150+ → RRF → CE(opt) → LLM → fuse → MMR top 10
        </text>
      </svg>

      <div className="about-funnel-flow" role="list">
        {FUNNEL_STEPS.map((step, i) => {
          const active = selected === step.key;
          return (
            <div key={step.key} className="about-funnel-item" role="listitem">
              <button
                type="button"
                className={`about-funnel-node pressable${active ? " is-active" : ""}`}
                style={{ ["--funnel-c" as string]: step.hue }}
                onClick={(e) => onSelect(step.key, e.currentTarget)}
                aria-expanded={active}
                aria-controls={active ? DETAIL_PANEL_ID : undefined}
              >
                <span className="about-funnel-num font-num">{String(i + 1).padStart(2, "0")}</span>
                <strong>{step.title}</strong>
                <span className="meta">{step.short}</span>
              </button>
              {i < FUNNEL_STEPS.length - 1 ? (
                <div className="about-funnel-arrow" aria-hidden>
                  →
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <h3 className="about-score-heading">Score formula</h3>
      <pre className="formula about-formula" aria-label="Score formula">
        {formulaText}
      </pre>
      <div className="about-weight-row" role="group" aria-label="Score weight breakdown">
        {SCORE_BARS.map((b) => {
          const active = selected === b.id;
          const w = pct(b.weight);
          return (
            <button
              key={b.id}
              type="button"
              className={`about-weight pressable${active ? " is-active" : ""}`}
              style={{ flex: w, ["--weight-c" as string]: b.c }}
              onClick={(e) => onSelect(b.id, e.currentTarget)}
              aria-expanded={active}
              aria-controls={active ? DETAIL_PANEL_ID : undefined}
            >
              <span className="font-num">{w}</span>
              <span>{b.label}</span>
            </button>
          );
        })}
      </div>
      <p className="meta about-diagram-tradeoff">
        Tradeoff: LLM fit dominates the number so prompts stay versioned and eval-gated; RRF alone
        cannot enforce YOE honesty.
      </p>
    </div>
  );
}
