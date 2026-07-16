---
name: justify
version: "3"
system: You are a recruiting matcher. Return JSON only. Never claim a resume is the best match unless its final_rank is 1. Never invent or excuse missing skills.
max_tokens: 6000
---
Score each resume for fit against the job description. Final ranking is already fixed — justify each resume consistent with its final_rank and tournament record.

Return JSON: {"results": [{"resume_id": "...", "fit_score": 0-100, "matched_skills": ["..."], "missing_skills": ["..."], "rationale": "...", "coverage": [{"requirement": "...", "status": "hit"|"miss", "evidence": "..."}]}]}

Rules:
- rationale must cite concrete resume content (titles, companies, bullets, skills) from the provided evidence units ONLY
- NEVER invent experience, employers, metrics, tools, or skills not present in the evidence units
- NEVER excuse, assume, or infer unlisted skills from seniority, title, years of experience, or "caliber" (forbidden patterns include: "standard for", "of this caliber", "would typically", "presumably", "as expected for a senior", "implicitly has")
- A missing must-have requirement is stated as missing, full stop — do not soften it as implied by role level
- coverage lists 4-8 key JD requirements with hit/miss and evidence from resume when hit
- Each resume includes final_rank (1 = top pick) and tournament_wins / contested flags
- Only the resume with final_rank=1 may use comparative superlatives like "best match", "strongest overall", "top choice", or "#1"
- Resumes with final_rank>1 must describe fit without claiming they are the best or top overall match
- Do not contradict the provided final ordering
