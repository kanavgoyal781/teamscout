"""Sumble job-post matching and related-people path."""
from __future__ import annotations
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.errors import ServiceFailingError
from app.services import sumble_client
logger = get_logger(__name__)
def search_org_job_posts(organization_id: int, limit: int | None = None) -> tuple[list[dict], int]:
    """Search org's job posts (filter mode). Used to find matching JD post."""
    lim = limit or getattr(settings, "SUMBLE_JOB_MATCH_LIMIT", 30)
    data = sumble_client.post(
        "/v6/jobs",
        {
            "filter": {"organization_ids": [organization_id]},
            "select": {"attributes": ["title"]},
            "limit": lim,
        },
        credit_costing=True,
    )
    jobs = data.get("jobs")
    credits = int(data.get("credits_used") or 0)
    return (jobs if isinstance(jobs, list) else [], credits)
def find_best_matching_job_post(organization_id: int, jd_title: str, company: str) -> tuple[int | None, int]:
    """Find Sumble job post for org whose title best matches cached JD (title sim + company)."""
    if not jd_title:
        return None, 0
    try:
        jobs, search_credits = search_org_job_posts(organization_id)
    except (httpx.HTTPError, ServiceFailingError):
        return None, 0
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
        score = sumble_client.title_similarity(jd_l, title)
        if comp_l and (comp_l in title.lower() or comp_l.split()[0] in title.lower()):
            score += 0.15
        jd_words = set(w for w in jd_l.split() if len(w) > 2)
        title_words = set(w for w in title.lower().split() if len(w) > 2)
        if jd_words:
            overlap = len(jd_words & title_words) / max(1, len(jd_words))
            score += 0.1 * overlap
        if score > best_score:
            best_score = score
            best_id = int(jid)
    if best_score >= 0.28 and best_id is not None:
        return best_id, search_credits
    return None, search_credits
def get_related_people_for_job(
    sumble_job_id: int, limit: int | None = None
) -> tuple[list[sumble_client.SumblePerson], int]:
    """Documented list-mode jobs + related_people (the 'find-related-people' flow)."""
    lim = limit or getattr(settings, "SUMBLE_SEARCH_LIMIT", sumble_client.DEFAULT_LIMIT)
    data = sumble_client.post(
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
    results: list[sumble_client.SumblePerson] = []
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
                    sumble_client.SumblePerson(
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
