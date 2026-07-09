"use client";

import { useCallback, useId, useState, type ComponentType } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  BookOpen,
  ChevronDown,
  Database,
  GitBranch,
  Layers,
  Scale,
  Search,
  Shield,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";

type DetailKey =
  | "browser"
  | "api"
  | "sqlite"
  | "llm"
  | "emb"
  | "jsearch"
  | "sumble"
  | "drive"
  | "f1"
  | "f2"
  | "retrieve"
  | "dense"
  | "rrf"
  | "llm_rerank"
  | "fuse"
  | "sqlite_why"
  | "honesty"
  | "anti_bloat"
  | "score_llm"
  | "score_rrf"
  | "score_skills"
  | "score_recency"
  | null;

type Detail = {
  title: string;
  why: string;
  how: string;
  tradeoff: string;
  color: string;
};

const DETAILS: Record<Exclude<DetailKey, null>, Detail> = {
  browser: {
    title: "Next.js browser (UI)",
    why: "Operators need a fast, keyboard-friendly surface for multi-step recruiting flows — not a multi-app portal.",
    how: "App Router pages for Feature 1, library, and this About story. React Query for server state; credit mutations never auto-retry.",
    tradeoff: "Single SPA-style client talks to one API origin (NEXT_PUBLIC_API_BASE). No BFF microservice.",
    color: "#5b8def",
  },
  api: {
    title: "FastAPI — single process",
    why: "All product logic is request-scoped: parse, rank, Sumble, reveal. One process keeps failure modes and deploy surface small.",
    how: "Routers under /resumes, /searches, /jobs, /contacts, /library, /ops. Typed errors, rate limits, request IDs, JSON logs in prod.",
    tradeoff: "Horizontal scale means multiple processes each with their own in-memory rate-limit counters — fine at one-machine deploy size.",
    color: "#3dd68c",
  },
  sqlite: {
    title: "SQLite file store",
    why: "One operator, one deploy: resumes, job cache, contacts, reveals, traces, embedding cache all fit a single file without DBA tax.",
    how: "SQLAlchemy models; create_all + light migrations; Fly volume mounts /data for persistence. Relative paths resolve under backend/.",
    tradeoff: "Not a multi-writer warehouse. Litestream optional for S3-compatible backup — not a second primary DB.",
    color: "#e8b84a",
  },
  llm: {
    title: "LLM (OpenAI-compatible)",
    why: "Structured extraction, rerank rationales, and resume justifications need language understanding — but only on top candidates.",
    how: "complete_json with versioned prompts from app/prompts/*.md; traces record prompt name/version/hash and estimated cost.",
    tradeoff: "Daily USD ceiling fail-closed (429). Unconfigured → 503 ServiceNotConfiguredError, never invented text.",
    color: "#c084fc",
  },
  emb: {
    title: "Embeddings API",
    why: "Dense retrieval catches semantic match when keyword BM25 alone would miss synonymy and paraphrases.",
    how: "L2-normalized vectors; content-hash cache in embedding_cache so re-ranking the same text does not re-bill.",
    tradeoff: "Depends on hosted embedding quality/dim. Cache is best-effort; miss falls through to the live API.",
    color: "#22d3ee",
  },
  jsearch: {
    title: "JSearch (live jobs)",
    why: "Feature 1 needs fresh market jobs, not a static fixture corpus.",
    how: "RapidAPI JSearch /search-v2; cache in jobs_cache with stable job_id so team extract/find stay addressable.",
    tradeoff: "External availability and pricing. Paste-job paths exist so team extract does not depend on JSearch.",
    color: "#f472b6",
  },
  sumble: {
    title: "Sumble (people + email)",
    why: "Finding the hiring team is the product differentiator after a strong job match.",
    how: "Org resolve → job-post match or people filter → gated email enrich. Credits logged with redacted URLs; no double-charge on reveal.",
    tradeoff: "Real credits. Daily credit ceiling fail-closed. Path label shows which strategy fired.",
    color: "#fb923c",
  },
  drive: {
    title: "Google Drive (optional)",
    why: "Recruiters often keep 50–60 resumes in a shared folder; bulk ingest beats one-by-one upload.",
    how: "Public folder via API key (preferred) or OAuth refresh; hash-dedup into the library.",
    tradeoff: "Optional for health ok. Unconfigured Drive hard-fails on sync with a clear 503 — no silent empty sync.",
    color: "#94a3b8",
  },
  f1: {
    title: "Feature 1 — Resume → jobs → team",
    why: "Primary path: one candidate resume against the live market, then outreach targets.",
    how: "Upload/parse → confirm profile → hybrid rank top 10 → extract team from JD → Sumble find → reveal email. Alternate: paste a job and run team/Sumble without JSearch.",
    tradeoff: "Scoped to this funnel. No full ATS, no applications tracker (beta stubs only).",
    color: "#3dd68c",
  },
  f2: {
    title: "Feature 2 — Library → best resume for a JD",
    why: "When you already have a resume pile, the question flips: which resume best fits this job posting?",
    how: "Ingest library (upload/ZIP/Drive) → paste full JD → rank all library resumes → top 3 with coverage + justification. Winner gets accent treatment.",
    tradeoff: "Close scores are expected. Transparency (coverage table, rationale) matters more than a single opaque score.",
    color: "#5b8def",
  },
  retrieve: {
    title: "1 · Retrieve",
    why: "Ranking needs a candidate set large enough for fusion but small enough for LLM cost.",
    how: "Fetch up to JOBS_FETCH_TARGET (~150) from JSearch; filter by JOBS_RECENCY_DAYS (default 14); require apply URL; cache rows.",
    tradeoff: "Recency filter can drop good roles with missing posted_at. Empty after filters fails loud — no mock jobs.",
    color: "#5b8def",
  },
  dense: {
    title: "2 · Dense + BM25",
    why: "Semantic and lexical signals catch different failure modes; using only one is brittle.",
    how: "Embed query + candidates (cosine). BM25 over tokenized title/skills/description. Both produce ranked ID lists.",
    tradeoff: "Two rankers mean two score spaces — fixed by RRF, not by ad-hoc score averaging.",
    color: "#22d3ee",
  },
  rrf: {
    title: "3 · RRF fuse",
    why: "Reciprocal Rank Fusion merges rankings without requiring calibrated scores across systems.",
    how: "For 0-based index i: add 1/(RRF_K+i+1) (K default 60). Min-max normalize → rrf_normalized in [0,1].",
    tradeoff: "RRF ignores magnitude of gaps between neighbors; LLM stage reintroduces absolute fit judgment.",
    color: "#e8b84a",
  },
  llm_rerank: {
    title: "4 · LLM rerank (top 30)",
    why: "Cheap retrieval is imperfect; a language model judges JD–resume fit on a shortlist only.",
    how: "Top RERANK_TOP_N by RRF get llm_fit 0–100 via versioned prompt. Optional — dense-only eval path exists.",
    tradeoff: "Cost and latency. Daily ceiling and max_tokens budgets bound spend; missing LLM → fail loud, not silent 0.",
    color: "#c084fc",
  },
  fuse: {
    title: "5 · Final weighted score",
    why: "Operators need one number and a transparent breakdown they can argue with.",
    how: "final = 100 × (0.5·llm/100 + 0.3·rrf + 0.1·skills + 0.1·recency). Resume pick swaps recency for experience_fit.",
    tradeoff: "Weights are product policy (validated at startup). Tuning requires green eval floors, not gut feel alone.",
    color: "#3dd68c",
  },
  sqlite_why: {
    title: "Why SQLite",
    why: "At this scale, a separate Postgres + vector stack is operational weight without matching value.",
    how: "File-backed state for all product tables; Docker/Fly volume for durability; optional Litestream replica.",
    tradeoff: "Concurrency model is single-writer friendly. Not chosen for multi-tenant SaaS scale-out.",
    color: "#e8b84a",
  },
  honesty: {
    title: "Honesty layer",
    why: "Silent fallbacks and mock data in app code hide broken integrations until a demo fails.",
    how: "ServiceNotConfiguredError / ServiceFailingError → clear JSON. No mocks under backend/app. Traces + ceilings for LLM/Sumble.",
    tradeoff: "Degraded health (503) when keys missing is intentional — UI lists exact env vars.",
    color: "#f07178",
  },
  anti_bloat: {
    title: "What we refused",
    why: "Platform fashion (queues, meshes, feature stores, K8s-as-product) does not earn its place for two focused features.",
    how: "check_scope enforces allowlisted deps, size budgets, banned infra terms, eval floors. Production-grade = CI, deploy, observability.",
    tradeoff: "You give up multi-service elasticity. You gain a codebase one engineer can reason about end-to-end.",
    color: "#94a3b8",
  },
  score_llm: {
    title: "llm_fit (weight 0.5)",
    why: "Highest weight: final judgment of fit after retrieval shortlist.",
    how: "LLM returns 0–100; fuse uses llm_fit/100. Missing LLM is not silently treated as 50.",
    tradeoff: "Dominates score when present — keep prompts versioned and eval-gated.",
    color: "#c084fc",
  },
  score_rrf: {
    title: "rrf_normalized (weight 0.3)",
    why: "Stable fusion of dense + BM25 without requiring score calibration.",
    how: "RRF sums then min-max normalize across the candidate pool.",
    tradeoff: "Relative within pool — not comparable across unrelated searches.",
    color: "#e8b84a",
  },
  score_skills: {
    title: "skill_jaccard (weight 0.1)",
    why: "Explicit skill overlap is easy to explain in the UI (green chips / amber gaps).",
    how: "Jaccard between profile skills and job skills / description hits.",
    tradeoff: "Weak on soft skills and synonymy — dense+LLM compensate.",
    color: "#3dd68c",
  },
  score_recency: {
    title: "recency / experience_fit (weight 0.1)",
    why: "Jobs: prefer fresher postings. Resume pick: prefer experience fit to the JD instead of post age.",
    how: "Half-life decay for job posted_at. Resume path uses experience_fit in the same weight slot.",
    tradeoff: "Missing posted_at drops candidates from recency-filtered fetch, not a fake mid score.",
    color: "#22d3ee",
  },
};

const FUNNEL_STEPS: { key: Exclude<DetailKey, null>; title: string; short: string; hue: string }[] = [
  { key: "retrieve", title: "Retrieve", short: "JSearch + cache", hue: "#5b8def" },
  { key: "dense", title: "Dense + BM25", short: "Two rankings", hue: "#22d3ee" },
  { key: "rrf", title: "RRF fuse", short: "k = 60", hue: "#e8b84a" },
  { key: "llm_rerank", title: "LLM rerank", short: "Top 30", hue: "#c084fc" },
  { key: "fuse", title: "Final score", short: "0–100", hue: "#3dd68c" },
];

function DetailPanel({
  detailKey,
  onClose,
}: {
  detailKey: Exclude<DetailKey, null>;
  onClose: () => void;
}) {
  const d = DETAILS[detailKey];
  const reduced = useReducedMotion();
  return (
    <motion.aside
      className="about-detail"
      style={{ borderColor: d.color }}
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? undefined : { opacity: 0, y: 6 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      role="region"
      aria-label={`Details: ${d.title}`}
      data-testid="about-detail"
    >
      <div className="about-detail-head">
        <span className="about-detail-swatch" style={{ background: d.color }} aria-hidden />
        <h3>{d.title}</h3>
        <button type="button" className="about-detail-close" onClick={onClose} aria-label="Close details">
          ×
        </button>
      </div>
      <div className="about-detail-body">
        <div>
          <h4>Why</h4>
          <p>{d.why}</p>
        </div>
        <div>
          <h4>How it works in TeamScout</h4>
          <p>{d.how}</p>
        </div>
        <div>
          <h4>Tradeoff we accepted</h4>
          <p>{d.tradeoff}</p>
        </div>
      </div>
    </motion.aside>
  );
}

function SelectableCard({
  id,
  active,
  color,
  icon: Icon,
  title,
  blurb,
  onSelect,
}: {
  id: Exclude<DetailKey, null>;
  active: boolean;
  color: string;
  icon: ComponentType<{ size?: number }>;
  title: string;
  blurb: string;
  onSelect: (k: Exclude<DetailKey, null>) => void;
}) {
  return (
    <button
      type="button"
      className={`about-card${active ? " is-active" : ""}`}
      style={{ ["--card-accent" as string]: color }}
      onClick={() => onSelect(id)}
      aria-expanded={active}
      aria-controls="about-detail-panel"
      data-testid={`about-card-${id}`}
    >
      <span className="about-card-icon" style={{ color }} aria-hidden>
        <Icon size={20} />
      </span>
      <span className="about-card-title">{title}</span>
      <span className="about-card-blurb">{blurb}</span>
      <span className="about-card-cta">
        Why this design <ChevronDown size={14} aria-hidden />
      </span>
    </button>
  );
}

export default function AboutArchitecture() {
  const [selected, setSelected] = useState<DetailKey>("api");
  const uid = useId();

  const select = useCallback((k: Exclude<DetailKey, null>) => {
    setSelected((prev) => (prev === k ? null : k));
  }, []);

  const open = selected;

  return (
    <div className="about-root" data-testid="about-funnel">
      {/* Hero / product story */}
      <section className="panel about-hero">
        <p className="about-kicker">
          <Sparkles size={14} aria-hidden /> TeamScout product story
        </p>
        <h2 className="about-hero-title">Recruiting intelligence, two features deep</h2>
        <p className="about-hero-lede">
          TeamScout is a focused app — not a platform. It helps you (1) take one resume to the live
          market and find the hiring team, and (2) match a pasted job description against a library of
          resumes. Everything below is the real architecture: click any node or step for the{" "}
          <strong>why</strong>, the <strong>how</strong>, and the <strong>tradeoff</strong>.
        </p>
        <div className="about-pill-row" role="list">
          {[
            { label: "Honesty layer", tip: "No silent fallbacks" },
            { label: "In-process ranking", tip: "Dense + BM25 + RRF + LLM" },
            { label: "SQLite", tip: "One file, one deploy" },
            { label: "Credit-safe Sumble", tip: "No double charge" },
          ].map((p) => (
            <span key={p.label} className="about-pill" role="listitem" title={p.tip}>
              {p.label}
            </span>
          ))}
        </div>
      </section>

      {/* Interactive system diagram */}
      <section className="panel about-diagram-panel">
        <div className="about-section-head">
          <Workflow size={18} aria-hidden />
          <div>
            <h2>System map</h2>
            <p className="meta" style={{ margin: 0 }}>
              Click a node to open architecture rationale. Optional services are dashed.
            </p>
          </div>
        </div>

        <div className="about-diagram" role="img" aria-label="TeamScout system architecture diagram">
          <svg viewBox="0 0 920 340" className="about-svg" aria-hidden>
            <defs>
              <linearGradient id={`${uid}-g1`} x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#5b8def" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#3dd68c" stopOpacity="0.15" />
              </linearGradient>
              <linearGradient id={`${uid}-g2`} x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#c084fc" />
                <stop offset="50%" stopColor="#22d3ee" />
                <stop offset="100%" stopColor="#3dd68c" />
              </linearGradient>
              <marker id={`${uid}-arrow`} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#3a4154" />
              </marker>
            </defs>
            <rect x="0" y="0" width="920" height="340" rx="16" fill={`url(#${uid}-g1)`} opacity="0.4" />

            {/* Edges */}
            <g stroke="#3a4154" strokeWidth="2" fill="none" markerEnd={`url(#${uid}-arrow)`}>
              <path d="M170,80 L250,80" />
              <path d="M410,80 L490,40" />
              <path d="M410,80 L490,80" />
              <path d="M410,80 L490,120" />
              <path d="M410,100 L490,200" />
              <path d="M410,100 L490,260" />
              <path d="M410,100 L490,310" strokeDasharray="6 4" />
              <path d="M330,110 L330,200" />
              <path d="M330,230 L490,200" strokeDasharray="4 3" opacity="0.6" />
            </g>

            {/* Nodes as foreignObject buttons via HTML overlay instead for a11y */}
          </svg>

          <div className="about-diagram-nodes">
            {(
              [
                { id: "browser" as const, label: "Browser", sub: "Next.js UI", x: "4%", y: "12%", c: "#5b8def" },
                { id: "api" as const, label: "FastAPI", sub: "Single process", x: "28%", y: "12%", c: "#3dd68c" },
                { id: "sqlite" as const, label: "SQLite", sub: "State + traces", x: "28%", y: "58%", c: "#e8b84a" },
                { id: "llm" as const, label: "LLM", sub: "Parse · rerank", x: "58%", y: "4%", c: "#c084fc" },
                { id: "emb" as const, label: "Embeddings", sub: "Dense retrieval", x: "58%", y: "22%", c: "#22d3ee" },
                { id: "jsearch" as const, label: "JSearch", sub: "Live jobs", x: "58%", y: "40%", c: "#f472b6" },
                { id: "sumble" as const, label: "Sumble", sub: "Team + email", x: "58%", y: "58%", c: "#fb923c" },
                { id: "drive" as const, label: "Drive", sub: "Optional library", x: "58%", y: "76%", c: "#94a3b8", optional: true },
              ] as const
            ).map((n) => (
              <button
                key={n.id}
                type="button"
                className={`about-node${selected === n.id ? " is-active" : ""}${
                  "optional" in n && n.optional ? " is-optional" : ""
                }`}
                style={{ left: n.x, top: n.y, ["--node-c" as string]: n.c }}
                onClick={() => select(n.id)}
                aria-expanded={selected === n.id}
                aria-controls="about-detail-panel"
              >
                <strong>{n.label}</strong>
                <span>{n.sub}</span>
              </button>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          {open && DETAILS[open] && (["browser", "api", "sqlite", "llm", "emb", "jsearch", "sumble", "drive"] as DetailKey[]).includes(open) ? (
            <DetailPanel key={open} detailKey={open as Exclude<DetailKey, null>} onClose={() => setSelected(null)} />
          ) : null}
        </AnimatePresence>
      </section>

      {/* Features */}
      <section className="panel">
        <div className="about-section-head">
          <Layers size={18} aria-hidden />
          <div>
            <h2>Two features only</h2>
            <p className="meta" style={{ margin: 0 }}>
              Click a card for the product decision behind the scope boundary.
            </p>
          </div>
        </div>
        <div className="about-card-grid">
          <SelectableCard
            id="f1"
            active={selected === "f1"}
            color="#3dd68c"
            icon={Users}
            title="Feature 1 — Resume → jobs → team"
            blurb="One resume against the market, then hiring contacts via Sumble."
            onSelect={select}
          />
          <SelectableCard
            id="f2"
            active={selected === "f2"}
            color="#5b8def"
            icon={Search}
            title="Feature 2 — Library → best resume"
            blurb="Many resumes in a library; paste a JD; pick the best fit."
            onSelect={select}
          />
        </div>
        <AnimatePresence mode="wait">
          {(selected === "f1" || selected === "f2") && (
            <DetailPanel key={selected} detailKey={selected} onClose={() => setSelected(null)} />
          )}
        </AnimatePresence>
      </section>

      {/* Ranking funnel */}
      <section className="panel">
        <div className="about-section-head">
          <GitBranch size={18} aria-hidden />
          <div>
            <h2>Retrieve → rank funnel</h2>
            <p className="meta" style={{ margin: 0 }}>
              Color-coded pipeline. Click any stage for rationale (same math as production).
            </p>
          </div>
        </div>

        <div className="about-funnel-flow" role="list">
          {FUNNEL_STEPS.map((step, i) => (
            <div key={step.key} className="about-funnel-item" role="listitem">
              <button
                type="button"
                className={`about-funnel-node${selected === step.key ? " is-active" : ""}`}
                style={{
                  background: `linear-gradient(135deg, ${step.hue}33, ${step.hue}11)`,
                  borderColor: step.hue,
                  boxShadow: selected === step.key ? `0 0 0 2px ${step.hue}55` : undefined,
                }}
                onClick={() => select(step.key)}
                aria-expanded={selected === step.key}
              >
                <span className="about-funnel-num font-num" style={{ color: step.hue }}>
                  {i + 1}
                </span>
                <strong>{step.title}</strong>
                <span className="meta">{step.short}</span>
              </button>
              {i < FUNNEL_STEPS.length - 1 ? (
                <div className="about-funnel-arrow" style={{ color: step.hue }} aria-hidden>
                  →
                </div>
              ) : null}
            </div>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {open && FUNNEL_STEPS.some((s) => s.key === open) ? (
            <DetailPanel key={open} detailKey={open as Exclude<DetailKey, null>} onClose={() => setSelected(null)} />
          ) : null}
        </AnimatePresence>
      </section>

      {/* Score formula interactive */}
      <section className="panel">
        <div className="about-section-head">
          <Scale size={18} aria-hidden />
          <div>
            <h2>Score formula</h2>
            <p className="meta" style={{ margin: 0 }}>
              Click a term to see why it carries that weight. Numbers use mono for an engineered read.
            </p>
          </div>
        </div>
        <pre className="formula about-formula" aria-label="Score formula">
{`final = 100 × (
  0.5 × (llm_fit / 100)
+ 0.3 × rrf_normalized
+ 0.1 × skill_jaccard
+ 0.1 × recency_or_experience_fit
)`}
        </pre>
        <div className="about-weight-row">
          {(
            [
              { id: "score_llm" as const, w: "50%", label: "llm_fit", c: "#c084fc" },
              { id: "score_rrf" as const, w: "30%", label: "rrf", c: "#e8b84a" },
              { id: "score_skills" as const, w: "10%", label: "skills", c: "#3dd68c" },
              { id: "score_recency" as const, w: "10%", label: "recency / exp", c: "#22d3ee" },
            ] as const
          ).map((b) => (
            <button
              key={b.id}
              type="button"
              className={`about-weight${selected === b.id ? " is-active" : ""}`}
              style={{ flex: b.w, background: b.c }}
              onClick={() => select(b.id)}
              aria-expanded={selected === b.id}
            >
              <span className="font-num">{b.w}</span>
              <span>{b.label}</span>
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait">
          {open &&
          (open === "score_llm" ||
            open === "score_rrf" ||
            open === "score_skills" ||
            open === "score_recency") ? (
            <DetailPanel key={open} detailKey={open} onClose={() => setSelected(null)} />
          ) : null}
        </AnimatePresence>
      </section>

      {/* Design decisions */}
      <section className="panel">
        <div className="about-section-head">
          <Shield size={18} aria-hidden />
          <div>
            <h2>Architecture decisions</h2>
            <p className="meta" style={{ margin: 0 }}>
              Deliberate constraints that keep the product honest and shippable.
            </p>
          </div>
        </div>
        <div className="about-card-grid about-card-grid-3">
          <SelectableCard
            id="sqlite_why"
            active={selected === "sqlite_why"}
            color="#e8b84a"
            icon={Database}
            title="SQLite at this scale"
            blurb="File-backed product state without a separate database service."
            onSelect={select}
          />
          <SelectableCard
            id="honesty"
            active={selected === "honesty"}
            color="#f07178"
            icon={Shield}
            title="Honesty layer"
            blurb="Fail loud. No mocks in app code. No silent fallbacks."
            onSelect={select}
          />
          <SelectableCard
            id="anti_bloat"
            active={selected === "anti_bloat"}
            color="#94a3b8"
            icon={BookOpen}
            title="Anti-bloat contract"
            blurb="Two features + beta stubs. Scope gates in CI."
            onSelect={select}
          />
        </div>
        <AnimatePresence mode="wait">
          {(selected === "sqlite_why" || selected === "honesty" || selected === "anti_bloat") && (
            <DetailPanel key={selected} detailKey={selected} onClose={() => setSelected(null)} />
          )}
        </AnimatePresence>
      </section>

      <section className="panel about-footer-note">
        <p className="meta" style={{ margin: 0 }}>
          Deeper engineer notes (credit-safety, observability tables, deploy surface) live in the repo
          file <code className="font-num">ARCHITECTURE.md</code>. API origin:{" "}
          <code className="font-num">
            {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}
          </code>
          . This page is documentation of the running product — not marketing copy.
        </p>
      </section>
    </div>
  );
}
