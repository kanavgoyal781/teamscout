from pathlib import Path

import fitz

TEXT = """Jane Doe
Senior Backend Engineer
San Francisco, CA

Summary
Backend engineer with 8 years building distributed APIs and data pipelines.

Skills
Python, FastAPI, PostgreSQL, Redis, AWS, Docker, Kubernetes

Experience
Backend Engineer — Acme Corp
- Built REST APIs serving 2M requests/day
- Migrated monolith services to Kubernetes

Software Engineer — Beta LLC
- Implemented CI/CD pipelines and observability tooling
"""


def main() -> None:
    output = Path(__file__).with_name("sample_resume.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), TEXT)
    doc.save(output)
    doc.close()
    print(f"wrote {output}")


if __name__ == "__main__":
    main()