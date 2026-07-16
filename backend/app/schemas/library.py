from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.jobs import RankedJob, ScoreBreakdown
from app.schemas.resume import ResumeProfile


class IntentProfile(BaseModel):
    role: str
    years_of_experience: float = 0
    location: str = ""
    remote_preference: Literal["remote", "hybrid", "onsite", "any"] = "any"

    def search_text(self) -> str:
        parts = [
            self.role,
            self.location,
            f"{self.years_of_experience} years experience",
            f"remote preference: {self.remote_preference}",
        ]
        return "\n".join(part for part in parts if part)

    def as_query_profile(self) -> ResumeProfile:
        return ResumeProfile(
            title=self.role,
            years_of_experience=self.years_of_experience,
            location=self.location,
            skills=[],
            summary=(
                f"Seeking {self.role} roles with {self.years_of_experience} years experience. "
                f"Location: {self.location}. Remote preference: {self.remote_preference}."
            ),
        )


class IntentSearchRequest(BaseModel):
    role: str
    years_of_experience: float = 0
    location: str = ""
    remote_preference: Literal["remote", "hybrid", "onsite", "any"] = "any"


class IntentSearchResponse(BaseModel):
    search_id: str
    results: list[RankedJob] = Field(default_factory=list)


class LibraryResumeOut(BaseModel):
    id: str
    filename: str
    content_hash: str
    source: str
    profile: ResumeProfile
    created_at: str | None = None
    cluster_id: str | None = None
    cluster_label: str | None = None
    cluster_size: int | None = None


class LibraryResumeListResponse(BaseModel):
    resumes: list[LibraryResumeOut] = Field(default_factory=list)
    total: int = 0
    distinct_versions: int = 0


class IngestFileResult(BaseModel):
    filename: str
    status: Literal["cached", "parsed", "failed", "skipped"]
    resume_id: str | None = None
    # Plain-language reason for failed/skipped (never includes secrets or raw URLs).
    reason: str | None = None


class DriveSyncRequest(BaseModel):
    folder_url: str


class DriveSyncResponse(BaseModel):
    folder_id: str
    files_seen: int
    files_parsed: int
    files_skipped: int
    files_ignored: int = 0
    files_failed: int = 0
    resumes: list[LibraryResumeOut] = Field(default_factory=list)
    file_results: list[IngestFileResult] = Field(default_factory=list)
    units_indexed: bool | None = None
    units_index_warning: str | None = None


class LibraryUploadResponse(BaseModel):
    files_received: int
    files_parsed: int
    files_skipped: int
    files_ignored: int = 0
    resumes: list[LibraryResumeOut] = Field(default_factory=list)
    distinct_versions: int = 0
    units_indexed: bool | None = None
    units_index_warning: str | None = None
    file_results: list[IngestFileResult] = Field(default_factory=list)


class ResumeCandidate(BaseModel):
    resume_id: str
    filename: str
    profile: ResumeProfile
    content_hash: str | None = None
    cluster_id: str | None = None


class RequirementCoverage(BaseModel):
    requirement: str
    status: Literal["hit", "miss"]
    evidence: str | None = None


class AlignmentRow(BaseModel):
    requirement: str
    kind: str = "must"
    category: str = "skill"
    weight: float = 1.0
    evidence_unit: str | None = None
    # Post-floor (or hard-match) score 0–1; UI prefers strength bucket over raw %.
    evidence_score: float = 0.0
    strength: Literal["none", "weak", "solid", "strong"] = "none"
    status: Literal["hit", "miss"] = "miss"


class TournamentRecord(BaseModel):
    ran: bool = False
    comparisons: int = 0
    cache_hits: int = 0
    cost_usd: float | None = None
    wins: int = 0
    borda_score: float = 0.0
    contested: bool = False
    overrode_coverage: bool = False
    reasons: list[str] = Field(default_factory=list)


class RankedResumeRecommendation(BaseModel):
    resume_id: str
    filename: str
    match_score: float
    score_breakdown: ScoreBreakdown
    coverage: list[RequirementCoverage] = Field(default_factory=list)
    coverage_score: float = 0.0
    # Count of must-have requirements with evidence above floor (hit).
    must_haves_hit: int = 0
    must_haves_total: int = 0
    alignment: list[AlignmentRow] = Field(default_factory=list)
    cluster_id: str | None = None
    cluster_label: str | None = None
    cluster_size: int | None = None
    tournament: TournamentRecord | None = None
    content_hash: str | None = None


class RecommendResumesResponse(BaseModel):
    job_id: str
    recommendations: list[RankedResumeRecommendation] = Field(default_factory=list)
    tournament_comparisons: int = 0
    tournament_ran: bool = False


class RecommendFromJdRequest(BaseModel):
    job_description: str
    title: str = ""
    company: str = ""
    location: str = ""
    apply_url: str = ""


class RecommendFromJdResponse(BaseModel):
    job_id: str
    job_title: str = ""
    job_company: str = ""
    recommendations: list[RankedResumeRecommendation] = Field(default_factory=list)
    tournament_comparisons: int = 0
    tournament_ran: bool = False
