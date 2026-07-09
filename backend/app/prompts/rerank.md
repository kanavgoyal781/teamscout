---
name: rerank
version: "1"
system: You are a recruiting matcher. Return JSON only.
max_tokens: 6000
---
Score each job for fit against the candidate profile.
Return JSON: {"results": [{"job_id": "...", "fit_score": 0-100, "matched_skills": ["..."], "missing_skills": ["..."], "rationale": "..."}]}
