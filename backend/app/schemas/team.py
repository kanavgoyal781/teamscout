from pydantic import BaseModel, Field


class TeamExtraction(BaseModel):
    team_name: str = ""
    department: str = ""
    likely_hiring_titles: list[str] = Field(default_factory=list)


class TeamExtractionResponse(BaseModel):
    job_id: str
    extraction_id: str
    extraction: TeamExtraction


class FindTeamRequest(BaseModel):
    extraction_id: str
    search_id: str | None = None


class ContactOut(BaseModel):
    id: str
    full_name: str
    title: str | None = None
    company: str | None = None
    team: str | None = None
    seniority: str | None = None
    sumble_person_id: str | None = None
    email_revealed: bool = False
    email: str | None = None


class FindTeamResponse(BaseModel):
    job_id: str
    contacts: list[ContactOut] = Field(default_factory=list)
    credits_used: int = 0
    team_searched: bool = True


class TeamListResponse(BaseModel):
    job_id: str
    contacts: list[ContactOut] = Field(default_factory=list)
    extraction_id: str | None = None
    extraction: TeamExtraction | None = None
    team_searched: bool = False


class EmailRevealResponse(BaseModel):
    contact_id: str
    cost_credits: int | None = None
    cached: bool = False
    email: str | None = None
    status: str = "pending"