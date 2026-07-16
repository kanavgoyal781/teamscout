from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PrefMode = Literal["hard", "soft"]
RemoteMode = Literal["remote", "hybrid", "onsite", "any"]
EmploymentType = Literal["fulltime", "contractor", "any"]
DateWindow = Literal["day", "3days", "week", "month"]
SeniorityLevel = Literal["intern", "junior", "mid", "senior", "lead", "any"]
SourceQuality = Literal["direct_ats", "aggregator", "feed"]


class Job(BaseModel):
    id: str
    source: str
    source_job_id: str
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    posted_at: datetime | None = None
    skills: list[str] = Field(default_factory=list)
    source_quality: SourceQuality = "aggregator"
    seniority: str | None = None
    remote_mode: str | None = None  # remote|hybrid|onsite|unknown
    employment_type: str | None = None  # fulltime|contractor|parttime|unknown
    salary_min: float | None = None
    salary_unknown: bool = True
    duplicates_count: int = 1

    def embedding_text(self) -> str:
        skills_text = ", ".join(self.skills)
        description = self.description[:1500]
        return f"{self.title}\n{skills_text}\n{description}"

    def lexical_text(self) -> str:
        return f"{self.title} {self.company} {self.location} {' '.join(self.skills)} {self.description}"

    def dedup_embedding_text(self) -> str:
        return f"{self.company}\n{self.title}\n{self.description[:500]}"


class ScoreBreakdown(BaseModel):
    llm_fit: float
    rrf_normalized: float
    dense_rank_score: float = 0.0
    skill_jaccard: float
    recency: float
    experience_fit: float | None = None
    requirements_met: float | None = None
    cross_encoder: float = 0.0
    required_years: float | None = None
    soft_boost: float = 0.0
    final_score: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    rationale: str = ""
    match_likelihood: float | None = None


class RankedJob(BaseModel):
    job: Job
    match_score: float
    score_breakdown: ScoreBreakdown


class SearchParams(BaseModel):
    remote_mode: RemoteMode = "any"
    remote_mode_pref: PrefMode = "soft"
    employment_type: EmploymentType = "any"
    employment_type_pref: PrefMode = "soft"
    date_window: DateWindow = "month"
    seniority: SeniorityLevel = "any"
    seniority_pref: PrefMode = "soft"
    min_salary: int | None = None
    min_salary_pref: PrefMode = "soft"
    use_expand: bool = True


class FacetBucket(BaseModel):
    value: str
    count: int


class JobFacets(BaseModel):
    company: list[FacetBucket] = Field(default_factory=list)
    seniority: list[FacetBucket] = Field(default_factory=list)
    remote_mode: list[FacetBucket] = Field(default_factory=list)
    salary_bucket: list[FacetBucket] = Field(default_factory=list)
    posted_age: list[FacetBucket] = Field(default_factory=list)
    source: list[FacetBucket] = Field(default_factory=list)


class SourceCounts(BaseModel):
    fetched: int = 0
    kept_after_filters: int = 0
    deduped_away: int = 0
    errors: int = 0


class DroppedCounts(BaseModel):
    recency: int = 0
    missing_apply_url: int = 0
    missing_title_or_description: int = 0
    hard_seniority: int = 0
    hard_remote: int = 0
    hard_employment: int = 0
    hard_salary: int = 0
    exact_duplicate: int = 0
    embedding_duplicate: int = 0
    fetch_cap: int = 0

    def as_dict(self) -> dict[str, int]:
        return {k: v for k, v in self.model_dump().items() if v > 0}

    def merge(self, other: "DroppedCounts") -> "DroppedCounts":
        data = self.model_dump()
        for key, value in other.model_dump().items():
            data[key] = data.get(key, 0) + value
        return DroppedCounts(**data)
