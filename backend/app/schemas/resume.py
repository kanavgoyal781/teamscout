from pydantic import BaseModel, Field
class WorkExperience(BaseModel):
    title: str
    company: str
    bullets: list[str] = Field(default_factory=list)
class ResumeProfile(BaseModel):
    name: str = ""
    title: str = ""
    years_of_experience: float = 0
    location: str = ""
    skills: list[str] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    summary: str = ""
    def search_text(self) -> str:
        parts = [
            self.title,
            self.location,
            ", ".join(self.skills),
            self.summary,
        ]
        for role in self.work_experience:
            parts.append(role.title)
            parts.append(role.company)
            parts.extend(role.bullets)
        return "\n".join(p for p in parts if p)
