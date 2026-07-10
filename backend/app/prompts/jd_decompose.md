---
name: jd_decompose
version: "1"
system: You extract atomic hiring requirements from job descriptions. Return JSON only.
max_tokens: 3000
---
Decompose the job description into atomic, independently-checkable requirements.

Return JSON:
{
  "requirements": [
    {
      "text": "short requirement phrase",
      "kind": "must" | "nice",
      "category": "skill" | "experience" | "domain" | "education",
      "weight": number
    }
  ]
}

Rules:
- 5–14 atomic requirements; each is one skill, years band, domain, or education item
- kind "must" for hard requirements / minimum qualifications; "nice" for preferred
- Default weights: must=2.0, nice=1.0 (you may adjust slightly within 0.5–3.0)
- Prefer concrete skill/tool names over vague soft skills
- Do not invent requirements not supported by the JD text
