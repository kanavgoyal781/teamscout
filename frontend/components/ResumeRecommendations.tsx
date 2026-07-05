"use client";

import { RankedJob, RankedResumeRecommendation } from "../lib/api";
import { formatPostedAt } from "../lib/format";

type ResumeRecommendationsProps = {
  jobResults: RankedJob[];
  searching: boolean;
  selectedJobId: string | null;
  recommending: boolean;
  recommendations: RankedResumeRecommendation[];
  onPickJob: (jobId: string) => void;
};

export default function ResumeRecommendations({
  jobResults,
  searching,
  selectedJobId,
  recommending,
  recommendations,
  onPickJob,
}: ResumeRecommendationsProps) {
  return (
    <>
      {jobResults.length > 0 ? (
        <section className="panel">
          <h2>3. Pick a job</h2>
          <div className="job-list">
            {jobResults.map((item) => (
              <article key={item.job.id} className="job-card">
                <div className="job-card-header">
                  <div>
                    <h3>{item.job.title}</h3>
                    <p className="meta">
                      {item.job.company} · {item.job.location} · Posted {formatPostedAt(item.job.posted_at)}
                    </p>
                  </div>
                  <div className="score-pill">{item.match_score}</div>
                </div>
                <p className="job-description">{item.job.description.slice(0, 220)}…</p>
                <button
                  type="button"
                  className={selectedJobId === item.job.id ? "primary" : ""}
                  onClick={() => onPickJob(item.job.id)}
                  disabled={recommending}
                >
                  {recommending && selectedJobId === item.job.id
                    ? "Ranking resumes…"
                    : "Pick best resume"}
                </button>
              </article>
            ))}
          </div>
        </section>
      ) : searching ? (
        <section className="panel">
          <p className="meta empty-hint">Fetching and ranking jobs…</p>
        </section>
      ) : null}

      {selectedJobId && !recommending && recommendations.length > 0 ? (
        <section className="panel">
          <h2>4. Top resume picks</h2>
          <div className="recommendation-list">
            {recommendations.map((item, index) => (
              <article key={item.resume_id} className="recommendation-card">
                <div className="job-card-header">
                  <div>
                    <h3>
                      #{index + 1} {item.filename}
                    </h3>
                  </div>
                  <div className="score-pill">{item.match_score}</div>
                </div>
                <p className="rationale">{item.score_breakdown.rationale}</p>
                <div className="chip-row">
                  {item.score_breakdown.matched_skills.map((skill) => (
                    <span key={`m-${item.resume_id}-${skill}`} className="chip chip-match">
                      {skill}
                    </span>
                  ))}
                  {item.score_breakdown.missing_skills.map((skill) => (
                    <span key={`x-${item.resume_id}-${skill}`} className="chip chip-miss">
                      {skill}
                    </span>
                  ))}
                </div>
                {item.coverage.length > 0 ? (
                  <table className="coverage-table">
                    <thead>
                      <tr>
                        <th>Requirement</th>
                        <th>Status</th>
                        <th>Evidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {item.coverage.map((row) => (
                        <tr key={`${item.resume_id}-${row.requirement}`}>
                          <td>{row.requirement}</td>
                          <td className={row.status === "hit" ? "coverage-hit" : "coverage-miss"}>
                            {row.status}
                          </td>
                          <td>{row.evidence ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : selectedJobId && recommending ? (
        <section className="panel">
          <p className="meta empty-hint">Ranking library resumes against job description…</p>
        </section>
      ) : null}
    </>
  );
}