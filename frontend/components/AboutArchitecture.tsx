"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ComponentType,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  BookOpen,
  ChevronDown,
  Database,
  GitBranch,
  Layers,
  Pause,
  Play,
  Scale,
  Search,
  Server,
  Shield,
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
  | "score_experience"
  | "score_requirements"
  | "score_recency"
  | "mlops_evals"
  | "mlops_traces"
  | "mlops_ceilings"
  | "deploy_topology"
  | "video"
  | null;

type Detail = {
  title: string;
  why: string;
  how: string;
  tradeoff: string;
  color: string;
};

const BRASS = "#c4a35a";
const INK = "#8b93a7";

/**
 * Default product-policy weights from backend `RANKING_WEIGHT_*` in
 * `app/core/config.py` (validated to sum to 1.0 at startup). About documents
 * these defaults; runtime env can override the API without this page updating.
 */
const SCORE_WEIGHTS = {
  llm: 0.38,
  rrf: 0.2,
  skills: 0.12,
  experience: 0.12,
  requirements: 0.1,
  recency: 0.08,
} as const;

function pct(w: number): string {
  return `${Math.round(w * 100)}%`;
}

function weightLabel(name: string, w: number): string {
  return `${name} (weight ${w.toFixed(2)})`;
}

const DETAILS: Record<Exclude<DetailKey, null>, Detail> = {
  browser: {
    title: "Next.js browser (UI)",
    why: "Operators need a fast, keyboard-friendly surface for multi-step recruiting flows — not a multi-app portal.",
    how: "App Router pages for Feature 1, library, and this About story. React Query for server state; credit mutations never auto-retry.",
    tradeoff: "Single SPA-style client talks to one API origin (NEXT_PUBLIC_API_BASE). No separate BFF process.",
    color: "#5b8def",
  },
  api: {
    title: "FastAPI — single process",
    why: "All product logic is request-scoped: parse, rank, find hiring team, reveal. One process keeps failure modes and deploy surface small.",
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
    title: "Live jobs (multi-source)",
    why: "Feature 1 needs fresh market jobs, not a static fixture corpus.",
    how: "Primary: RapidAPI JSearch /search-v2 with multi-query broadening. Optional free boards (Remotive, Arbeitnow) merge + dedupe into jobs_cache with stable job_id.",
    tradeoff: "JSearch is required (key). Free boards are best-effort enrichment — failures log and continue. Paste-job paths still work without boards.",
    color: "#f472b6",
  },
  sumble: {
    title: "Hiring team (people + email)",
    why: "Finding who owns the hire is the product differentiator after a strong job match.",
    how: "Company resolve → posted-role match or people filter → gated email enrich. Credits logged with redacted URLs; no double-charge on reveal.",
    tradeoff: "Real credits. Daily credit ceiling fail-closed. Path label shows which strategy fired — vendor plumbing stays off the product surface.",
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
    how: "Upload/parse → confirm profile → hybrid rank top 10 → extract hiring team from JD → people lookup → reveal email. Alternate: paste a job and run team flow without JSearch.",
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
    how: "Multi-query JSearch + optional Remotive/Arbeitnow; merge/dedupe; filter by JOBS_RECENCY_DAYS; require apply URL; cache rows.",
    tradeoff: "Broader pool costs more JSearch pages. Empty after filters fails loud — no mock jobs.",
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
    tradeoff: "RRF ignores magnitude of gaps between neighbors; later stages reintroduce absolute fit judgment.",
    color: "#e8b84a",
  },
  llm_rerank: {
    title: "4 · LLM rerank (top 30, batched)",
    why: "Cheap retrieval is imperfect; a language model judges JD–resume fit — including seniority and hard requirements.",
    how: "Top RERANK_TOP_N by RRF, scored in batches of 8 so JSON finishes complete; salvage rebuilds truncated results arrays. Versioned prompt (years, must-haves, over/under-qualified penalties).",
    tradeoff: "Cost and latency. Daily ceiling and max_tokens budgets bound spend; missing LLM → fail loud, not silent 0.",
    color: "#c084fc",
  },
  fuse: {
    title: "5 · Final weighted score",
    why: "Keyword title overlap alone promotes senior roles. Operators need YOE, requirements, and skills in the number.",
    how: `final = 100 × (${SCORE_WEIGHTS.llm}·llm/100 + ${SCORE_WEIGHTS.rrf}·rrf + ${SCORE_WEIGHTS.skills}·skills + ${SCORE_WEIGHTS.experience}·experience + ${SCORE_WEIGHTS.requirements}·requirements + ${SCORE_WEIGHTS.recency}·recency). Weights validated at startup.`,
    tradeoff: "Weights are product policy. Tuning must keep eval floors green (NDCG/MRR + fit-signal suite).",
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
    how: "ServiceNotConfiguredError / ServiceFailingError → clear JSON. No mocks under backend/app. Traces + ceilings for LLM and hiring-team credits.",
    tradeoff: "Degraded health (503) when keys missing is intentional — UI lists exact env vars.",
    color: "#f07178",
  },
  anti_bloat: {
    title: "What we refused",
    why: "Platform fashion (queues, meshes, centralized ML platforms, cluster-as-product) does not earn its place for two focused features.",
    how: "check_scope enforces allowlisted deps, size budgets, banned infra terms, eval floors. Production-grade = CI, deploy, observability.",
    tradeoff: "You give up multi-service elasticity. You gain a codebase one engineer can reason about end-to-end.",
    color: "#94a3b8",
  },
  score_llm: {
    title: weightLabel("llm_fit", SCORE_WEIGHTS.llm),
    why: "Highest weight: final judgment of fit after retrieval shortlist — including seniority and must-haves.",
    how: "LLM returns 0–100; fuse uses llm_fit/100. Prompt v2 penalizes YOE mismatch. Missing LLM is not silently treated as 50.",
    tradeoff: "Dominates score when present — keep prompts versioned and eval-gated.",
    color: "#c084fc",
  },
  score_rrf: {
    title: weightLabel("rrf_normalized", SCORE_WEIGHTS.rrf),
    why: "Stable fusion of dense + BM25 without requiring score calibration.",
    how: "RRF sums then min-max normalize across the candidate pool.",
    tradeoff: "Relative within pool — not comparable across unrelated searches.",
    color: "#e8b84a",
  },
  score_skills: {
    title: weightLabel("skill_jaccard", SCORE_WEIGHTS.skills),
    why: "Explicit skill overlap is easy to explain in the UI (green chips / amber gaps).",
    how: "Jaccard between profile skills and job.skills lists (case-normalized).",
    tradeoff: "Weak on soft skills and synonymy — dense+LLM compensate. Description-derived must-haves use requirements_met, not this term.",
    color: "#3dd68c",
  },
  score_experience: {
    title: weightLabel("experience_fit", SCORE_WEIGHTS.experience),
    why: "Keyword search over-promotes Staff/Principal titles. YOE and seniority bands must move the score.",
    how: "Parse min years from JD; infer junior/mid/senior/staff/principal; score under- and over-qualification (0–1).",
    tradeoff: "Heuristic parse can miss odd phrasing — LLM stage and requirements_met backstop.",
    color: "#f472b6",
  },
  score_requirements: {
    title: weightLabel("requirements_met", SCORE_WEIGHTS.requirements),
    why: "Title matches without covering hard must-haves are false positives.",
    how: "Job.skills + Requirements section terms vs profile skills/text → coverage fraction 0–1.",
    tradeoff: "Token matching is imperfect for synonyms; dense+LLM close the gap.",
    color: "#fb923c",
  },
  score_recency: {
    title: weightLabel("recency", SCORE_WEIGHTS.recency),
    why: "Prefer fresher postings without dominating true fit signals.",
    how: "Half-life decay on posted_at (missing date → neutral 0.5). Resume pick sets recency=0 and uses experience/requirements.",
    tradeoff: "Older excellent fits can still win if experience + requirements + LLM are strong.",
    color: "#22d3ee",
  },
  video: {
    title: "Product motion (AI-generated)",
    why: "A short visual of resume → ranked matches → hiring-team constellation explains the product faster than a diagram alone.",
    how: "Three AI-generated shots played as a muted sequential playlist (resume card → ranked fits with score rings → hiring-team constellation). Sources: /videos/teamscout-match-01.mp4 … -03.mp4. Not a production screen recording.",
    tradeoff: "Illustrative film, not live product data. Real scores always come from the live ranking pipeline gated by eval scripts.",
    color: BRASS,
  },
  mlops_evals: {
    title: "Eval gates (not a remote catalog)",
    why: "Ranking is product policy. Floors prevent quiet regressions when prompts, weights, or fixtures change.",
    how: "evals/thresholds.json floors: NDCG@10 / MRR (hybrid), resume-pick correctness, experience/requirements order, overqualified penalty. Offline suite: make eval-fit. Hybrid ranking (embeddings; LLM optional): make eval. History: evals/history.jsonl + make eval-report. CI always runs fit-signals and uploads history when present; ranking/resume-pick when embeddings secrets exist.",
    tradeoff: "No remote experiment platform. Trends live in a JSONL file and CI artifacts — enough for a two-feature app.",
    color: "#5b8def",
  },
  mlops_traces: {
    title: "Traces + prompt versions",
    why: "Credit-costing and LLM calls must be auditable without bolting on a second observability vendor as product infra.",
    how: "SQLite traces table records operation, model, prompt name/version/hash, tokens, latency, cost, credits, cache hits. Versioned prompts under app/prompts/*.md. Ops dashboard at GET /ops (OPS_TOKEN). Optional OTLP export when configured.",
    tradeoff: "Trace writes are best-effort so a DB blip does not fail the user request; cost ceilings still fail closed on read errors.",
    color: "#22d3ee",
  },
  mlops_ceilings: {
    title: "Cost ceilings + embedding cache",
    why: "A runaway rerank loop or email-reveal storm should stop the day, not empty the wallet.",
    how: "LLM_DAILY_COST_CEILING_USD and SUMBLE_DAILY_CREDIT_CEILING → 429 CostCeilingExceededError. embedding_cache keys sha256(model+text). make pipeline runs scope → backend unit tests → fit-signal eval in order.",
    tradeoff: "Ceilings are process-local daily sums over SQLite traces — correct for one Fly machine; not a multi-region billing system.",
    color: "#fb923c",
  },
  deploy_topology: {
    title: "Deploy topology",
    why: "One live surface: browser talks to a single API process with file-backed state — not a cluster.",
    how: "Vercel (Next.js) → NEXT_PUBLIC_API_BASE → Fly.io FastAPI :8000. Volume teamscout_data at /data holds teamscout.db + uploads. Optional Litestream to S3-compatible storage. Operator path: make deploy-status, make deploy-api, make deploy-web, then DEMO_API_BASE=… make demo-check. See DEPLOYMENT.md.",
    tradeoff: "min_machines_running=1 and in-memory rate limits assume one machine. Scaling out needs shared limits + a shared DB story first.",
    color: "#3dd68c",
  },
};

const FUNNEL_STEPS: { key: Exclude<DetailKey, null>; title: string; short: string; hue: string }[] = [
  { key: "retrieve", title: "Retrieve", short: "Multi-source + cache", hue: "#5b8def" },
  { key: "dense", title: "Dense + BM25", short: "Two rankings", hue: "#22d3ee" },
  { key: "rrf", title: "RRF fuse", short: "k = 60", hue: "#e8b84a" },
  { key: "llm_rerank", title: "LLM rerank", short: "Top 30 · batch 8", hue: "#c084fc" },
  { key: "fuse", title: "Final score", short: "Six signals", hue: "#3dd68c" },
];

/** End-to-end product path shown as a classic request pipeline (not a queue mesh). */
const REQUEST_PATH: { stage: string; detail: string }[] = [
  { stage: "Parse", detail: "PDF/DOCX → structured profile (LLM + resume_schema prompt)" },
  { stage: "Confirm", detail: "Operator edits title, location, skills before search" },
  { stage: "Fetch", detail: "JSearch multi-query + optional free boards → jobs_cache" },
  { stage: "Rank", detail: "Dense + BM25 → RRF → batched LLM rerank → weighted fuse" },
  { stage: "Team", detail: "Extract roles from JD → company/people lookup → gated email reveal" },
];

const SCORE_BARS = [
  { id: "score_llm" as const, weight: SCORE_WEIGHTS.llm, label: "llm_fit", c: "#c084fc" },
  { id: "score_rrf" as const, weight: SCORE_WEIGHTS.rrf, label: "rrf", c: "#e8b84a" },
  { id: "score_skills" as const, weight: SCORE_WEIGHTS.skills, label: "skills", c: "#3dd68c" },
  { id: "score_experience" as const, weight: SCORE_WEIGHTS.experience, label: "experience", c: "#f472b6" },
  { id: "score_requirements" as const, weight: SCORE_WEIGHTS.requirements, label: "requirements", c: "#fb923c" },
  { id: "score_recency" as const, weight: SCORE_WEIGHTS.recency, label: "recency", c: "#22d3ee" },
] as const;

const PRINCIPLES = [
  { label: "Honesty layer", tip: "No silent fallbacks; missing keys fail loud" },
  { label: "Multi-signal rank", tip: "YOE + requirements + RRF + LLM" },
  { label: "Eval floors", tip: "NDCG/MRR + fit-signal suite" },
  { label: "In-process ML ops", tip: "Traces, ceilings, history — not a sprawling platform stack" },
  { label: "Credit-safe reveals", tip: "No double charge on email reveal" },
] as const;

const DETAIL_PANEL_ID = "about-detail-panel";

function DetailPanel({
  detailKey,
  onClose,
  closeRef,
}: {
  detailKey: Exclude<DetailKey, null>;
  onClose: () => void;
  closeRef: RefObject<HTMLButtonElement | null>;
}) {
  const d = DETAILS[detailKey];
  const reduced = useReducedMotion();
  const panelRef = useRef<HTMLElement | null>(null);

  // Mount-only focus/scroll: with AnimatePresence mode="wait", this panel only mounts
  // after the previous key has exited, so closeRef always points at *this* instance.
  // Parent timeouts race exit animations and must not be used for A→B switches.
  useLayoutEffect(() => {
    const closeBtn = closeRef.current;
    const panel = panelRef.current;
    closeBtn?.focus({ preventScroll: true });
    panel?.scrollIntoView({
      block: "nearest",
      behavior: reduced ? "auto" : "smooth",
    });
  }, [detailKey, closeRef, reduced]);

  return (
    <motion.aside
      ref={panelRef}
      className="about-detail"
      style={{ borderColor: d.color }}
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? undefined : { opacity: 0, y: 6 }}
      transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
      role="region"
      aria-label={`Details: ${d.title}`}
      data-testid="about-detail"
      id={DETAIL_PANEL_ID}
      tabIndex={-1}
    >
      <div className="about-detail-head">
        <span className="about-detail-swatch" style={{ background: d.color }} aria-hidden />
        <h3>{d.title}</h3>
        <button
          ref={closeRef}
          type="button"
          className="about-detail-close"
          onClick={onClose}
          aria-label="Close details"
        >
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
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  title: string;
  blurb: string;
  onSelect: (k: Exclude<DetailKey, null>, el: HTMLElement | null) => void;
}) {
  return (
    <button
      type="button"
      className={`about-card${active ? " is-active" : ""}`}
      style={{ ["--card-accent" as string]: color }}
      onClick={(e) => onSelect(id, e.currentTarget)}
      aria-expanded={active}
      aria-controls={active ? DETAIL_PANEL_ID : undefined}
      data-testid={`about-card-${id}`}
    >
      <span className="about-card-icon" style={{ color }} aria-hidden>
        <Icon size={18} strokeWidth={1.75} />
      </span>
      <span className="about-card-title">{title}</span>
      <span className="about-card-blurb">{blurb}</span>
      <span className="about-card-cta">
        Why this design <ChevronDown size={14} aria-hidden />
      </span>
    </button>
  );
}

function SectionHead({
  kicker,
  title,
  lede,
  icon: Icon,
}: {
  kicker: string;
  title: string;
  lede: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;
}) {
  return (
    <div className="about-section-head">
      <span className="about-section-icon" aria-hidden>
        <Icon size={16} strokeWidth={1.75} />
      </span>
      <div>
        <p className="about-section-kicker">{kicker}</p>
        <h2 className="about-section-title">{title}</h2>
        <p className="about-section-lede">{lede}</p>
      </div>
    </div>
  );
}

/** Three-beat product film: sequential muted clips (no system ffmpeg stitch). */
const PRODUCT_SHOTS = [
  {
    id: "resume",
    src: "/videos/teamscout-match-01.mp4",
    poster: "/videos/teamscout-match-01-poster.jpg",
    fig: "Fig. 1a",
    caption: "Resume card — structured profile from an upload",
  },
  {
    id: "matches",
    src: "/videos/teamscout-match-02.mp4",
    poster: "/videos/teamscout-match-02-poster.jpg",
    fig: "Fig. 1b",
    caption: "Ranked fits — multi-signal scores with transparent breakdown",
  },
  {
    id: "team",
    src: "/videos/teamscout-match-03.mp4",
    poster: "/videos/teamscout-match-03-poster.jpg",
    fig: "Fig. 1c",
    caption: "Hiring-team constellation — who to reach after the match",
  },
] as const;

function ProductVideoPlate({
  selected,
  onSelect,
}: {
  selected: boolean;
  onSelect: (el: HTMLElement | null) => void;
}) {
  const reduced = useReducedMotion();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** User intent to keep the sequence playing; independent of brief pause-on-ended. */
  const wantPlayRef = useRef(true);
  const [shotIndex, setShotIndex] = useState(0);
  /** Mirrors wantPlayRef so the control label does not flicker on natural end. */
  const [userWantsPlay, setUserWantsPlay] = useState(true);

  const shot = PRODUCT_SHOTS[shotIndex] ?? PRODUCT_SHOTS[0];

  const setWantPlay = useCallback((want: boolean) => {
    wantPlayRef.current = want;
    setUserWantsPlay(want);
  }, []);

  const clearPlayRetry = useCallback(() => {
    if (playRetryRef.current != null) {
      clearTimeout(playRetryRef.current);
      playRetryRef.current = null;
    }
  }, []);

  /** Attempt play when intent is on; schedule at most one delayed retry per failure streak. */
  const tryPlay = useCallback(() => {
    const el = videoRef.current;
    if (!el || reduced || !wantPlayRef.current) return;
    void el.play().catch(() => {
      if (!wantPlayRef.current) return;
      // Do not clear an in-flight retry — concurrent onCanPlay must not cancel recovery.
      if (playRetryRef.current != null) return;
      playRetryRef.current = setTimeout(() => {
        playRetryRef.current = null;
        const retryEl = videoRef.current;
        if (!retryEl || !wantPlayRef.current) return;
        void retryEl.play().catch(() => {
          // Autoplay exhausted — flip intent so the control shows Play and one
          // user gesture restarts (avoid stuck "Pause" that only clears intent).
          setWantPlay(false);
        });
      }, 280);
    });
  }, [reduced, setWantPlay]);

  // After each shot remount, try immediately; onCanPlay recovers if not ready yet.
  useEffect(() => {
    if (reduced || !wantPlayRef.current) return;
    tryPlay();
    return clearPlayRetry;
  }, [reduced, shotIndex, tryPlay, clearPlayRetry]);

  const advanceShot = useCallback(() => {
    setShotIndex((i) => (i + 1) % PRODUCT_SHOTS.length);
  }, []);

  const togglePlayback = useCallback(
    (e: ReactMouseEvent | ReactKeyboardEvent) => {
      e.stopPropagation();
      const el = videoRef.current;
      if (!el || reduced) return;
      // Toggle by intent, not el.paused — natural end briefly pauses but sequence should continue.
      if (wantPlayRef.current) {
        setWantPlay(false);
        clearPlayRetry();
        el.pause();
      } else {
        setWantPlay(true);
        tryPlay();
      }
    },
    [clearPlayRetry, reduced, setWantPlay, tryPlay],
  );

  return (
    <figure className="about-video-block">
      <div className="about-video-shell">
        <button
          type="button"
          className="about-video-frame"
          onClick={(e) => onSelect(e.currentTarget)}
          aria-label="Open details about the TeamScout product motion"
          aria-expanded={selected}
          aria-controls={selected ? DETAIL_PANEL_ID : undefined}
          data-testid="about-product-video"
        >
          {reduced ? (
            // eslint-disable-next-line @next/next/no-img-element -- static poster for reduced-motion
            <img
              className="about-video"
              src={PRODUCT_SHOTS[0].poster}
              alt=""
              width={1280}
              height={720}
            />
          ) : (
            <video
              key={shot.src}
              ref={videoRef}
              className="about-video"
              src={shot.src}
              poster={shot.poster}
              muted
              playsInline
              preload="auto"
              data-testid="about-product-video-el"
              data-shot={shot.id}
              onEnded={advanceShot}
              onCanPlay={() => {
                if (wantPlayRef.current) tryPlay();
              }}
            />
          )}
          {/* Decorative markers inside the frame control — must stay non-interactive.
              Play/Pause is a sibling of the frame button (not nested). */}
          <span className="about-video-shots" aria-hidden>
            {PRODUCT_SHOTS.map((s, i) => (
              <span
                key={s.id}
                className="about-video-shot-mark"
                data-active={
                  (reduced ? i === 0 : i === shotIndex) ? "true" : "false"
                }
              />
            ))}
          </span>
        </button>
        {!reduced ? (
          <button
            type="button"
            className="about-video-playback"
            onClick={togglePlayback}
            aria-label={userWantsPlay ? "Pause product video" : "Play product video"}
            data-testid="about-product-video-playback"
          >
            {userWantsPlay ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />}
            <span>{userWantsPlay ? "Pause" : "Play"}</span>
          </button>
        ) : null}
      </div>
      <figcaption className="about-video-plate-label" aria-live="polite">
        <span className="about-video-fig">{reduced ? "Fig. 1" : shot.fig}</span>
        <span className="about-video-caption-text">
          {reduced
            ? "Product film — resume → ranked fits → hiring-team constellation"
            : shot.caption}
        </span>
        <span className="about-video-meta">
          {reduced
            ? "AI-generated · still frame (reduced motion)"
            : `AI-generated · shot ${shotIndex + 1} of ${PRODUCT_SHOTS.length} · not a live recording`}
        </span>
      </figcaption>
      <p className="meta about-video-note">
        Real scores come from the weighted pipeline below, gated by{" "}
        <code>scripts/eval_ranking.py</code> and <code>scripts/eval_fit_signals.py</code>.
      </p>
    </figure>
  );
}

export default function AboutArchitecture() {
  const [selected, setSelected] = useState<DetailKey>(null);
  const uid = useId();
  const reduced = useReducedMotion();
  const triggerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  const closeDetail = useCallback(() => {
    setSelected(null);
    const trigger = triggerRef.current;
    // Restore focus after unmount/animation tick.
    requestAnimationFrame(() => {
      trigger?.focus?.();
    });
  }, []);

  const select = useCallback((k: Exclude<DetailKey, null>, el: HTMLElement | null) => {
    setSelected((prev) => {
      if (prev === k) {
        requestAnimationFrame(() => {
          triggerRef.current?.focus?.();
        });
        return null;
      }
      triggerRef.current = el;
      return k;
    });
  }, []);

  // Escape dismisses the shared detail panel.
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeDetail();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, closeDetail]);

  const open = selected;

  const fadeUp = reduced
    ? undefined
    : {
        initial: { opacity: 0, y: 12 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: "-40px" },
        transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const },
      };

  const formulaText = `final = 100 × (
  ${SCORE_WEIGHTS.llm.toFixed(2)} × (llm_fit / 100)
+ ${SCORE_WEIGHTS.rrf.toFixed(2)} × rrf_normalized
+ ${SCORE_WEIGHTS.skills.toFixed(2)} × skill_jaccard
+ ${SCORE_WEIGHTS.experience.toFixed(2)} × experience_fit
+ ${SCORE_WEIGHTS.requirements.toFixed(2)} × requirements_met
+ ${SCORE_WEIGHTS.recency.toFixed(2)} × recency
)`;

  return (
    <div className="about-root" data-testid="about-funnel">
      {/* Sticky top dock: one panel instance, stays in view while reading the essay */}
      <div className="about-detail-slot" data-testid="about-detail-slot">
        <AnimatePresence mode="wait">
          {open ? (
            <DetailPanel key={open} detailKey={open} onClose={closeDetail} closeRef={closeRef} />
          ) : null}
        </AnimatePresence>
      </div>

      {/* I · Thesis + product plate */}
      <motion.section className="panel about-hero about-plate" {...fadeUp}>
        <div className="about-hero-grid">
          <div className="about-hero-copy">
            <p className="about-kicker">I · The problem</p>
            <h2 className="about-hero-title">
              Recruiting tools that shout. Rankings that lie by omission.
            </h2>
            <p className="about-hero-lede">
              Keyword search promotes Staff titles over mid-level fit. Opaque scores hide the
              tradeoffs. TeamScout is deliberately small:{" "}
              <strong>two features</strong>, multi-signal ranking, and an honesty layer that fails
              loud when integrations are missing — never invents a match.
            </p>
            <p className="about-hero-lede about-hero-lede-secondary">
              Take one resume to the live market and find the hiring team. Or invert the question:
              paste a job, rank a resume library, pick the best fit. Click any node or weight for
              the <em>why</em>, <em>how</em>, and <em>tradeoff</em>.
            </p>

            <ul className="about-principle-index" aria-label="Design principles">
              {PRINCIPLES.map((p) => (
                <li key={p.label} title={p.tip}>
                  <span className="about-principle-mark" aria-hidden />
                  <span className="about-principle-label">{p.label}</span>
                  <span className="about-principle-tip">{p.tip}</span>
                </li>
              ))}
            </ul>
          </div>

          <ProductVideoPlate
            selected={open === "video"}
            onSelect={(el) => select("video", el)}
          />
        </div>
      </motion.section>

      {/* II · System map */}
      <motion.section className="panel about-diagram-panel" {...fadeUp}>
        <SectionHead
          kicker="II · The system"
          title="A map you can read in one sitting"
          lede="One browser surface, one API process, one SQLite file. External services are explicit — optional ones are dashed. Click a node."
          icon={Workflow}
        />

        <div
          className="about-diagram"
          role="group"
          aria-label="TeamScout system architecture"
        >
          <svg viewBox="0 0 920 340" className="about-svg" aria-hidden>
            <defs>
              <linearGradient id={`${uid}-g1`} x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#c4a35a" stopOpacity="0.08" />
                <stop offset="100%" stopColor="#5b8def" stopOpacity="0.04" />
              </linearGradient>
              <marker id={`${uid}-arrow`} markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#3a4154" />
              </marker>
            </defs>
            <rect x="0" y="0" width="920" height="340" rx="4" fill={`url(#${uid}-g1)`} />
            <g stroke="#3a4154" strokeWidth="1.5" fill="none" markerEnd={`url(#${uid}-arrow)`} opacity="0.85">
              <path d="M170,80 L250,80" />
              <path d="M410,80 L490,40" />
              <path d="M410,80 L490,80" />
              <path d="M410,80 L490,120" />
              <path d="M410,100 L490,200" />
              <path d="M410,100 L490,260" />
              <path d="M410,100 L490,310" strokeDasharray="5 4" />
              <path d="M330,110 L330,200" />
              <path d="M330,230 L490,200" strokeDasharray="4 3" opacity="0.55" />
            </g>
          </svg>

          <div className="about-diagram-nodes">
            {(
              [
                { id: "browser" as const, label: "Browser", sub: "Next.js UI", x: "4%", y: "12%", c: "#5b8def" },
                { id: "api" as const, label: "FastAPI", sub: "Single process", x: "28%", y: "12%", c: "#3dd68c" },
                { id: "sqlite" as const, label: "SQLite", sub: "State + traces", x: "28%", y: "58%", c: "#e8b84a" },
                { id: "llm" as const, label: "LLM", sub: "Parse · rerank", x: "58%", y: "4%", c: "#c084fc" },
                { id: "emb" as const, label: "Embeddings", sub: "Dense retrieval", x: "58%", y: "22%", c: "#22d3ee" },
                { id: "jsearch" as const, label: "Jobs", sub: "Multi-source", x: "58%", y: "40%", c: "#f472b6" },
                { id: "sumble" as const, label: "Hiring team", sub: "People + email", x: "58%", y: "58%", c: "#fb923c" },
                { id: "drive" as const, label: "Drive", sub: "Optional library", x: "58%", y: "76%", c: "#94a3b8", optional: true },
              ] as const
            ).map((n) => {
              const active = selected === n.id;
              return (
                <button
                  key={n.id}
                  type="button"
                  className={`about-node${active ? " is-active" : ""}${
                    "optional" in n && n.optional ? " is-optional" : ""
                  }`}
                  style={{ left: n.x, top: n.y, ["--node-c" as string]: n.c }}
                  onClick={(e) => select(n.id, e.currentTarget)}
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
      </motion.section>

      {/* III · Two features */}
      <motion.section className="panel" {...fadeUp}>
        <SectionHead
          kicker="III · Scope"
          title="Two features. Full stop."
          lede="Everything else is a stub or a refusal. Click a card for the product decision behind the boundary."
          icon={Layers}
        />
        <div className="about-card-grid">
          <SelectableCard
            id="f1"
            active={selected === "f1"}
            color="#3dd68c"
            icon={Users}
            title="Feature 1 — Resume → jobs → team"
            blurb="One resume against the market, then the people who own the hire."
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
      </motion.section>

      {/* IV · Ranking funnel + request path */}
      <motion.section className="panel" {...fadeUp}>
        <SectionHead
          kicker="IV · The funnel"
          title="Retrieve, fuse, judge, score"
          lede="Production math, not a sketch. Each stage is selectable — same signals as the live pipeline. Below: the full Feature 1 request path from upload to email."
          icon={GitBranch}
        />

        <ol className="about-request-path" aria-label="Feature 1 request path">
          {REQUEST_PATH.map((row, i) => (
            <li key={row.stage} className="about-request-step">
              <span className="about-request-num font-num">{String(i + 1).padStart(2, "0")}</span>
              <span className="about-request-stage">{row.stage}</span>
              <span className="about-request-detail">{row.detail}</span>
            </li>
          ))}
        </ol>

        <div className="about-funnel-flow" role="list">
          {FUNNEL_STEPS.map((step, i) => {
            const active = selected === step.key;
            return (
              <div key={step.key} className="about-funnel-item" role="listitem">
                <button
                  type="button"
                  className={`about-funnel-node${active ? " is-active" : ""}`}
                  style={{ ["--funnel-c" as string]: step.hue }}
                  onClick={(e) => select(step.key, e.currentTarget)}
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
      </motion.section>

      {/* V · Score formula */}
      <motion.section className="panel about-score-panel" {...fadeUp}>
        <SectionHead
          kicker="V · The score"
          title="A formula you can audit"
          lede="Click a term for its weight rationale. YOE and requirements sit in the number so Staff keyword hits cannot drown a true mid-level fit."
          icon={Scale}
        />
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
                className={`about-weight${active ? " is-active" : ""}`}
                style={{ flex: w, ["--weight-c" as string]: b.c }}
                onClick={(e) => select(b.id, e.currentTarget)}
                aria-expanded={active}
                aria-controls={active ? DETAIL_PANEL_ID : undefined}
              >
                <span className="font-num">{w}</span>
                <span>{b.label}</span>
              </button>
            );
          })}
        </div>
        <p className="meta about-score-footnote">
          Weights shown are default product policy from backend{" "}
          <code>RANKING_WEIGHT_*</code> (<code>app/core/config.py</code>); the live process may
          override them via env. Benchmarks: hybrid NDCG@10 / MRR floors in{" "}
          <code>evals/thresholds.json</code>; offline fit-signal suite scores experience order,
          requirements order, and staff/principal penalty rate via{" "}
          <code>scripts/eval_fit_signals.py</code>.
        </p>
      </motion.section>

      {/* VI · Lightweight ML ops */}
      <motion.section className="panel" {...fadeUp} data-testid="about-mlops">
        <SectionHead
          kicker="VI · Lightweight ML ops"
          title="Evals, traces, ceilings — in process"
          lede="Production-grade here means observable credit calls and regression floors, not a second data platform. Click a card for the operator path."
          icon={Activity}
        />
        <div className="about-card-grid about-card-grid-3">
          <SelectableCard
            id="mlops_evals"
            active={selected === "mlops_evals"}
            color="#5b8def"
            icon={Scale}
            title="Eval gates"
            blurb="thresholds.json floors · make eval-fit · history.jsonl"
            onSelect={select}
          />
          <SelectableCard
            id="mlops_traces"
            active={selected === "mlops_traces"}
            color="#22d3ee"
            icon={Activity}
            title="Traces & prompts"
            blurb="SQLite traces · versioned prompts · token-gated /ops"
            onSelect={select}
          />
          <SelectableCard
            id="mlops_ceilings"
            active={selected === "mlops_ceilings"}
            color="#fb923c"
            icon={Shield}
            title="Ceilings & cache"
            blurb="Daily USD/credit caps · embedding cache · make pipeline"
            onSelect={select}
          />
        </div>
        <p className="meta about-score-footnote">
          Operator sequence: <code>make pipeline</code> (scope → backend unit tests → fit-signals;
          optional ranking/resume-pick when embeddings are in repo-root <code>.env</code>; optional{" "}
          <code>demo-check</code> when <code>DEMO_API_BASE</code> is set). Floors are never lowered
          in PRs — see <code>evals/thresholds.json</code> and <code>CONSTRAINTS.md</code>.
        </p>
      </motion.section>

      {/* VII · Deploy topology */}
      <motion.section className="panel" {...fadeUp} data-testid="about-deploy">
        <SectionHead
          kicker="VII · Deploy"
          title="One browser, one API, one volume"
          lede="Vercel hosts the UI; Fly hosts FastAPI with SQLite on a persistent volume. One process, one volume. Operator runbook: DEPLOYMENT.md."
          icon={Server}
        />
        <button
          type="button"
          className={`about-deploy-diagram${selected === "deploy_topology" ? " is-active" : ""}`}
          onClick={(e) => select("deploy_topology", e.currentTarget)}
          aria-expanded={selected === "deploy_topology"}
          aria-controls={selected === "deploy_topology" ? DETAIL_PANEL_ID : undefined}
          data-testid="about-card-deploy_topology"
        >
          <div className="about-deploy-row" aria-hidden>
            <span className="about-deploy-box">Browser</span>
            <span className="about-deploy-arrow">→</span>
            <span className="about-deploy-box about-deploy-box-accent">Vercel · Next.js</span>
            <span className="about-deploy-arrow">→</span>
            <span className="about-deploy-box about-deploy-box-accent">Fly · FastAPI :8000</span>
            <span className="about-deploy-arrow">→</span>
            <span className="about-deploy-box">/data · SQLite + uploads</span>
          </div>
          <p className="about-deploy-caption">
            <code>NEXT_PUBLIC_API_BASE</code> points the UI at Fly. Optional Litestream replicates the
            DB file to S3-compatible storage. Click for operator steps (
            <code>make deploy-api</code> / <code>make deploy-web</code>).
          </p>
        </button>
      </motion.section>

      {/* VIII · Discipline */}
      <motion.section className="panel" {...fadeUp}>
        <SectionHead
          kicker="VIII · Discipline"
          title="Constraints that keep the product honest"
          lede="Shippable over fashionable. Fail loud over degrade quietly. Two features over a platform."
          icon={Shield}
        />
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
            color={INK}
            icon={BookOpen}
            title="Anti-bloat contract"
            blurb="Two features + beta stubs. Scope gates in CI."
            onSelect={select}
          />
        </div>
      </motion.section>

      <section className="panel about-footer-note">
        <p className="about-colophon">
          Engineer notes — credit-safety, observability tables, deploy surface — live in{" "}
          <code className="font-num">ARCHITECTURE.md</code> and{" "}
          <code className="font-num">DEPLOYMENT.md</code>. API origin:{" "}
          <code className="font-num">
            {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}
          </code>
          . This page documents the running product; it does not invent capabilities or claim a
          public URL is live without an operator deploy.
        </p>
      </section>
    </div>
  );
}
