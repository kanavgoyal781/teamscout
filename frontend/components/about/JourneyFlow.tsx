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
  engineers: string;
};

const FEATURE1_STEPS: JourneyStep[] = [
  {
    id: "parse",
    title: "Parse",
    product: "Upload a PDF/DOCX. We extract a structured profile you can edit.",
    underneath:
      "Structured extraction with a versioned prompt. Content-hash dedup avoids storing the same file twice in one workspace.",
    engineers: "services/parser · prompts/resume_schema",
  },
  {
    id: "confirm",
    title: "Confirm",
    product: "Lock title, location, and skills before any search spends API budget.",
    underneath: "Confirm snapshots the edited profile used for ranking and job search.",
    engineers: "api/routers/resumes",
  },
  {
    id: "expand",
    title: "Expand queries",
    product: "Turn the profile into several market-facing search queries.",
    underneath: "Optional language-model expand into a few variants; cache avoids re-billing identical profiles.",
    engineers: "services/query_expand",
  },
  {
    id: "fetch",
    title: "Fetch jobs",
    product: "Pull a live market pool (~150+) and cache stable job rows.",
    underneath: "Multi-source registry (live board + free ATS boards + remote feeds); filter and dedupe; workspace job cache.",
    engineers: "services/jobs · job_sources",
  },
  {
    id: "rank",
    title: "Rank",
    product: "Hybrid dense + BM25 → RRF → optional CE → LLM → weighted fuse → MMR top 10.",
    underneath:
      "Hybrid rank with a transparent score breakdown (fit, retrieval, skills, experience, requirements, recency).",
    engineers: "services/ranking · hybrid_rank · ranking_math",
  },
  {
    id: "team",
    title: "Hiring team",
    product: "Extract likely hiring titles from the JD, then look up people. Email reveal is gated.",
    underneath:
      "Team extract from the posting → people search → email reveal with no double-charge. Product copy never names the vendor.",
    engineers: "services/team_extract · team_search · email_reveal",
  },
];

const FEATURE2_STEPS: JourneyStep[] = [
  {
    id: "ingest",
    title: "Ingest library",
    product: "Upload many resumes, a ZIP, or sync a shared Drive folder.",
    underneath: "Hash-dedup into the workspace library; optional Drive public-folder or OAuth path.",
    engineers: "services/library_store · drive",
  },
  {
    id: "jd",
    title: "Paste JD",
    product: "Paste the full job description, not just a title keyword.",
    underneath: "Paste path stores a job row for alignment against the library.",
    engineers: "api/routers/library",
  },
  {
    id: "decompose",
    title: "Decompose requirements",
    product: "Break the posting into weighted atomic requirements.",
    underneath: "Requirement decompose (language model or deterministic path for offline eval).",
    engineers: "services/jd_decompose",
  },
  {
    id: "maxsim",
    title: "MaxSim coverage",
    product: "Each requirement finds its best evidence unit on every resume.",
    underneath: "Late-interaction coverage over bullet and skill units.",
    engineers: "services/resume_units · ranking_math_align",
  },
  {
    id: "tournament",
    title: "Close-call tournament",
    product: "When top scores are neck-and-neck, a pairwise judge reorders the band.",
    underneath: "Borda over contested IDs with order-normalized cache; gap threshold about 0.05.",
    engineers: "services/pairwise_tournament",
  },
  {
    id: "justify",
    title: "Justify top 3",
    product: "Alignment table + short rationale for the winner and runners-up.",
    underneath: "Justification prompt plus tournament cost logged to traces.",
    engineers: "services/resume_justify · resume_ranking",
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
                    <details className="journey-engineers" data-testid={`journey-engineers-${step.id}`}>
                      <summary>For engineers</summary>
                      <p className="meta font-num journey-engineers-path">{step.engineers}</p>
                    </details>
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
      <JourneyTrack featureLabel="Feature 1 · Resume → jobs → hiring team" steps={FEATURE1_STEPS} />
      <JourneyTrack featureLabel="Feature 2 · Library → best resume" steps={FEATURE2_STEPS} />
    </div>
  );
}
