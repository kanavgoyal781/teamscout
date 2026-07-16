"""Public /stats response whitelist."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
class PublicStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs_ranked_total: int = Field(ge=0)
    resumes_parsed_total: int = Field(ge=0)
    teams_discovered_total: int = Field(ge=0)
    median_rank_latency_ms: float | None = None
    total_llm_cost_usd: float = Field(ge=0)
