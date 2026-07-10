"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  BookOpen,
  Database,
  GitBranch,
  Layers,
  Scale,
  Search,
  Server,
  Shield,
  Users,
  Workflow,
} from "lucide-react";

import AboutPrinciplesStrip from "./about/AboutPrinciplesStrip";
import AboutStats from "./about/AboutStats";
import ArchitectureDiagram from "./about/ArchitectureDiagram";
import { DetailPanel, SectionHead, SelectableCard } from "./about/AboutShared";
import JourneyFlow from "./about/JourneyFlow";
import MlopsCycleDiagram from "./about/MlopsCycleDiagram";
import ProductVideoPlate from "./about/ProductVideoPlate";
import RankingFunnelDiagram from "./about/RankingFunnelDiagram";
import { INK, PRINCIPLES, type DetailKey } from "./about/details";

export default function AboutArchitecture() {
  const [selected, setSelected] = useState<DetailKey>(null);
  const reduced = useReducedMotion();
  const triggerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  const closeDetail = useCallback(() => {
    setSelected(null);
    const trigger = triggerRef.current;
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

  return (
    <div className="about-root" data-testid="about-funnel">
      <div className="about-detail-slot" data-testid="about-detail-slot">
        <AnimatePresence mode="wait">
          {open ? (
            <DetailPanel key={open} detailKey={open} onClose={closeDetail} closeRef={closeRef} />
          ) : null}
        </AnimatePresence>
      </div>

      {/* I · Hero + live stats */}
      <motion.section className="panel about-hero about-plate" {...fadeUp}>
        <div className="about-hero-grid">
          <div className="about-hero-copy">
            <p className="about-kicker">I · The product</p>
            <h2 className="about-hero-title">
              Two recruiting journeys. Multi-signal ranking. Fail loud, never invent a match.
            </h2>
            <p className="about-hero-lede">
              TeamScout takes one resume to the live market and finds the hiring team — or inverts
              the question: paste a job, rank a resume library, pick the best fit. Deliberately
              small: multi-signal scores you can audit, and an honesty layer that fails loud when
              integrations are missing.
            </p>
            <AboutStats />
            <ul className="about-proof-strip" data-testid="about-proof-strip" aria-label="Proof above the fold">
              <li>
                <code className="font-num">evals/thresholds.json</code>
                <span> — NDCG/MRR + resume-pick floors (never lowered)</span>
              </li>
              <li>
                <code className="font-num">offline eval scripts</code>
                <span> — CI anti-bloat + honesty gates</span>
              </li>
              <li>
                <code className="font-num">CONSTRAINTS.md</code>
                <span> — two features, SQLite, fail loud</span>
              </li>
            </ul>
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

          <ProductVideoPlate selected={open === "video"} onSelect={(el) => select("video", el)} />
        </div>
      </motion.section>

      {/* II · Journeys */}
      <motion.section className="panel" {...fadeUp} data-testid="about-journeys">
        <SectionHead
          kicker="II · Two journeys"
          title="What the operator does — and what runs underneath"
          lede="Expand any step for the real modules (parser, query_expand, hybrid rank, MaxSim, tournament). Product copy says hiring team; technical notes name services."
          icon={Layers}
        />
        <JourneyFlow />
      </motion.section>

      {/* III · Architecture SVG */}
      <motion.section className="panel about-diagram-panel" {...fadeUp}>
        <SectionHead
          kicker="III · Architecture"
          title="Browser → Next → FastAPI → services → SQLite + APIs"
          lede="One browser surface, one API process, one SQLite file. External services are explicit — optional ones are dashed. Click a node."
          icon={Workflow}
        />
        <ArchitectureDiagram selected={selected} onSelect={select} />
      </motion.section>

      {/* IV · Two features (cards) */}
      <motion.section className="panel" {...fadeUp}>
        <SectionHead
          kicker="IV · Scope"
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

      {/* V · Ranking funnel */}
      <motion.section className="panel about-score-panel" {...fadeUp}>
        <SectionHead
          kicker="V · Ranking funnel"
          title="150+ → hybrid → LLM top 30 → fuse → MMR top 10"
          lede="Production math, not a sketch. Each stage is selectable — same signals as the live pipeline. Default product-policy weights are shown below."
          icon={GitBranch}
        />
        <RankingFunnelDiagram selected={selected} onSelect={select} />
        <p className="meta about-score-footnote">
          Weights shown are default product policy from backend{" "}
          <code>RANKING_WEIGHT_*</code> (<code>app/core/config</code>); the live process may
          override them via env. Benchmarks: hybrid NDCG@10 / MRR floors in{" "}
          <code>evals/thresholds.json</code>.
        </p>
      </motion.section>

      {/* VI · ML ops cycle */}
      <motion.section className="panel" {...fadeUp} data-testid="about-mlops">
        <SectionHead
          kicker="VI · Lightweight ML ops"
          title="Evals, traces, ceilings — in process"
          lede="Production-grade here means observable credit calls and regression floors, not a second data platform. Click a node on the cycle."
          icon={Activity}
        />
        <MlopsCycleDiagram selected={selected} onSelect={select} />
        <div className="about-card-grid about-card-grid-3" style={{ marginTop: 16 }}>
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
          Operator sequence: <code>make pipeline</code> (scope → backend unit tests → fit-signals).
          Floors are never lowered in PRs — see <code>evals/thresholds.json</code> and{" "}
          <code>CONSTRAINTS.md</code>.
        </p>
      </motion.section>

      {/* VII · Deploy */}
      <motion.section className="panel" {...fadeUp} data-testid="about-deploy">
        <SectionHead
          kicker="VII · Deploy"
          title="One browser, one API, one volume"
          lede="Vercel hosts the UI; Fly hosts FastAPI with SQLite on a persistent volume. Operator runbook: DEPLOYMENT.md."
          icon={Server}
        />
        <button
          type="button"
          className={`about-deploy-diagram pressable${selected === "deploy_topology" ? " is-active" : ""}`}
          onClick={(e) => select("deploy_topology", e.currentTarget)}
          aria-expanded={selected === "deploy_topology"}
          aria-controls={selected === "deploy_topology" ? "about-detail-panel" : undefined}
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
            DB file to S3-compatible storage. Click for operator steps.
          </p>
        </button>
      </motion.section>

      {/* VIII · Discipline + principles strip */}
      <motion.section className="panel" {...fadeUp}>
        <SectionHead
          kicker="VIII · Engineering principles"
          title="Constraints that keep the product honest"
          lede="Shippable over fashionable. Fail loud over degrade quietly. Two features over a platform. Links open the repo paths that enforce this."
          icon={Shield}
        />
        <AboutPrinciplesStrip />
        <div className="about-card-grid about-card-grid-3" style={{ marginTop: 16 }}>
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

      <footer className="panel about-footer-note" data-testid="about-footer">
        <p className="about-colophon">
          Engineer notes — credit-safety, observability tables, deploy surface — live in{" "}
          <code className="font-num">ARCHITECTURE.md</code> and{" "}
          <code className="font-num">DEPLOYMENT.md</code> in the repo. Built with FastAPI · Next.js ·
          SQLite · in-process hybrid rank. Set{" "}
          <code className="font-num">NEXT_PUBLIC_GITHUB_BASE</code> for clickable principle links. API
          origin:{" "}
          <code className="font-num">
            {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}
          </code>
          . This page documents the running product; it does not invent capabilities.
        </p>
      </footer>
    </div>
  );
}
