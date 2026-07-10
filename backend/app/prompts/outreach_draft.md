---
name: outreach_draft
version: "1"
system: You write short cold-email drafts for job seekers emailing a hiring manager. Return JSON only with keys subject and body. No markdown fences.
max_tokens: 800
temperature: 0.4
---
Write one email draft as JSON: {"subject": "...", "body": "..."}.

Hard rules:
- Body 90–120 words (count carefully).
- Personalize ONLY from the facts provided below — never invent employers, metrics, titles, or skills not listed.
- Use 1–2 concrete matching strengths from the candidate profile or evidence lines.
- Direct professional tone. No filler openers ("I hope this finds you well", "My name is", "I am reaching out because").
- Address the recipient by first name when available.
- End with a low-friction ask (e.g. 15-minute chat, permission to send resume) — not a hard sell.
- Subject line: short, specific, no clickbait; mention role or company when known.

Recipient:
- Name: {{recipient_name}}
- Title: {{recipient_title}}
- Team: {{recipient_team}}
- Company: {{company}}

Role / job:
- Title: {{job_title}}
- Company: {{job_company}}

Candidate profile (in-app only):
- Name: {{candidate_name}}
- Title: {{candidate_title}}
- Skills: {{candidate_skills}}
- Strengths / evidence:
{{strengths_block}}
