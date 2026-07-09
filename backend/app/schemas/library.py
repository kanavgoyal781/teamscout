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


class LibraryResumeListResponse(BaseModel):
    resumes: list[LibraryResumeOut] = Field(default_factory=list)
    total: int = 0


class DriveSyncRequest(BaseModel):
    folder_url: str


class DriveSyncResponse(BaseModel):
    folder_id: str
    files_seen: int
    files_parsed: int
    files_skipped: int
    files_ignored: int = 0
    resumes: list[LibraryResumeOut] = Field(default_factory=list)


class LibraryUploadResponse(BaseModel):
    files_received: int
    files_parsed: int
    files_skipped: int
    files_ignored: int = 0
    resumes: list[LibraryResumeOut] = Field(default_factory=list)


class ResumeCandidate(BaseModel):
    resume_id: str
    filename: str
    profile: ResumeProfile


class RequirementCoverage(BaseModel):
    requirement: str
    status: Literal["hit", "miss"]
    evidence: str | None = None


class RankedResumeRecommendation(BaseModel):
    resume_id: str
    filename: str
    match_score: float
    score_breakdown: ScoreBreakdown
    coverage: list[RequirementCoverage] = Field(default_factory=list)


class RecommendResumesResponse(BaseModel):
    job_id: str
    recommendations: list[RankedResumeRecommendation] = Field(default_factory=list)
