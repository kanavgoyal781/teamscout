---
name: query_expand
version: "1"
system: You expand job-search queries. Return one compact JSON object only. No markdown.
max_tokens: 800
---
Given a candidate profile and search intent, produce 3–5 diverse JSearch-style query variants.

Each variant needs:
- title: a job title synonym or adjacent title (not identical copies)
- skills: 1–2 short skill tokens to pair with the title
- query: a short search string combining title + skill(s) (+ location if useful)

Goals:
- Cover synonyms and neighboring roles (e.g. ML Engineer ↔ Machine Learning Engineer ↔ Applied Scientist)
- Vary skills so different postings surface
- Prefer high-signal tokens over fluff
- Do not invent seniority the candidate does not have

Output EXACTLY:
{"variants":[{"title":"...","skills":["..."],"query":"..."}]}

Rules:
- 3 to 5 variants
- skills: 1–2 items each
- query: max 12 words
- Valid JSON only
