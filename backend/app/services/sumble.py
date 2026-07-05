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

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.logging import get_logger
from app.errors import ServiceFailingError, ServiceNotConfiguredError

logger = get_logger(__name__)

EMAIL_REVEAL_COST = 10
DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class SumbleOrganization:
    organization_id: int
    name: str | None


@dataclass(frozen=True)
class SumblePerson:
    person_id: int
    name: str | None
    title: str | None
    team: str | None
    seniority: str | None
    job_function: str | None


def _require_sumble_config() -> None:
    if not is_set(settings.SUMBLE_API_KEY):
        raise ServiceNotConfiguredError("Sumble", "SUMBLE_API_KEY")


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.SUMBLE_API_KEY}",
        "Content-Type": "application/json",
    }


def _post(path: str, payload: dict[str, Any], *, credit_costing: bool = False) -> dict[str, Any]:
    _require_sumble_config()
    url = f"{settings.SUMBLE_BASE_URL.rstrip('/')}{path}"
    if credit_costing:
        logger.info("sumble.credit_call", method="POST", url=_redact_url(url))

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=_auth_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise ServiceFailingError("Sumble", f"HTTP {exc.response.status_code}: {detail}") from exc
    except httpx.HTTPError as exc:
        raise ServiceFailingError("Sumble", str(exc)) from exc

    if not isinstance(data, dict):
        raise ServiceFailingError("Sumble", "unexpected response format")

    if credit_costing:
        logger.info(
            "sumble.credit_result",
            credits_used=data.get("credits_used"),
            credits_remaining=data.get("credits_remaining"),
        )
    return data


def _escape_query_value(value: str) -> str:
    return value.replace("'", "\\'")


def _title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def map_llm_extraction_to_sumble(
    department: str, likely_hiring_titles: list[str]
) -> tuple[list[str], list[str]]:
    """Small mapping helper: department + titles -> (job_functions, job_levels).

    Per https://docs.sumble.com/api/lookups/job-title-lookup.md the response
    shapes are objects:
      job_function: {id, slug, name} | null
      job_level: {id, name, level_rank} | null

    Prefers slug for job_function (docs DSL examples use slugs e.g. EQ '<slug>'),
    falls back to name. This is validated by scripts/smoke_sumble.py.

    A parse error must surface (narrow except); broad except is forbidden.
    """
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
        return ([f for f in funcs if f], levels)

    # Try title-lookup for canonical job_function / job_level
    try:
        data = _post(
            "/v6/jobs/title-lookup",
            {"titles": titles[:20]},
            credit_costing=True,
        )
        results = data.get("results") or []
        seen_f: set[str] = set(funcs)
        seen_l: set[str] = set()
        for r in results:
            if not isinstance(r, dict):
                continue
            jf_obj = r.get("job_function")
            jl_obj = r.get("job_level")
            # Prefer slug for job_function (DSL uses slugs), fallback to name
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
        # Only transient/network/config errors; parse defects must not be swallowed
        # Fallback: pass titles through as functions (best effort)
        for t in titles[:5]:
            if t not in funcs:
                funcs.append(t)

    return ([f for f in funcs if f], levels)


def build_people_query(
    *,
    department: str,
    likely_hiring_titles: list[str],
) -> str | None:
    """Build documented advanced query string for people filter.query.query .

    Uses only supported fields from docs (job_function EQ, job_level EQ).
    Never uses non-existent "team CONTAINS".
    Prefers slugs (from title-lookup) for job_function values per DSL examples.
    Validated via scripts/smoke_sumble.py.
    """
    funcs, levels = map_llm_extraction_to_sumble(department, likely_hiring_titles)
    clauses: list[str] = []
    if funcs:
        if len(funcs) == 1:
            clauses.append(f"job_function EQ '{_escape_query_value(funcs[0])}'")
        else:
            ors = " OR ".join(f"job_function EQ '{_escape_query_value(f)}'" for f in funcs[:3])
            clauses.append(f"({ors})")
    if levels:
        if len(levels) == 1:
            clauses.append(f"job_level EQ '{_escape_query_value(levels[0])}'")
        else:
            ors = " OR ".join(f"job_level EQ '{_escape_query_value(l)}'" for l in levels[:3])
            clauses.append(f"({ors})")
    if not clauses:
        return None
    return " AND ".join(clauses)


def _derive_domain(company_name: str, apply_url: str | None = None) -> str | None:
    """Heuristic to derive domain for org resolve-by-url (per docs preference for url/domain).

    Uses apply_url host (stripping common job boards) or slug+ .com from company name.
    """
    if apply_url:
        try:
            host = (urlparse(apply_url).netloc or "").lower().strip()
            if host:
                # Strip common ATS / job board subdomains and hosts
                for junk in (
                    "jobs.", "careers.", "boards.", "myjobs.", "jobs-",
                    "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
                    "breezy.hr", "myworkday.com", "taleo.net", "jobvite.com",
                    "smartrecruiters.com", "recruitee.com",
                ):
                    host = host.replace(junk, "")
                host = host.strip(".")
                # Take registrable domain-ish
                parts = [p for p in host.split(".") if p]
                if len(parts) >= 2:
                    candidate = ".".join(parts[-2:])
                    if len(candidate) > 3 and not candidate.startswith("com."):
                        return candidate
        except (ValueError, TypeError, AttributeError):
            pass
    # fallback from name
    slug = "".join(c for c in (company_name or "").lower() if c.isalnum())
    if slug:
        return f"{slug}.com"
    return None


def lookup_organization(company_name: str, apply_url: str | None = None) -> SumbleOrganization:
    """Resolve org using documented /v6/organizations. Prefer url/domain per docs.

    Tries name+url derived, then name. Raises clear error (no fabricated id) on failure.
    """
    company_name = (company_name or "").strip()
    if not company_name:
        raise ServiceFailingError("Sumble", "company name is required for organization lookup")

    orgs_inputs: list[dict[str, str]] = []
    dom = _derive_domain(company_name, apply_url)
    if dom:
        orgs_inputs.append({"name": company_name, "url": dom})
    orgs_inputs.append({"name": company_name})

    _require_sumble_config()  # fail fast with correct error before any calls
    for inp in orgs_inputs:
        try:
            data = _post(
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
                        return SumbleOrganization(
                            organization_id=int(oid), name=attrs.get("name")
                        )
        except ServiceFailingError:
            # transient or no match for this candidate; try next
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
    """Documented filter-mode people search as fallback path.

    Request body uses only documented keys: filter.organization_ids + filter.query.query (EQ),
    select.attributes, limit (default 10).
    """
    lim = getattr(settings, "SUMBLE_SEARCH_LIMIT", DEFAULT_LIMIT)
    titles = likely_hiring_titles or []
    filter_body: dict[str, Any] = {"organization_ids": [organization_id]}
    query = build_people_query(department=department, likely_hiring_titles=titles)
    if query:
        filter_body["query"] = {"query": query}

    data = _post(
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

    credits_used = int(data.get("credits_used") or 0)
    return results, credits_used


def search_org_job_posts(organization_id: int, limit: int | None = None) -> list[dict]:
    """Search org's job posts (filter mode). Used to find matching JD post.

    Selects only free attributes (title is free per docs; organization is paid).
    Limit defaults to SUMBLE_JOB_MATCH_LIMIT (30) to control credit spend.
    """
    lim = limit or getattr(settings, "SUMBLE_JOB_MATCH_LIMIT", 30)
    data = _post(
        "/v6/jobs",
        {
            "filter": {"organization_ids": [organization_id]},
            "select": {"attributes": ["title"]},
            "limit": lim,
        },
        credit_costing=True,
    )
    jobs = data.get("jobs")
    return jobs if isinstance(jobs, list) else []


def find_best_matching_job_post(
    organization_id: int, jd_title: str, company: str
) -> int | None:
    """Find Sumble job post for org whose title best matches cached JD (title sim + company).

    Returns Sumble job_id (int) or None. Heuristic quality focused.
    """
    if not jd_title:
        return None
    try:
        jobs = search_org_job_posts(organization_id)
    except (httpx.HTTPError, ServiceFailingError):
        return None

    best_id: int | None = None
    best_score = 0.0
    jd_l = jd_title.lower()
    comp_l = (company or "").lower()

    for j in jobs:
        if not isinstance(j, dict):
            continue
        jid = j.get("job_id")
        if jid is None:
            continue
        attrs = j.get("attributes") or {}
        title = str(attrs.get("title") or "")
        if not title:
            continue
        score = _title_similarity(jd_l, title)
        # boost if company/domain overlap
        if comp_l and (comp_l in title.lower() or comp_l.split()[0] in title.lower()):
            score += 0.15
        # word overlap boost
        jd_words = set(w for w in jd_l.split() if len(w) > 2)
        title_words = set(w for w in title.lower().split() if len(w) > 2)
        if jd_words:
            overlap = len(jd_words & title_words) / max(1, len(jd_words))
            score += 0.1 * overlap
        if score > best_score:
            best_score = score
            best_id = int(jid)

    if best_score >= 0.28 and best_id is not None:
        return best_id
    return None


def get_related_people_for_job(
    sumble_job_id: int, limit: int | None = None
) -> tuple[list[SumblePerson], int]:
    """Documented list-mode jobs + related_people (the 'find-related-people' flow).

    Per docs: returns the people most relevant to that role (hiring managers/team).
    Request uses documented "jobs" list + "select.related_people".
    Response: jobs[0].related_people[] with person_id + attributes.
    """
    lim = limit or getattr(settings, "SUMBLE_SEARCH_LIMIT", DEFAULT_LIMIT)
    data = _post(
        "/v6/jobs",
        {
            "jobs": [{"job_id": sumble_job_id}],
            "select": {
                "related_people": {
                    "attributes": ["name", "job_title", "job_function", "job_level"],
                    "limit": lim,
                }
            },
        },
        credit_costing=True,
    )
    jobs = data.get("jobs") or []
    results: list[SumblePerson] = []
    if isinstance(jobs, list) and jobs:
        row = jobs[0]
        if isinstance(row, dict):
            rels = row.get("related_people") or []
            for rp in rels:
                if not isinstance(rp, dict):
                    continue
                pid = rp.get("person_id")
                if pid is None:
                    continue
                attrs = rp.get("attributes") or {}
                results.append(
                    SumblePerson(
                        person_id=int(pid),
                        name=attrs.get("name"),
                        title=attrs.get("job_title"),
                        team=None,
                        seniority=attrs.get("job_level"),
                        job_function=attrs.get("job_function"),
                    )
                )
    credits_used = int(data.get("credits_used") or 0)
    return results, credits_used


def find_hiring_team(
    *,
    organization_id: int,
    team_name: str,
    department: str,
    likely_hiring_titles: list[str],
    jd_title: str = "",
    company: str = "",
) -> tuple[list[SumblePerson], int, str]:
    """Primary path: org job-posts match -> find-related-people.

    Fallback: people filter by function/level.
    Returns (people, credits_used, path_label)
    Path labels exactly: "Matched Sumble job post" or "Filtered by function/level"
    """
    lim = getattr(settings, "SUMBLE_SEARCH_LIMIT", DEFAULT_LIMIT)

    # Preferred: job post match
    if jd_title:
        try:
            matched_id = find_best_matching_job_post(organization_id, jd_title, company)
            if matched_id is not None:
                people, credits = get_related_people_for_job(matched_id, limit=lim)
                if people:
                    logger.info(
                        "sumble.team_path",
                        path="Matched Sumble job post",
                        sumble_job_id=matched_id,
                        count=len(people),
                    )
                    return people, credits, "Matched Sumble job post"
        except (httpx.HTTPError, ServiceFailingError) as exc:
            logger.info("sumble.job_related_fallback", reason=str(exc)[:200])

    # Fallback
    people, credits = search_people(
        organization_id=organization_id,
        team_name=team_name,
        department=department,
        likely_hiring_titles=likely_hiring_titles,
    )
    logger.info("sumble.team_path", path="Filtered by function/level", count=len(people))
    return people, credits, "Filtered by function/level"


def reveal_email(person_id: int) -> tuple[str | None, int]:
    """Documented list-mode enrich for email (people list + email attr).

    Keeps billing/terminal cache intact in callers. Matches current docs contract.
    """
    data = _post(
        "/v6/people",
        {
            "people": [{"person_id": person_id}],
            "select": {"attributes": ["email"]},
        },
        credit_costing=True,
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