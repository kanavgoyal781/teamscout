from __future__ import annotations
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.services.jobs_svc.filters import annotate_job, jsearch_params_from_search
from app.services.jobs_svc.sources.base import FetchCriteria
from app.services.jobs_svc.sources.util import (
    board_cache_delete, board_cache_get, board_cache_set, load_ats_slugs, parse_iso, strip_html,
)
from app.services.jobs_svc.jsearch import fetch_jsearch_raw
logger = get_logger(__name__)
_UA, _ATS_N = {"User-Agent": "TeamScout/1.0 (job-source)"}, 4
def _skills(desc: str, profile: ResumeProfile) -> list[str]:
    from app.services.jobs_svc.fetch import extract_skills_from_description
    return extract_skills_from_description(desc, profile.skills)
def _job(**kw) -> Job:
    quality, is_remote = kw.pop("quality"), kw.pop("is_remote", None)
    employment, salary_min = kw.pop("employment", None), kw.pop("salary_min", None)
    remote_mode = kw.pop("remote_mode", None)
    job = Job(id=str(uuid.uuid4()), source_quality=quality, skills=kw.pop("skills", None) or [], **kw)
    job = annotate_job(job, is_remote_flag=is_remote, structured_employment=employment, structured_salary_min=salary_min)
    return job.model_copy(update={"remote_mode": remote_mode}) if remote_mode else job
def _http_json(url: str, *, params: dict | None = None) -> object:
    from app.core.redact import format_httpx_error, redact_error
    from urllib.parse import urlparse

    host = urlparse(url).netloc or "job_source"
    try:
        with httpx.Client(timeout=default_timeout(), headers=_UA) as client:
            r = client.get(url, params=params); r.raise_for_status(); return r.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("job_source", format_httpx_error(exc) or f"{host} request failed") from exc
    except (ValueError, TypeError) as exc:
        raise ServiceFailingError("job_source", redact_error(f"invalid JSON from {host}")) from exc
def _skip(source: str, slug: str, idx: int, reason: str, item: object) -> None:
    keys = list(item.keys())[:8] if isinstance(item, dict) else type(item).__name__
    logger.warning("jobs.source_item_skip", source=source, slug=slug, index=idx, reason=reason, keys=keys)
class JSearchSource:
    name, cost_free, source_quality = "jsearch", False, "aggregator"
    def is_configured(self) -> bool:
        return is_set(settings.JOBS_API_KEY) and is_set(settings.JOBS_API_BASE)
    def is_enabled_for(self, criteria: FetchCriteria) -> bool:
        return self.is_configured()
    def fetch(self, criteria: FetchCriteria, db: Session | None = None) -> list[Job]:
        if not self.is_configured(): raise ServiceNotConfiguredError("Jobs API", "JOBS_API_KEY")
        base = jsearch_params_from_search(criteria.params)
        if criteria.params.remote_mode == "remote" and criteria.params.remote_mode_pref == "hard":
            base = {**base, "remote_jobs_only": "true"}
        raw, _ = fetch_jsearch_raw(criteria.queries or ["software engineer"], base_params=base)
        out: list[Job] = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                _skip("jsearch", "-", i, "not_object", item); continue
            title = str(item.get("job_title") or "").strip()
            desc = str(item.get("job_description") or "").strip()
            apply_url = str(item.get("job_apply_link") or item.get("job_google_link") or "").strip()
            if not title or not desc or not apply_url:
                _skip("jsearch", "-", i, "missing_required", item); continue
            sid = str(item.get("job_id") or item.get("job_google_link") or apply_url)
            loc = ", ".join(str(p).strip() for p in (item.get("job_city"), item.get("job_state"), item.get("job_country")) if p)
            skills_raw = item.get("job_required_skills")
            skills_list: list = skills_raw if isinstance(skills_raw, list) else []
            skills = [str(s).strip() for s in skills_list if str(s).strip()] or _skills(desc, criteria.profile)
            is_remote = item.get("job_is_remote")
            if isinstance(is_remote, str):
                is_remote = is_remote.strip().lower() in {"1", "true", "yes"}
            elif not isinstance(is_remote, bool):
                is_remote = None
            try:
                sal = float(item["job_min_salary"]) if item.get("job_min_salary") is not None else None
            except (TypeError, ValueError):
                sal = None
            out.append(_job(
                source="jsearch", quality="aggregator", source_job_id=sid, title=title,
                company=str(item.get("employer_name") or "Unknown").strip(), location=loc,
                description=desc, apply_url=apply_url, posted_at=parse_iso(item.get("job_posted_at_datetime_utc")),
                skills=skills, is_remote=is_remote, employment=item.get("job_employment_type"), salary_min=sal,
            ))
        return out
class _AtsBoardSource:
    cost_free, source_quality, name, _url_tmpl = True, "direct_ats", "", ""
    def is_configured(self) -> bool:
        return True
    def is_enabled_for(self, criteria: FetchCriteria) -> bool:
        return bool(settings.JOBS_SOURCE_ATS_ENABLED and settings.JOBS_EXTRA_SOURCES_ENABLED)
    def _parse_payload(self, payload: object, slug: str, profile: ResumeProfile) -> list[Job]:
        raise NotImplementedError
    def _fetch_slug(self, slug: str, criteria: FetchCriteria) -> list[Job]:
        from app.db.session import SessionLocal
        session = SessionLocal()
        try:
            cached = board_cache_get(session, self.name, slug)
            if cached is not None:
                try:
                    return self._parse_payload(cached, slug, criteria.profile)
                except ServiceFailingError:
                    board_cache_delete(session, self.name, slug)
                    logger.warning("jobs.board_cache_invalidated", source=self.name, slug=slug)
            payload = _http_json(self._url_tmpl.format(slug=slug))
            jobs = self._parse_payload(payload, slug, criteria.profile)
            board_cache_set(session, self.name, slug, payload)
            return jobs
        finally:
            session.close()
    def fetch(self, criteria: FetchCriteria, db: Session | None = None) -> list[Job]:
        _ = db
        slugs = load_ats_slugs().get(self.name, [])
        if not slugs: return []
        merged: list[Job] = []
        errors = 0
        with ThreadPoolExecutor(max_workers=_ATS_N) as pool:
            futs = {pool.submit(self._fetch_slug, s, criteria): s for s in slugs}
            for fut in as_completed(futs):
                slug = futs[fut]
                try:
                    merged.extend(fut.result())
                except Exception as exc:
                    errors += 1
                    logger.warning("jobs.ats_slug_failed", source=self.name, slug=slug,
                                   error=f"{type(exc).__name__}:{str(exc)[:100]}")
        if errors and not merged: raise ServiceFailingError(self.name, f"all {errors} board fetches failed")
        return merged
def _co(slug: str) -> str:
    return slug.replace("-", " ").title()
class GreenhouseSource(_AtsBoardSource):
    name, _url_tmpl = "greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    def _parse_payload(self, payload: object, slug: str, profile: ResumeProfile) -> list[Job]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list): raise ServiceFailingError("greenhouse", "expected {jobs: [...]}")
        out, company = [], _co(slug)
        for i, item in enumerate(payload["jobs"]):
            if not isinstance(item, dict):
                _skip("greenhouse", slug, i, "not_object", item); continue
            title, apply_url, jid = str(item.get("title") or "").strip(), str(item.get("absolute_url") or "").strip(), item.get("id")
            if not title or not apply_url or jid is None:
                _skip("greenhouse", slug, i, "missing_required", item); continue
            loc_obj = item.get("location")
            location = str((loc_obj or {}).get("name") if isinstance(loc_obj, dict) else (loc_obj or "")).strip()
            content = strip_html(str(item.get("content") or "")) or title
            out.append(_job(
                source="greenhouse", quality="direct_ats", source_job_id=str(jid), title=title,
                company=str(item.get("company_name") or company).strip(), location=location or "Unknown",
                description=content, apply_url=apply_url,
                posted_at=parse_iso(item.get("first_published") or item.get("updated_at")),
                skills=_skills(content, profile),
            ))
        if not out and payload["jobs"]: raise ServiceFailingError("greenhouse", f"no parseable jobs for slug={slug}")
        return out
class LeverSource(_AtsBoardSource):
    name, _url_tmpl = "lever", "https://api.lever.co/v0/postings/{slug}?mode=json"
    def _parse_payload(self, payload: object, slug: str, profile: ResumeProfile) -> list[Job]:
        if not isinstance(payload, list): raise ServiceFailingError("lever", "expected JSON array")
        out, company = [], _co(slug)
        for i, item in enumerate(payload):
            if not isinstance(item, dict):
                _skip("lever", slug, i, "not_object", item); continue
            title = str(item.get("text") or "").strip()
            apply_url = str(item.get("hostedUrl") or item.get("applyUrl") or "").strip()
            jid = item.get("id")
            if not title or not apply_url or not jid:
                _skip("lever", slug, i, "missing_required", item); continue
            cats_raw = item.get("categories")
            cats: dict = cats_raw if isinstance(cats_raw, dict) else {}
            location = str(cats.get("location") or item.get("country") or "").strip()
            desc = str(item.get("descriptionPlain") or item.get("descriptionBodyPlain") or "").strip()
            desc = desc or strip_html(str(item.get("description") or title))
            wp = str(item.get("workplaceType") or "").lower()
            remote_mode = "hybrid" if "hybrid" in wp else ("onsite" if wp in {"on-site","onsite","office"} else None)
            is_remote = True if wp == "remote" else None
            out.append(_job(
                source="lever", quality="direct_ats", source_job_id=str(jid), title=title, company=company,
                location=location or "Unknown", description=desc, apply_url=apply_url,
                posted_at=parse_iso(item.get("createdAt")), skills=_skills(desc, profile),
                is_remote=is_remote, remote_mode=remote_mode,
            ))
        if not out and payload: raise ServiceFailingError("lever", f"no parseable jobs for slug={slug}")
        return out
def _ashby_remote(item: dict) -> tuple[bool | None, str | None]:
    wp = str(item.get("workplaceType") or "").strip().lower()
    if "hybrid" in wp: return None, "hybrid"
    if wp in {"remote", "remotefirst", "remote-first"}:
        return True, "remote"
    if wp in {"onsite", "on-site", "office", "in-office"}: return False, "onsite"
    ir = item.get("isRemote") if isinstance(item.get("isRemote"), bool) else None
    if ir is True: return True, "remote"
    if ir is False:
        return False, None
    return None, None
class AshbySource(_AtsBoardSource):
    name, _url_tmpl = "ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}"
    def _parse_payload(self, payload: object, slug: str, profile: ResumeProfile) -> list[Job]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list): raise ServiceFailingError("ashby", "expected {jobs: [...]}")
        out, company = [], _co(slug)
        for i, item in enumerate(payload["jobs"]):
            if not isinstance(item, dict):
                _skip("ashby", slug, i, "not_object", item); continue
            title = str(item.get("title") or "").strip()
            apply_url = str(item.get("jobUrl") or item.get("applyUrl") or "").strip()
            jid = item.get("id")
            if not title or not apply_url or not jid:
                _skip("ashby", slug, i, "missing_required", item); continue
            desc = str(item.get("descriptionPlain") or "").strip() or strip_html(str(item.get("descriptionHtml") or title))
            location = str(item.get("location") or "").strip()
            is_remote, remote_mode = _ashby_remote(item)
            out.append(_job(
                source="ashby", quality="direct_ats", source_job_id=str(jid), title=title, company=company,
                location=location or ("Remote" if is_remote else "Unknown"), description=desc, apply_url=apply_url,
                posted_at=parse_iso(item.get("publishedAt")), skills=_skills(desc, profile),
                is_remote=is_remote, remote_mode=remote_mode,
                employment=str(item.get("employmentType") or "") or None,
            ))
        if not out and payload["jobs"]: raise ServiceFailingError("ashby", f"no parseable jobs for slug={slug}")
        return out
class RemotiveSource:
    name, cost_free, source_quality = "remotive", True, "feed"
    def is_configured(self) -> bool:
        return True
    def is_enabled_for(self, criteria: FetchCriteria) -> bool:
        return bool(settings.JOBS_EXTRA_SOURCES_ENABLED and settings.JOBS_SOURCE_REMOTIVE_ENABLED
                    and criteria.params.remote_mode in {"remote", "any"})
    def fetch(self, criteria: FetchCriteria, db: Session | None = None) -> list[Job]:
        q = f"{criteria.profile.title} {' '.join(criteria.profile.skills[:2])}".strip()
        payload = _http_json("https://remotive.com/api/remote-jobs", params={"search": q, "limit": "50"})
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list): raise ServiceFailingError("remotive", "expected {jobs: [...]}")
        out: list[Job] = []
        for i, item in enumerate(payload["jobs"]):
            if not isinstance(item, dict):
                _skip("remotive", "-", i, "not_object", item); continue
            title, desc = str(item.get("title") or "").strip(), str(item.get("description") or "").strip()
            apply_url = str(item.get("url") or "").strip()
            if not title or not desc or not apply_url:
                _skip("remotive", "-", i, "missing_required", item); continue
            tags_raw = item.get("tags")
            tags: list = tags_raw if isinstance(tags_raw, list) else []
            skills = [str(t).strip() for t in tags if str(t).strip()] or _skills(desc, criteria.profile)
            out.append(_job(
                source="remotive", quality="feed", source_job_id=str(item.get("id") or apply_url), title=title,
                company=str(item.get("company_name") or "Unknown").strip(),
                location=str(item.get("candidate_required_location") or "Remote").strip() or "Remote",
                description=desc, apply_url=apply_url, posted_at=parse_iso(item.get("publication_date")),
                skills=skills, is_remote=True,
            ))
        return out
class RemoteOKSource:
    name, cost_free, source_quality = "remoteok", True, "feed"
    def is_configured(self) -> bool:
        return True
    def is_enabled_for(self, criteria: FetchCriteria) -> bool:
        return bool(settings.JOBS_EXTRA_SOURCES_ENABLED and settings.JOBS_SOURCE_REMOTEOK_ENABLED
                    and criteria.params.remote_mode in {"remote", "any"})
    def fetch(self, criteria: FetchCriteria, db: Session | None = None) -> list[Job]:
        payload = _http_json("https://remoteok.com/api")
        if not isinstance(payload, list): raise ServiceFailingError("remoteok", "expected JSON array")
        out: list[Job] = []
        for i, item in enumerate(payload):
            if not isinstance(item, dict) or not item.get("id") or not item.get("position"):
                continue
            title = str(item.get("position") or "").strip()
            desc = strip_html(str(item.get("description") or title))
            slug = str(item.get("slug") or item.get("id") or "").strip()
            apply_url = str(item.get("url") or item.get("apply_url") or "").strip()
            if not apply_url and slug:
                apply_url = f"https://remoteOK.com/remote-jobs/{slug}"
            if not title or not apply_url:
                _skip("remoteok", slug or "-", i, "missing_required", item); continue
            tags_raw = item.get("tags")
            tags: list = tags_raw if isinstance(tags_raw, list) else []
            skills = [str(t).strip() for t in tags if str(t).strip()] or _skills(desc, criteria.profile)
            out.append(_job(
                source="remoteok", quality="feed", source_job_id=str(item.get("id")), title=title,
                company=str(item.get("company") or "Unknown").strip(),
                location=str(item.get("location") or "Remote").strip() or "Remote", description=desc,
                apply_url=apply_url, posted_at=parse_iso(item.get("date") or item.get("epoch")),
                skills=skills, is_remote=True,
            ))
        if not out and len(payload) > 1: raise ServiceFailingError("remoteok", "no parseable jobs")
        return out
class AdzunaSource:
    name, cost_free, source_quality = "adzuna", False, "aggregator"
    def is_configured(self) -> bool:
        return is_set(settings.ADZUNA_APP_ID) and is_set(settings.ADZUNA_APP_KEY)
    def is_enabled_for(self, criteria: FetchCriteria) -> bool:
        return self.is_configured()
    def fetch(self, criteria: FetchCriteria, db: Session | None = None) -> list[Job]:
        if not self.is_configured(): raise ServiceNotConfiguredError("Adzuna", "ADZUNA_APP_ID")
        what, where = criteria.profile.title or "software engineer", criteria.profile.location or "United States"
        payload = _http_json(
            "https://api.adzuna.com/v1/api/jobs/us/search/1",
            params={"app_id": settings.ADZUNA_APP_ID or "", "app_key": settings.ADZUNA_APP_KEY or "",
                    "what": what, "where": where, "results_per_page": "50"},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list): raise ServiceFailingError("adzuna", "expected {results: [...]}")
        out: list[Job] = []
        for i, item in enumerate(payload["results"]):
            if not isinstance(item, dict):
                _skip("adzuna", "-", i, "not_object", item); continue
            title, desc = str(item.get("title") or "").strip(), str(item.get("description") or "").strip()
            apply_url = str(item.get("redirect_url") or "").strip()
            if not title or not desc or not apply_url:
                _skip("adzuna", "-", i, "missing_required", item); continue
            co_raw = item.get("company")
            co: dict = co_raw if isinstance(co_raw, dict) else {}
            loc_raw = item.get("location")
            loc: dict = loc_raw if isinstance(loc_raw, dict) else {}
            try:
                sal = float(item["salary_min"]) if item.get("salary_min") is not None else None
            except (TypeError, ValueError):
                sal = None
            out.append(_job(
                source="adzuna", quality="aggregator", source_job_id=str(item.get("id") or apply_url),
                title=title, company=str(co.get("display_name") or "Unknown").strip(),
                location=str(loc.get("display_name") or where).strip(), description=desc,
                apply_url=apply_url, posted_at=parse_iso(item.get("created")),
                skills=_skills(desc, criteria.profile), salary_min=sal,
            ))
        return out
