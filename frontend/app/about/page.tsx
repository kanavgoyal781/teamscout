"use client";

import AppShell from "../../components/AppShell";

const FUNNEL = [
  { title: "Retrieve", body: "Fetch ~150 jobs (JSearch), 14-day recency filter, cache in SQLite." },
  { title: "Dense + BM25", body: "Cosine similarity over embeddings and BM25 lexical ranks in-process." },
  { title: "RRF fuse", body: "Reciprocal Rank Fusion (k=60), then min-max normalize to rrf_normalized." },
  { title: "LLM rerank", body: "Optional rerank of top 30 candidates → llm_fit 0–100." },
  { title: "Final score", body: "Weighted blend returned as match_score 0–100 with transparent score_breakdown." },
];

export default function AboutPage() {
  return (
    <AppShell
      title="Architecture"
      lede="How TeamScout retrieves, ranks, and explains matches — with an honesty layer for external services."
    >
      <section className="panel" data-testid="about-funnel">
        <h2>Retrieve → rank funnel</h2>
        <div className="funnel" role="list">
          {FUNNEL.map((step, i) => (
            <div key={step.title} className="funnel-step" role="listitem">
              <span className="step-num font-num">{i + 1}</span>
              <div>
                <strong>{step.title}</strong>
                <p className="meta" style={{ margin: "4px 0 0" }}>
                  {step.body}
                </p>
              </div>
            </div>
          ))}
        </div>

        <h2 style={{ marginTop: 24 }}>Score formula</h2>
        <pre className="formula" aria-label="Score formula">
{`final = 100 * (
  0.5 * (llm_fit / 100)
+ 0.3 * rrf_normalized
+ 0.1 * skill_jaccard
+ 0.1 * recency
)`}
        </pre>
        <p className="meta" style={{ marginTop: 16 }}>
          Full engineer notes live in the repo root file{" "}
          <code className="font-num">ARCHITECTURE.md</code> (credit-safety, error philosophy, deploy
          surface). API base:{" "}
          <code className="font-num">
            {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}
          </code>
        </p>
      </section>

      <section className="panel">
        <h2>Two features only</h2>
        <div className="field-grid">
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Feature 1</h3>
            <p className="meta" style={{ margin: 0 }}>
              Resume upload → profile confirm → hybrid job rank → team extract → Sumble find → email
              reveal.
            </p>
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Feature 2</h3>
            <p className="meta" style={{ margin: 0 }}>
              Library ingest → intent search → top-3 resume pick with coverage table and justification.
            </p>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
