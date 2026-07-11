"use client";

import { DETAIL_PANEL_ID, type DetailKey } from "./details";

type Props = {
  selected: DetailKey;
  onSelect: (k: Exclude<DetailKey, null>, el: HTMLElement | null) => void;
};

type NodeDef = {
  id: Exclude<DetailKey, null>;
  label: string;
  sub: string;
  c: string;
  optional?: boolean;
  /** Named CSS grid-template-areas token (e.g. "browser", "api") */
  area: string;
};

/**
 * Layout is pure CSS grid in normal document flow.
 * Captions sit AFTER the grid — never under absolute-positioned nodes.
 *
 *   Browser → FastAPI ─┬→ LLM
 *              │       ├→ Embeddings
 *              ↓       ├→ Jobs
 *            SQLite    ├→ Hiring team
 *                      └→ Drive (optional, dashed)
 */
const NODES: NodeDef[] = [
  { id: "browser", label: "Browser", sub: "Next.js UI", c: "#5b8def", area: "browser" },
  { id: "api", label: "FastAPI", sub: "Single process", c: "#3dd68c", area: "api" },
  { id: "sqlite", label: "SQLite", sub: "State + traces", c: "#e8b84a", area: "sqlite" },
  { id: "llm", label: "LLM", sub: "Parse · rerank", c: "#c084fc", area: "llm" },
  { id: "emb", label: "Embeddings", sub: "Dense retrieval", c: "#22d3ee", area: "emb" },
  { id: "jsearch", label: "Jobs", sub: "Multi-source", c: "#f472b6", area: "jobs" },
  { id: "sumble", label: "Hiring team", sub: "People + email", c: "#fb923c", area: "team" },
  {
    id: "drive",
    label: "Drive",
    sub: "Optional library",
    c: "#94a3b8",
    area: "drive",
    optional: true,
  },
];

export default function ArchitectureDiagram({ selected, onSelect }: Props) {
  return (
    <div className="about-diagram" role="group" aria-label="TeamScout system architecture">
      <div className="about-arch-grid" data-testid="about-arch-grid">
        {/* Flow arrows (decorative, aria-hidden) */}
        <div className="about-arch-arrow about-arch-arrow-h about-arch-arrow-browser-api" aria-hidden>
          →
        </div>
        <div className="about-arch-arrow about-arch-arrow-v about-arch-arrow-api-sqlite" aria-hidden>
          ↓
        </div>
        <div className="about-arch-arrow about-arch-arrow-h about-arch-arrow-api-services" aria-hidden>
          →
        </div>

        {NODES.map((n) => {
          const active = selected === n.id;
          return (
            <button
              key={n.id}
              type="button"
              className={`about-node about-arch-node pressable${active ? " is-active" : ""}${
                n.optional ? " is-optional" : ""
              }`}
              style={{ gridArea: n.area, ["--node-c" as string]: n.c }}
              onClick={(e) => onSelect(n.id, e.currentTarget)}
              aria-expanded={active}
              aria-controls={active ? DETAIL_PANEL_ID : undefined}
              data-testid={`about-arch-node-${n.id}`}
            >
              <strong>{n.label}</strong>
              <span>{n.sub}</span>
            </button>
          );
        })}
      </div>

      <div className="about-diagram-footer">
        <p className="meta about-diagram-caption font-num">
          Browser (Next.js) → FastAPI → services → SQLite + external APIs
        </p>
        <p className="meta about-diagram-tradeoff">
          Tradeoff: one process and one file store keep failure modes small; multi-writer SaaS scale
          is out of scope. Dashed border = optional Drive.
        </p>
      </div>
    </div>
  );
}
