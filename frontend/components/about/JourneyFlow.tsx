"use client";

import { useId, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown } from "lucide-react";

import { easeOut } from "../../lib/motion";

export type JourneyStep = {
  id: string;
  title: string;
  product: string;
  underneath: string;
  module: string;
};

const FEATURE1_STEPS: JourneyStep[] = [
  {
    id: "parse",
    title: "Parse",
    product: "Upload a PDF/DOCX. We extract a structured profile you can edit.",
    underneath:
      "parser.py + LLM complete_json with versioned resume_schema prompt. Content-hash dedup on storage.",
    module: "services/parser.py · prompts/resume_schema.md",
  },
  {
    id: "confirm",
    title: "Confirm",
    product: "Lock title, location, and skills before any search spends API budget.",
    underneath: "PUT /resumes/{id}/confirm snapshots the operator-edited profile used for ranking.",
    module: "api/routers/resumes.py",
  },
  {
    id: "expand",
    title: "Expand queries",
    product: "Turn the profile into several market-facing search queries.",
    underneath: "query_expand.py may call the LLM for 3–5 variants; content-hash cache avoids re-billing.",
    module: "services/query_expand.py",
  },
  {
    id: "fetch",
    title: "Fetch jobs",
    product: "Pull a live market pool (~150+) and cache stable job rows.",
    underneath:
      "jobs.py / jsearch_client multi-query; optional free boards merge + dedupe into jobs_cache.",
    module: "services/jobs.py · jsearch_client.py",
  },
  {
    id: "rank",
    title: "Rank",
    product: "Hybrid dense + BM25 → RRF → optional CE (RRF50→15) → LLM → weighted fuse → MMR top 10.",
    underneath:
      "hybrid_rank + ranking.py. Score breakdown is transparent in the UI (llm_fit, rrf, skills, YOE, requirements, recency).",
    module: "services/ranking.py · hybrid_rank.py · ranking_math.py",
  },
  {
    id: "team",
    title: "Hiring team",
    product: "Extract likely hiring titles from the JD, then look up people. Email reveal is gated.",
    underneath:
      "team_extract.py (LLM) → find-team people search → email reveal with no double-charge. Product copy never names the vendor.",
    module: "services/team_extract.py · team_search.py · email_reveal.py",
  },
];

const FEATURE2_STEPS: JourneyStep[] = [
  {
    id: "ingest",
    title: "Ingest library",
    product: "Upload many resumes, a ZIP, or sync a shared Drive folder.",
    underneath: "library_store hash-dedup; optional Drive public-folder or OAuth path.",
    module: "services/library_store.py · drive.py",
  },
  {
    id: "jd",
    title: "Paste JD",
    product: "Paste the full job description — not just a title keyword.",
    underneath: "recommend-from-jd ingests text into a job row for alignment.",
    module: "api/routers/library.py",
  },
  {
    id: "decompose",
    title: "Decompose requirements",
    product: "Break the posting into weighted atomic requirements.",
    underneath: "jd_decompose.py (LLM or deterministic fallback path for offline eval).",
    module: "services/jd_decompose.py",
  },
  {
    id: "maxsim",
    title: "MaxSim coverage",
    product: "Each requirement finds its best evidence unit on every resume.",
    underneath:
      "resume_units + ranking_math_align MaxSim late-interaction coverage over bullet/skill units.",
    module: "services/resume_units.py · ranking_math_align.py",
  },
  {
    id: "tournament",
    title: "Close-call tournament",
    product: "When top scores are neck-and-neck, a pairwise judge reorders the band.",
    underneath:
      "pairwise_tournament.py Borda over contested IDs; order-normalized cache; gap threshold ~0.05.",
    module: "services/pairwise_tournament.py",
  },
  {
    id: "justify",
    title: "Justify top 3",
    product: "Alignment table + short rationale for the winner and runners-up.",
    underneath: "resume_justify.py + versioned justify prompt; tournament cost logged to traces.",
    module: "services/resume_justify.py · resume_ranking.py",
  },
];

function JourneyTrack({
  featureLabel,
  steps,
}: {
  featureLabel: string;
  steps: JourneyStep[];
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const reduced = useReducedMotion();
  const baseId = useId();

  return (
    <div className="journey-track" data-testid={`journey-${featureLabel}`}>
      <p className="journey-track-title">{featureLabel}</p>
      <ol className="journey-steps" aria-label={`${featureLabel} steps`}>
        {steps.map((step, i) => {
          const open = openId === step.id;
          const panelId = `${baseId}-${step.id}`;
          return (
            <li key={step.id} className={`journey-step${open ? " is-open" : ""}`}>
              <button
                type="button"
                className="journey-step-btn pressable"
                onClick={() => setOpenId(open ? null : step.id)}
                aria-expanded={open}
                aria-controls={panelId}
                data-testid={`journey-step-${step.id}`}
              >
                <span className="journey-step-num font-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="journey-step-body">
                  <strong>{step.title}</strong>
                  <span className="journey-step-product">{step.product}</span>
                </span>
                <ChevronDown
                  size={16}
                  className={`journey-chevron${open ? " is-open" : ""}`}
                  aria-hidden
                />
              </button>
              <AnimatePresence initial={false}>
                {open ? (
                  <motion.div
                    id={panelId}
                    className="journey-under"
                    initial={reduced ? false : { height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={reduced ? undefined : { height: 0, opacity: 0 }}
                    transition={easeOut}
                  >
                    <p className="journey-under-label">What happens underneath</p>
                    <p>{step.underneath}</p>
                    <p className="meta font-num">{step.module}</p>
                  </motion.div>
                ) : null}
              </AnimatePresence>
              {i < steps.length - 1 ? (
                <div className="journey-connector" aria-hidden>
                  <svg width="24" height="16" viewBox="0 0 24 16">
                    <path
                      d="M2 8h16m0 0l-4-4m4 4l-4 4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function JourneyFlow() {
  return (
    <div className="journey-flow" data-testid="journey-flow">
      <JourneyTrack featureLabel="Feature 1 — Resume → jobs → hiring team" steps={FEATURE1_STEPS} />
      <JourneyTrack featureLabel="Feature 2 — Library → best resume" steps={FEATURE2_STEPS} />
    </div>
  );
}
