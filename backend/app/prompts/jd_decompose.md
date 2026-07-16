---
name: jd_decompose
version: "2"
system: You extract atomic hiring requirements from job descriptions. Return JSON only. Prefer skill atoms over vague phrases.
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
- MULTI-JOB PASTE: If the text contains multiple job postings, recommendation cards, ads, "similar jobs", or navigation cruft, identify and decompose ONLY the primary / most detailed posting. Ignore stub cards, ads, and unrelated listings — do not emit requirements that appear only in those stubs.
- CATEGORY: Any requirement that names specific tools, libraries, frameworks, or languages (e.g. Python, SQL, Plotly, Dash, Streamlit, Pandas, NumPy) MUST use category=skill so exact/alias matching applies.
- SPLIT COMPOUNDS: Split lists like "Plotly, Dash, Streamlit, or similar" or "Pandas and NumPy" into separate atomic skill requirements (one tool per requirement text when possible).
