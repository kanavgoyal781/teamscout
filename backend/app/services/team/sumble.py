"""Sumble REST client — org lookup, people search, email reveal.
Exact conformance to https://docs.sumble.com/api (OpenAPI v6):
- POST /v6/organizations for resolve (name or url/domain)
- POST /v6/people (filter mode for search; list mode for enrich/email)
- POST /v6/jobs (filter for job posts; list + related_people for find-related)
- POST /v6/jobs/title-lookup for vocab mapping
No invented fields or endpoints. All request bodies and response parsing
use only documented keys.
"""
from __future__ import annotations
from typing import Any
from urllib.parse import urlparse
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.errors import ServiceFailingError
from app.services import sumble_client, sumble_jobs
from app.services.team.client import SumbleOrganization, SumblePerson
EMAIL_REVEAL_COST = sumble_client.EMAIL_REVEAL_COST
DEFAULT_LIMIT = sumble_client.DEFAULT_LIMIT
search_org_job_posts = sumble_jobs.search_org_job_posts
find_best_matching_job_post = sumble_jobs.find_best_matching_job_post
get_related_people_for_job = sumble_jobs.get_related_people_for_job
logger = get_logger(__name__)
def map_llm_extraction_to_sumble(department: str, likely_hiring_titles: list[str]) -> tuple[list[str], list[str], int]:
    funcs: list[str] = []
    levels: list[str] = []
    dept = (department or "").strip()
    if dept:
        dlow = dept.lower()
        if any(k in dlow for k in ("engineer", "eng", "platform", "infra", "dev")):
            funcs.append("Engineering")
        elif "product" in dlow:
            funcs.append("Product")
        elif "design" in dlow:
            funcs.append("Design")
        elif "market" in dlow:
            funcs.append("Marketing")
        elif "sale" in dlow:
            funcs.append("Sales")
        else:
            funcs.append(dept)
    titles = [t.strip() for t in (likely_hiring_titles or []) if t and t.strip()]
    if not titles:
        return ([f for f in funcs if f], levels, 0)
    title_credits = 0
    try:
        data = sumble_client.post(
            "/v6/jobs/title-lookup",
            {"titles": titles[:20]},
            credit_costing=True,
        )
        title_credits = int(data.get("credits_used") or 0)
        results = data.get("results") or []
        seen_f: set[str] = set(funcs)
        seen_l: set[str] = set()
        for r in results:
            if not isinstance(r, dict):
                continue
            jf_obj = r.get("job_function")
            jl_obj = r.get("job_level")
            jf = None
            if isinstance(jf_obj, dict):
                jf = jf_obj.get("slug") or jf_obj.get("name")
            elif isinstance(jf_obj, str):
                jf = jf_obj  # legacy tolerance only
            jl = None
            if isinstance(jl_obj, dict):
                jl = jl_obj.get("name")
            elif isinstance(jl_obj, str):
                jl = jl_obj
            if jf and jf not in seen_f:
                seen_f.add(jf)
                funcs.append(jf)
            if jl and jl not in seen_l:
                seen_l.add(jl)
                levels.append(jl)
    except (httpx.HTTPError, ServiceFailingError):
        for t in titles[:5]:
            if t not in funcs:
                funcs.append(t)
    return ([f for f in funcs if f], levels, title_credits)
def build_people_query(
    *,
    department: str,
    likely_hiring_titles: list[str],
) -> tuple[str | None, int]:
    funcs, levels, title_credits = map_llm_extraction_to_sumble(department, likely_hiring_titles)
    clauses: list[str] = []
    if funcs:
        if len(funcs) == 1:
            clauses.append(f"job_function EQ '{sumble_client.escape_query_value(funcs[0])}'")
        else:
            ors = " OR ".join(f"job_function EQ '{sumble_client.escape_query_value(f)}'" for f in funcs[:3])
            clauses.append(f"({ors})")
    if levels:
        if len(levels) == 1:
            clauses.append(f"job_level EQ '{sumble_client.escape_query_value(levels[0])}'")
        else:
            ors = " OR ".join(f"job_level EQ '{sumble_client.escape_query_value(level)}'" for level in levels[:3])
            clauses.append(f"({ors})")
    query = " AND ".join(clauses) if clauses else None
    return query, title_credits
def _derive_domain(company_name: str, apply_url: str | None = None) -> str | None:
    if apply_url:
        try:
            host = (urlparse(apply_url).netloc or "").lower().strip()
            if host:
                for junk in (
                    "jobs.",
                    "careers.",
                    "boards.",
                    "myjobs.",
                    "jobs-",
                    "greenhouse.io",
                    "lever.co",
                    "ashbyhq.com",
                    "workable.com",
                    "breezy.hr",
                    "myworkday.com",
                    "taleo.net",
                    "jobvite.com",
                    "smartrecruiters.com",
                    "recruitee.com",
                ):
                    host = host.replace(junk, "")
                host = host.strip(".")
                parts = [p for p in host.split(".") if p]
                if len(parts) >= 2:
                    candidate = ".".join(parts[-2:])
                    if len(candidate) > 3 and not candidate.startswith("com."):
                        return candidate
        except (ValueError, TypeError, AttributeError):
            pass
    slug = "".join(c for c in (company_name or "").lower() if c.isalnum())
    if slug:
        return f"{slug}.com"
    return None
def lookup_organization(company_name: str, apply_url: str | None = None) -> tuple[SumbleOrganization, int]:
    company_name = (company_name or "").strip()
    if not company_name:
        raise ServiceFailingError("Sumble", "company name is required for organization lookup")
    orgs_inputs: list[dict[str, str]] = []
    dom = _derive_domain(company_name, apply_url)
    if dom:
        orgs_inputs.append({"name": company_name, "url": dom})
    orgs_inputs.append({"name": company_name})
    sumble_client.require_sumble_config()  # fail fast with correct error before any calls
    for inp in orgs_inputs:
        try:
            data = sumble_client.post(
                "/v6/organizations",
                {
                    "organizations": [inp],
                    "select": {"attributes": ["id", "name", "url"]},
                    "limit": 1,
                },
                credit_costing=True,
            )
            rows = data.get("organizations")
            if isinstance(rows, list) and rows:
                first = rows[0]
                if isinstance(first, dict):
                    attrs = first.get("attributes") or {}
                    oid = attrs.get("id")
                    if oid is not None:
                        org = SumbleOrganization(organization_id=int(oid), name=attrs.get("name"))
                        credits = int(data.get("credits_used") or 0)
                        return org, credits
        except ServiceFailingError:
            continue
    raise ServiceFailingError(
        "Sumble",
        f"organization could not be resolved for {company_name!r} (tried name and domain {dom!r}); provide better company/apply_url",
    )
def search_people(
    *,
    organization_id: int,
    team_name: str = "",
    department: str = "",
    likely_hiring_titles: list[str] | None = None,
) -> tuple[list[SumblePerson], int]:
    lim = getattr(settings, "SUMBLE_SEARCH_LIMIT", sumble_client.DEFAULT_LIMIT)
    titles = likely_hiring_titles or []
    filter_body: dict[str, Any] = {"organization_ids": [organization_id]}
    query, title_credits = build_people_query(department=department, likely_hiring_titles=titles)
    if query:
        filter_body["query"] = {"query": query}
    data = sumble_client.post(
        "/v6/people",
        {
            "filter": filter_body,
            "select": {"attributes": ["name", "job_title", "job_function", "job_level"]},
            "limit": lim,
        },
        credit_costing=True,
    )
    people_rows = data.get("people")
    if not isinstance(people_rows, list):
        raise ServiceFailingError("Sumble", "missing people array")
    results: list[SumblePerson] = []
    for row in people_rows:
        if not isinstance(row, dict):
            continue
        person_id = row.get("person_id")
        if person_id is None:
            continue
        attrs = row.get("attributes") or {}
        results.append(
            SumblePerson(
                person_id=int(person_id),
                name=attrs.get("name"),
                title=attrs.get("job_title"),
                team=team_name.strip() or attrs.get("job_function"),
                seniority=attrs.get("job_level"),
                job_function=attrs.get("job_function"),
            )
        )
    people_credits = int(data.get("credits_used") or 0)
    total_credits = people_credits + title_credits
    return results, total_credits
def find_hiring_team(
    *,
    organization_id: int,
    team_name: str,
    department: str,
    likely_hiring_titles: list[str],
    jd_title: str = "",
    company: str = "",
) -> tuple[list[SumblePerson], int, str]:
    lim = getattr(settings, "SUMBLE_SEARCH_LIMIT", sumble_client.DEFAULT_LIMIT)
    total_credits = 0
    if jd_title:
        try:
            matched_id, job_credits = sumble_jobs.find_best_matching_job_post(organization_id, jd_title, company)
            total_credits += job_credits
            if matched_id is not None:
                people, related_credits = sumble_jobs.get_related_people_for_job(matched_id, limit=lim)
                total_credits += related_credits
                if people:
                    logger.info(
                        "sumble.team_path",
                        path="Matched Sumble job post",
                        sumble_job_id=matched_id,
                        count=len(people),
                    )
                    return people, total_credits, "Matched Sumble job post"
        except (httpx.HTTPError, ServiceFailingError) as exc:
            logger.info("sumble.job_related_fallback", reason=str(exc)[:200])
    people, search_credits = search_people(
        organization_id=organization_id,
        team_name=team_name,
        department=department,
        likely_hiring_titles=likely_hiring_titles,
    )
    total_credits += search_credits
    logger.info("sumble.team_path", path="Filtered by function/level", count=len(people))
    return people, total_credits, "Filtered by function/level"
def reveal_email(person_id: int) -> tuple[str | None, int]:
    data = sumble_client.post(
        "/v6/people",
        {
            "people": [{"person_id": person_id}],
            "select": {"attributes": ["email"]},
        },
        credit_costing=True,
        operation="sumble.email_reveal",
    )
    people_rows = data.get("people")
    email: str | None = None
    if isinstance(people_rows, list) and people_rows:
        row = people_rows[0]
        if isinstance(row, dict):
            attrs = row.get("attributes") or {}
            raw_email = attrs.get("email")
            if isinstance(raw_email, str) and raw_email.strip():
                email = raw_email.strip()
    credits_used = int(data.get("credits_used") or 0)
    return email, credits_used
