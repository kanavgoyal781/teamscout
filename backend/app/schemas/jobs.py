from datetime import datetime

from pydantic import BaseModel, Field


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

    def embedding_text(self) -> str:
        skills_text = ", ".join(self.skills)
        description = self.description[:1500]
        return f"{self.title}\n{skills_text}\n{description}"

    def lexical_text(self) -> str:
        return f"{self.title} {self.company} {self.location} {' '.join(self.skills)} {self.description}"


class ScoreBreakdown(BaseModel):
    llm_fit: float
    rrf_normalized: float
    dense_rank_score: float = 0.0
    skill_jaccard: float
    recency: float
    experience_fit: float | None = None
    final_score: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    rationale: str = ""


class RankedJob(BaseModel):
    job: Job
    match_score: float
    score_breakdown: ScoreBreakdown
