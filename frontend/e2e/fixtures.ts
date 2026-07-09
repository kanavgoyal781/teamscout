import type { Page } from "@playwright/test";

export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export const healthy = {
  ok: true,
  db: true,
  version: "test",
  checks: {
    llm: "configured",
    embeddings: "configured",
    jobs_api: "configured",
    sumble: "configured",
    google_drive: "configured",
  },
  optional_checks: ["google_drive"],
};

export const degraded = {
  ok: false,
  db: true,
  checks: {
    llm: "missing",
    embeddings: "configured",
    jobs_api: "configured",
    sumble: "missing",
    google_drive: "missing",
  },
  optional_checks: ["google_drive"],
};

export const sampleProfile = {
  name: "Ada Lovelace",
  title: "Software Engineer",
  years_of_experience: 5,
  location: "Remote",
  skills: ["Python", "SQL", "Systems"],
  work_experience: [],
  summary: "Builder of analytical engines.",
};

export const rankedJob = {
  job: {
    id: "job-1",
    source: "jsearch",
    source_job_id: "src-1",
    title: "Staff Backend Engineer",
    company: "Acme Labs",
    location: "Remote",
    description:
      "Build reliable APIs in Python. Experience with SQL, ranking systems, and hiring collaboration preferred.",
    apply_url: "https://example.com/apply",
    posted_at: new Date(Date.now() - 36 * 3600 * 1000).toISOString(),
    skills: ["Python", "SQL"],
  },
  match_score: 87,
  score_breakdown: {
    llm_fit: 90,
    rrf_normalized: 0.82,
    dense_rank_score: 0.7,
    skill_jaccard: 0.66,
    recency: 0.9,
    experience_fit: null,
    final_score: 87,
    matched_skills: ["Python", "SQL"],
    missing_skills: ["Kubernetes"],
    rationale: "Strong Python and SQL overlap with the JD; systems experience transfers well.",
  },
};

export const rankedJob2 = {
  ...rankedJob,
  job: {
    ...rankedJob.job,
    id: "job-2",
    title: "Platform Engineer",
    company: "Beta Co",
  },
  match_score: 74,
};

export async function mockApi(
  page: Page,
  options: {
    health?: object;
    libraryEmpty?: boolean;
    searchError?: boolean;
    searchEmpty?: boolean;
    intentEmpty?: boolean;
    recommendEmpty?: boolean;
  } = {},
) {
  const health = options.health ?? healthy;

  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        headers: { "X-Request-ID": "req-e2e-test" },
        body: JSON.stringify(body),
      });

    if (path === "/health") {
      return json(health);
    }

    if (path === "/resumes/upload" && method === "POST") {
      return json({
        id: "resume-1",
        filename: "sample.pdf",
        content_hash: "abc",
        confirmed: false,
        profile: sampleProfile,
      });
    }

    if (path === "/resumes/resume-1/confirm" && method === "PUT") {
      return json({
        id: "resume-1",
        confirmed: true,
        profile: sampleProfile,
      });
    }

    if (path === "/searches" && method === "POST") {
      if (options.searchError) {
        return json(
          {
            error: "service_not_configured",
            message: "Jobs API is not configured",
            details: { request_id: "req-e2e-test" },
          },
          503,
        );
      }
      if (options.searchEmpty) {
        return json({
          search_id: "search-1",
          resume_id: "resume-1",
          results: [],
        });
      }
      return json({
        search_id: "search-1",
        resume_id: "resume-1",
        results: [rankedJob, rankedJob2],
      });
    }

    if (path === "/jobs/job-1/extract-team" && method === "POST") {
      return json({
        job_id: "job-1",
        extraction_id: "ext-1",
        extraction: {
          team_name: "Platform",
          department: "Engineering",
          likely_hiring_titles: ["Engineering Manager", "Director of Engineering"],
        },
      });
    }

    if (path === "/jobs/job-1/find-team" && method === "POST") {
      return json({
        job_id: "job-1",
        contacts: [
          {
            id: "c1",
            full_name: "Jordan Lee",
            title: "Engineering Manager",
            company: "Acme Labs",
            team: "Platform",
            seniority: "Manager",
            sumble_person_id: "s1",
            email_revealed: false,
            email: null,
          },
        ],
        credits_used: 12,
        team_searched: true,
        search_path: "Matched Sumble job post",
      });
    }

    if (path === "/jobs/job-1/team" && method === "GET") {
      return json({
        job_id: "job-1",
        contacts: [
          {
            id: "c1",
            full_name: "Jordan Lee",
            title: "Engineering Manager",
            company: "Acme Labs",
            team: "Platform",
            seniority: "Manager",
            sumble_person_id: "s1",
            email_revealed: false,
            email: null,
          },
        ],
        extraction_id: "ext-1",
        extraction: {
          team_name: "Platform",
          department: "Engineering",
          likely_hiring_titles: ["Engineering Manager"],
        },
        team_searched: true,
        search_path: "Matched Sumble job post",
      });
    }

    if (path === "/contacts/c1/reveal-email" && method === "POST") {
      if (url.searchParams.get("confirm") === "true") {
        return json({
          contact_id: "c1",
          cost_credits: 10,
          cached: false,
          email: "jordan.lee@acme.example",
          status: "revealed",
        });
      }
      return json({
        contact_id: "c1",
        cost_credits: 10,
        cached: false,
        email: null,
        status: "preview",
      });
    }

    if (path === "/library/resumes" && method === "GET") {
      if (options.libraryEmpty) {
        return json({ resumes: [], total: 0 });
      }
      return json({
        resumes: [
          {
            id: "lib-1",
            filename: "ada.pdf",
            content_hash: "h1",
            source: "upload",
            profile: sampleProfile,
            created_at: new Date().toISOString(),
          },
          {
            id: "lib-2",
            filename: "grace.pdf",
            content_hash: "h2",
            source: "upload",
            profile: { ...sampleProfile, name: "Grace Hopper", title: "Systems Engineer" },
            created_at: new Date().toISOString(),
          },
          {
            id: "lib-3",
            filename: "alan.pdf",
            content_hash: "h3",
            source: "upload",
            profile: { ...sampleProfile, name: "Alan Turing", title: "Researcher" },
            created_at: new Date().toISOString(),
          },
        ],
        total: 3,
      });
    }

    if (path === "/library/intent/search" && method === "POST") {
      if (options.intentEmpty) {
        return json({ search_id: "is-1", results: [] });
      }
      return json({ search_id: "is-1", results: [rankedJob] });
    }

    if (path === "/library/jobs/job-1/recommend-resumes" && method === "POST") {
      if (options.recommendEmpty) {
        return json({ job_id: "job-1", recommendations: [] });
      }
      return json({
        job_id: "job-1",
        recommendations: [
          {
            resume_id: "lib-1",
            filename: "ada.pdf",
            match_score: 91,
            score_breakdown: {
              ...rankedJob.score_breakdown,
              recency: 0,
              experience_fit: 0.85,
              final_score: 91,
              rationale: "Ada shows Python systems experience matching Platform API work.",
              matched_skills: ["Python", "Systems"],
              missing_skills: ["Kubernetes"],
            },
            coverage: [
              { requirement: "Python APIs", status: "hit", evidence: "Python systems experience" },
              { requirement: "Kubernetes", status: "miss", evidence: null },
            ],
          },
          {
            resume_id: "lib-2",
            filename: "grace.pdf",
            match_score: 78,
            score_breakdown: {
              ...rankedJob.score_breakdown,
              recency: 0,
              experience_fit: 0.6,
              final_score: 78,
              rationale: "Solid systems background with partial skill overlap.",
              matched_skills: ["Systems"],
              missing_skills: ["SQL"],
            },
            coverage: [
              { requirement: "Python APIs", status: "miss", evidence: null },
              { requirement: "Systems", status: "hit", evidence: "Systems Engineer" },
            ],
          },
          {
            resume_id: "lib-3",
            filename: "alan.pdf",
            match_score: 70,
            score_breakdown: {
              ...rankedJob.score_breakdown,
              recency: 0,
              experience_fit: 0.45,
              final_score: 70,
              rationale: "Research profile with theoretical systems strength.",
              matched_skills: ["Systems"],
              missing_skills: ["Python"],
            },
            coverage: [{ requirement: "Python APIs", status: "miss", evidence: null }],
          },
        ],
      });
    }

    // Default: empty OK
    return json({ ok: true });
  });
}
