"""Sumble REST client — org lookup, people search, email reveal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.logging import get_logger
from app.errors import ServiceFailingError, ServiceNotConfiguredError

logger = get_logger(__name__)

EMAIL_REVEAL_COST = 10
PEOPLE_SEARCH_LIMIT = 25


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


def build_people_query(
    *,
    team_name: str,
    department: str,
    likely_hiring_titles: list[str],
) -> str | None:
    clauses: list[str] = []
    department = department.strip()
    team_name = team_name.strip()

    if department:
        clauses.append(f"job_function EQ '{_escape_query_value(department)}'")
    if team_name:
        clauses.append(f"team CONTAINS '{_escape_query_value(team_name)}'")

    title_terms = [title.strip() for title in likely_hiring_titles if title.strip()]
    if title_terms:
        title_clauses = [
            f"job_title CONTAINS '{_escape_query_value(title)}'" for title in title_terms[:5]
        ]
        clauses.append(f"({' OR '.join(title_clauses)})")

    if not clauses:
        return None
    return " AND ".join(clauses)


def lookup_organization(company_name: str) -> SumbleOrganization:
    company_name = company_name.strip()
    if not company_name:
        raise ServiceFailingError("Sumble", "company name is required for organization lookup")

    data = _post(
        "/v6/organizations",
        {
            "organizations": [{"name": company_name}],
            "select": {"attributes": ["id", "name"]},
            "limit": 1,
        },
        credit_costing=True,
    )
    rows = data.get("organizations")
    if not isinstance(rows, list) or not rows:
        raise ServiceFailingError("Sumble", f"no organization match for {company_name!r}")

    first = rows[0]
    if not isinstance(first, dict):
        raise ServiceFailingError("Sumble", "invalid organization row")

    attributes = first.get("attributes") or {}
    org_id = attributes.get("id")
    if org_id is None:
        raise ServiceFailingError("Sumble", f"organization unresolved for {company_name!r}")

    return SumbleOrganization(organization_id=int(org_id), name=attributes.get("name"))


def search_people(
    *,
    organization_id: int,
    team_name: str,
    department: str,
    likely_hiring_titles: list[str],
) -> tuple[list[SumblePerson], int]:
    filter_body: dict[str, Any] = {"organization_ids": [organization_id]}
    query = build_people_query(
        team_name=team_name,
        department=department,
        likely_hiring_titles=likely_hiring_titles,
    )
    if query:
        filter_body["query"] = {"query": query}

    data = _post(
        "/v6/people",
        {
            "filter": filter_body,
            "select": {"attributes": ["name", "job_title", "job_function", "job_level"]},
            "limit": PEOPLE_SEARCH_LIMIT,
            "order_by_column": "job_level",
            "order_by_direction": "DESC",
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


def reveal_email(person_id: int) -> tuple[str | None, int]:
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