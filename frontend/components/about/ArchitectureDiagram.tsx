"use client";

import { useId } from "react";

import { DETAIL_PANEL_ID, type DetailKey } from "./details";

type Props = {
  selected: DetailKey;
  onSelect: (k: Exclude<DetailKey, null>, el: HTMLElement | null) => void;
};

const NODES = [
  { id: "browser" as const, label: "Browser", sub: "Next.js UI", x: "4%", y: "10%", c: "#5b8def" },
  { id: "api" as const, label: "FastAPI", sub: "Single process", x: "28%", y: "10%", c: "#3dd68c" },
  { id: "sqlite" as const, label: "SQLite", sub: "State + traces", x: "28%", y: "55%", c: "#e8b84a" },
  { id: "llm" as const, label: "LLM", sub: "Parse · rerank", x: "60%", y: "2%", c: "#c084fc" },
  { id: "emb" as const, label: "Embeddings", sub: "Dense retrieval", x: "60%", y: "22%", c: "#22d3ee" },
  { id: "jsearch" as const, label: "Jobs", sub: "Multi-source", x: "60%", y: "42%", c: "#f472b6" },
  { id: "sumble" as const, label: "Hiring team", sub: "People + email", x: "60%", y: "62%", c: "#fb923c" },
  { id: "drive" as const, label: "Drive", sub: "Optional library", x: "60%", y: "82%", c: "#94a3b8", optional: true },
] as const;

export default function ArchitectureDiagram({ selected, onSelect }: Props) {
  const uid = useId();

  return (
    <div className="about-diagram" role="group" aria-label="TeamScout system architecture">
      {/* Canvas only: absolute nodes must not overlay captions below */}
      <div className="about-diagram-canvas">
        <svg viewBox="0 0 920 360" className="about-svg" aria-hidden>
          <defs>
            <linearGradient id={`${uid}-g1`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#c4a35a" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#5b8def" stopOpacity="0.04" />
            </linearGradient>
            <marker id={`${uid}-arrow`} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#3a4154" />
            </marker>
          </defs>
          <rect x="0" y="0" width="920" height="360" rx="4" fill={`url(#${uid}-g1)`} />
          <g stroke="#3a4154" strokeWidth="1.5" fill="none" markerEnd={`url(#${uid}-arrow)`} opacity="0.85">
            <path d="M170,70 L250,70" />
            <path d="M410,70 L520,30" />
            <path d="M410,70 L520,80" />
            <path d="M410,70 L520,130" />
            <path d="M410,90 L520,200" />
            <path d="M410,90 L520,255" />
            {/* Drive: single dashed edge only (optional) */}
            <path d="M410,90 L520,320" strokeDasharray="5 4" />
            <path d="M330,100 L330,200" />
          </g>
        </svg>

        <div className="about-diagram-nodes">
          {NODES.map((n) => {
            const active = selected === n.id;
            return (
              <button
                key={n.id}
                type="button"
                className={`about-node pressable${active ? " is-active" : ""}${
                  "optional" in n && n.optional ? " is-optional" : ""
                }`}
                style={{ left: n.x, top: n.y, ["--node-c" as string]: n.c }}
                onClick={(e) => onSelect(n.id, e.currentTarget)}
                aria-expanded={active}
                aria-controls={active ? DETAIL_PANEL_ID : undefined}
              >
                <strong>{n.label}</strong>
                <span>{n.sub}</span>
              </button>
            );
          })}
        </div>
      </div>

      <p className="meta about-diagram-caption font-num">
        Browser (Next.js) → FastAPI → services → SQLite + external APIs
      </p>
      <p className="meta about-diagram-tradeoff">
        Tradeoff: one process and one file store keep failure modes small; multi-writer SaaS scale is
        out of scope. Dashed edge = optional Drive.
      </p>
    </div>
  );
}
