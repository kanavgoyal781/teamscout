/**
 * Interactive detail copy for the About page.
 * Captions must match real services; product language uses "hiring team" not vendor names.
 */

export type DetailKey =
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
  | "mmr"
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

export type Detail = {
  title: string;
  why: string;
  how: string;
  tradeoff: string;
  color: string;
};

export const BRASS = "#c4a35a";
export const INK = "#8b93a7";

/**
 * Default product-policy weights from backend `RANKING_WEIGHT_*` in
 * `app/core/config.py` (validated to sum to 1.0 at startup).
 */
export const SCORE_WEIGHTS = {
  llm: 0.38,
  rrf: 0.2,
  skills: 0.12,
  experience: 0.12,
  requirements: 0.1,
  recency: 0.08,
} as const;

export function pct(w: number): string {
  return `${Math.round(w * 100)}%`;
}

export function weightLabel(name: string, w: number): string {
  return `${name} (weight ${w.toFixed(2)})`;
}

export const DETAILS: Record<Exclude<DetailKey, null>, Detail> = {
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
    how: "Routers under /resumes, /searches, /jobs, /contacts, /library, /ops, /stats. Typed errors, rate limits, request IDs, JSON logs in prod.",
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
    how: "Ingest library (upload/ZIP/Drive) → paste full JD → decompose requirements → MaxSim unit coverage → optional close-call pairwise tournament → top 3 with alignment table + justification.",
    tradeoff: "Close scores are expected; tournament only reorders a narrow band. Transparency (evidence units, rationale) matters more than a single opaque score.",
    color: "#5b8def",
  },
  retrieve: {
    title: "1 · Retrieve",
    why: "Ranking needs a candidate set large enough for fusion but small enough for LLM cost.",
    how: "Optional LLM query expand (3–5 variants) → multi-query JSearch + optional Remotive/Arbeitnow; hard filters from SearchParams.date_window and prefs; exact/embedding dedupe; require apply URL; cache rows; expose dropped_counts. Target pool ~150+ (JOBS_FETCH_TARGET).",
    tradeoff: "Broader pool costs more JSearch pages. Soft prefs never exclude. Empty after filters fails loud — no mock jobs.",
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
    how: "For 0-based index i: add 1/(RRF_K+i+1) (K default 60). Min-max normalize → rrf_normalized in [0,1]. Top RERANK_TOP_N (30) advance to LLM.",
    tradeoff: "RRF ignores magnitude of gaps between neighbors; later stages reintroduce absolute fit judgment.",
    color: "#e8b84a",
  },
  llm_rerank: {
    title: "4 · LLM rerank (top 30, batched)",
    why: "Cheap retrieval is imperfect; a language model judges JD–resume fit — including seniority and hard requirements.",
    how: "Top RERANK_TOP_N by RRF, scored in batches of 6 with short job aliases; retry then explicit heuristic fill for omitted IDs. Versioned prompt (years, must-haves, over/under-qualified penalties).",
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
  mmr: {
    title: "6 · MMR diversify → top 10",
    why: "Without diversity, the top 10 can collapse to one company and near-duplicate titles.",
    how: "Maximal Marginal Relevance over ranked results (DEFAULT_MMR_LAMBDA=0.75) plus per-company soft cap. SEARCH_RESULTS_TOP_N=10 returned to the UI.",
    tradeoff: "Diversity can demote a slightly better near-dupe. Tradeoff is intentional for operator scan-ability.",
    color: "#fb923c",
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

export const FUNNEL_STEPS: {
  key: Exclude<DetailKey, null>;
  title: string;
  short: string;
  hue: string;
}[] = [
  { key: "retrieve", title: "Retrieve", short: "150+ multi-source", hue: "#5b8def" },
  { key: "dense", title: "Dense + BM25", short: "Two rankings", hue: "#22d3ee" },
  { key: "rrf", title: "RRF fuse", short: "k = 60", hue: "#e8b84a" },
  { key: "llm_rerank", title: "LLM rerank", short: "Top 30 · batch 6", hue: "#c084fc" },
  { key: "fuse", title: "Final score", short: "Six signals", hue: "#3dd68c" },
  { key: "mmr", title: "MMR top 10", short: "λ = 0.75", hue: "#fb923c" },
];

export const SCORE_BARS = [
  { id: "score_llm" as const, weight: SCORE_WEIGHTS.llm, label: "llm_fit", c: "#c084fc" },
  { id: "score_rrf" as const, weight: SCORE_WEIGHTS.rrf, label: "rrf", c: "#e8b84a" },
  { id: "score_skills" as const, weight: SCORE_WEIGHTS.skills, label: "skills", c: "#3dd68c" },
  { id: "score_experience" as const, weight: SCORE_WEIGHTS.experience, label: "experience", c: "#f472b6" },
  { id: "score_requirements" as const, weight: SCORE_WEIGHTS.requirements, label: "requirements", c: "#fb923c" },
  { id: "score_recency" as const, weight: SCORE_WEIGHTS.recency, label: "recency", c: "#22d3ee" },
] as const;

export const PRINCIPLES = [
  { label: "Honesty layer", tip: "No silent fallbacks; missing keys fail loud" },
  { label: "Multi-signal rank", tip: "YOE + requirements + RRF + LLM" },
  { label: "Eval floors", tip: "NDCG/MRR + fit-signal suite" },
  { label: "In-process ML ops", tip: "Traces, ceilings, history — not a sprawling platform stack" },
  { label: "Credit-safe reveals", tip: "No double charge on email reveal" },
] as const;

/** Repo paths linked from the engineering principles strip. */
export const PRINCIPLE_LINKS = [
  {
    label: "Anti-bloat contract",
    path: "CONSTRAINTS.md",
    tip: "Two features only; banned infra named and gated",
  },
  {
    label: "Scope gate",
    path: "scripts/check_scope.py",
    tip: "CI-blocking static check for size, deps, floors",
  },
  {
    label: "Architecture notes",
    path: "ARCHITECTURE.md",
    tip: "Request paths, ranking math, deploy surface",
  },
  {
    label: "Eval floors",
    path: "evals/thresholds.json",
    tip: "NDCG/MRR and resume-pick correctness floors",
  },
  {
    label: "Ranking service",
    path: "backend/app/services/ranking.py",
    tip: "Hybrid + LLM rerank + MMR diversify",
  },
] as const;

export const DETAIL_PANEL_ID = "about-detail-panel";

/**
 * GitHub blob URL for principle links.
 * Requires NEXT_PUBLIC_GITHUB_BASE (e.g. https://github.com/org/repo/blob/main).
 * Returns null when unset or still the placeholder — never ships OWNER/teamscout links.
 */
export function githubFileUrl(path: string): string | null {
  const raw = process.env.NEXT_PUBLIC_GITHUB_BASE?.replace(/\/$/, "") ?? "";
  if (!raw || /OWNER\/teamscout/i.test(raw)) return null;
  return `${raw}/${path}`;
}
