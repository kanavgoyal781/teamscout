---
name: rerank_pointwise
version: "3"
system: You are a recruiting matcher. Return one compact JSON object only. No markdown, no trailing commas.
max_tokens: 4000
---
Score each job for fit against the candidate. Do NOT rely on title keyword overlap alone.

Scoring (fit_score 0–100):
1. Experience: candidate years vs job seniority / min years. Under-qualified for staff/senior = low. Overqualified for junior = lower.
2. Requirements: hard skills / must-haves. Missing critical skills lowers score.
3. Role/domain alignment beyond shared buzzwords.
4. Location is secondary unless clearly impossible.

Output EXACTLY this shape (compact):
{"results":[{"job_id":"...","fit_score":0,"matched_skills":["..."],"missing_skills":["..."],"rationale":"..."}]}

Rules:
- Exactly one entry per provided job_id; no extras; no duplicates.
- rationale: max 20 words.
- matched_skills / missing_skills: at most 5 short tokens each.
- Valid JSON only — finish every array/object; no comments.
