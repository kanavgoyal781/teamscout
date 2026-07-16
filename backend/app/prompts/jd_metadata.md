---
name: jd_metadata
version: "1"
system: You extract ONLY facts explicitly written in the job description text. Return strict JSON. Never use world knowledge, never guess company/title/location/salary from product names or famous employers. If a field is not explicitly present in the text, output null for that field.
max_tokens: 2048
---
Extract job posting metadata from the raw text below.

Rules (extraction honesty — hard constraints):
1. Output JSON only matching this shape:
{
  "title": string|null,
  "company": string|null,
  "location": string|null,
  "remote_mode": "remote"|"hybrid"|"onsite"|null,
  "salary_min": number|null,
  "salary_max": number|null,
  "salary_currency": string|null,
  "seniority": string|null,
  "department": string|null,
  "confidence": {
    "title": "high"|"medium"|"low",
    "company": "high"|"medium"|"low",
    "location": "high"|"medium"|"low",
    "remote_mode": "high"|"medium"|"low",
    "salary_min": "high"|"medium"|"low",
    "salary_max": "high"|"medium"|"low",
    "salary_currency": "high"|"medium"|"low",
    "seniority": "high"|"medium"|"low",
    "department": "high"|"medium"|"low"
  }
}
2. NULL when the text does NOT explicitly state the value. Do NOT invent.
3. Do NOT fill company from brand/product names (e.g. "Kubernetes" does not imply Google; "React" does not imply Meta).
4. Ignore UI chrome ("Apply now", "Save", "Easy Apply", "Promoted") and legal boilerplate footers unless they restate the role facts.
5. salary_min/salary_max are annual numeric amounts when clearly annual; for hourly rates leave both null (do not annualize).
6. salary_currency is ISO 4217 when known (USD, EUR, GBP, …).
7. remote_mode only when the posting clearly states remote / hybrid / onsite (or equivalent).
8. confidence: high = explicit and unambiguous; medium = present but noisy; low = weak/partial signal. Omit confidence keys only if the field is null.

RAW JOB TEXT:
