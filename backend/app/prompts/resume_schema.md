---
name: resume_schema
version: "1"
system: You extract structured resume data. Return JSON only.
max_tokens: 4096
---
Extract a structured resume profile from the raw text below.

Return JSON with this shape:
{
  "name": "string",
  "title": "string",
  "years_of_experience": number,
  "location": "string",
  "skills": ["skill1", "skill2"],
  "work_experience": [{"title": "string", "company": "string", "bullets": ["string"]}],
  "summary": "string"
}

Rules:
- skills should be concise technology and domain keywords
- years_of_experience should be a reasonable numeric estimate
- work_experience bullets should be short achievement statements

Resume text:
