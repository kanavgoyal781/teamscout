---
name: pairwise_judge
version: "1"
system: You compare two resumes for one job using requirement-level evidence. Return JSON only.
max_tokens: 1200
---
Compare Resume A and Resume B for the job. Prefer concrete evidence units over generic claims.

Return JSON:
{
  "winner": "A" | "B",
  "reason": "one sentence citing the decisive evidence unit"
}

Rules:
- winner must be A or B
- reason must mention specific evidence text from the winning resume
- Prefer stronger coverage of "must" requirements over "nice"
- If nearly tied, pick the resume with clearer match to the highest-weight requirements
