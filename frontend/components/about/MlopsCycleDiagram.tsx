"use client";

import { useId } from "react";

import { DETAIL_PANEL_ID, type DetailKey } from "./details";

type Props = {
  selected: DetailKey;
  onSelect: (k: Exclude<DetailKey, null>, el: HTMLElement | null) => void;
};

const NODES = [
  { id: "mlops_evals" as const, label: "Eval floors", x: 210, y: 36, c: "var(--accent)" },
  { id: "mlops_traces" as const, label: "Traces", x: 340, y: 150, c: "var(--accent)" },
  { id: "mlops_ceilings" as const, label: "Ceilings", x: 80, y: 150, c: "var(--warning)" },
] as const;

export default function MlopsCycleDiagram({ selected, onSelect }: Props) {
  const uid = useId();

  return (
    <div className="about-mlops-cycle" data-testid="mlops-cycle-diagram">
      {/* Canvas only — captions stay outside absolute node overlay */}
      <div className="about-mlops-canvas">
        <svg viewBox="0 0 420 240" className="about-mlops-svg" aria-hidden>
          <defs>
            <marker id={`${uid}-arr`} markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="var(--border-strong)" />
            </marker>
          </defs>
          <circle cx="210" cy="120" r="88" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" strokeDasharray="6 4" />
          <path
            d="M210 32 A88 88 0 0 1 298 150"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            markerEnd={`url(#${uid}-arr)`}
            opacity="0.7"
          />
          <path
            d="M298 150 A88 88 0 0 1 122 150"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            markerEnd={`url(#${uid}-arr)`}
            opacity="0.7"
          />
          <path
            d="M122 150 A88 88 0 0 1 210 32"
            fill="none"
            stroke="var(--warning)"
            strokeWidth="2"
            markerEnd={`url(#${uid}-arr)`}
            opacity="0.7"
          />
          <text x="210" y="124" textAnchor="middle" fill="var(--text-muted)" fontSize="12" fontFamily="var(--font-mono)">
            learn → ship → observe
          </text>
        </svg>
        <div className="about-mlops-nodes">
          {NODES.map((n) => {
            const active = selected === n.id;
            return (
              <button
                key={n.id}
                type="button"
                className={`about-mlops-node pressable${active ? " is-active" : ""}`}
                style={{
                  left: `${(n.x / 420) * 100}%`,
                  top: `${(n.y / 240) * 100}%`,
                  ["--node-c" as string]: n.c,
                }}
                onClick={(e) => onSelect(n.id, e.currentTarget)}
                aria-expanded={active}
                aria-controls={active ? DETAIL_PANEL_ID : undefined}
                data-testid={`about-mlops-node-${n.id}`}
              >
                {n.label}
              </button>
            );
          })}
        </div>
      </div>
      <p className="meta about-diagram-tradeoff">
        Tradeoff: offline JSONL history + CI gates instead of a remote experiment platform — enough
        for two features without a second data platform.
      </p>
    </div>
  );
}
