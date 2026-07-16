"""Services; lazy `from app.services import name` → domain module.

Package names under app.services/ (ranking, resume, team, …) always win over _L —
`from app.services import ranking` is the ranking package (proxies engine via
ranking/__init__.__getattr__). Monkeypatch internal engine symbols on
app.services.ranking.engine, not the package. _L covers flat legacy aliases only
(no package-name collisions).
"""
from __future__ import annotations
import importlib
from typing import Any
_L={
"calibration":"app.services.ranking.calibration","cross_encoder":"app.services.ranking.cross_encoder",
"drive":"app.services.library.drive","email_reveal":"app.services.team.email_reveal",
"embeddings":"app.services.inference.embeddings","feedback_store":"app.services.feedback.store",
"health":"app.services.ops.health","hybrid_rank":"app.services.ranking.hybrid",
"jd_decompose":"app.services.resume.jd_decompose","job_boards":"app.services.jobs_svc.boards",
"job_dedup":"app.services.jobs_svc.dedup","job_facets":"app.services.jobs_svc.facets",
"job_filters":"app.services.jobs_svc.filters","job_sources":"app.services.jobs_svc.sources",
"jobs":"app.services.jobs_svc.fetch","jd_metadata":"app.services.jobs_svc.jd_metadata","jobs_store":"app.services.jobs_svc.store",
"jsearch_client":"app.services.jobs_svc.jsearch","library_store":"app.services.library.store",
"listwise":"app.services.ranking.listwise","llm":"app.services.inference.llm",
"observability":"app.services.ops.observability","observability_otlp":"app.services.ops.otlp",
"outreach_draft":"app.services.feedback.outreach_draft","pairwise_tournament":"app.services.resume.tournament",
"parser":"app.services.resume.parser","query_expand":"app.services.ranking.query_expand",
"ranking_config":"app.services.ranking.config",
"ranking_math":"app.services.ranking.math","ranking_math_align":"app.services.ranking.math_align",
"resume_justify":"app.services.resume.justify","resume_ranking":"app.services.resume.ranking",
"resume_units":"app.services.resume.units","sumble":"app.services.team.sumble",
"sumble_client":"app.services.team.client","sumble_jobs":"app.services.team.jobs_api",
"team_extract":"app.services.team.extract","team_search":"app.services.team.search",
}
def __getattr__(n:str)->Any:
    t=_L.get(n)
    if not t: raise AttributeError(n)
    return importlib.import_module(t)
