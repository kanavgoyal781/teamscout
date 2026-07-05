from dataclasses import dataclass

from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile, WorkExperience


@dataclass(frozen=True)
class ResumePickCase:
    name: str
    job: Job
    resumes: list[ResumeProfile]
    best_resume_index: int


def _job(
    job_id: str,
    title: str,
    skills: list[str],
    description: str,
) -> Job:
    return Job(
        id=job_id,
        source="fixture",
        source_job_id=job_id,
        title=title,
        company="TargetCo",
        location="Remote",
        description=description,
        apply_url=f"https://example.com/jobs/{job_id}",
        posted_at=None,
        skills=skills,
    )


def _resume(
    name: str,
    title: str,
    skills: list[str],
    summary: str,
    *,
    bullets: list[str] | None = None,
) -> ResumeProfile:
    return ResumeProfile(
        name=name,
        title=title,
        years_of_experience=6,
        location="Remote",
        skills=skills,
        work_experience=[
            WorkExperience(title=title, company="PastCo", bullets=bullets or [summary]),
        ],
        summary=summary,
    )


CASES: list[ResumePickCase] = [
    ResumePickCase(
        name="python_backend",
        job=_job(
            "case-1",
            "Senior Python Backend Engineer",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
            "Build Python APIs with FastAPI, PostgreSQL, and AWS.",
        ),
        resumes=[
            _resume("A", "Java Engineer", ["Java", "Spring"], "Java microservices only"),
            _resume(
                "B",
                "Senior Python Backend Engineer",
                ["Python", "FastAPI", "PostgreSQL", "AWS"],
                "Shipped FastAPI services on AWS with PostgreSQL",
                bullets=["Built FastAPI APIs backed by PostgreSQL on AWS"],
            ),
            _resume("C", "Frontend Engineer", ["React", "TypeScript"], "React UI specialist"),
        ],
        best_resume_index=1,
    ),
    ResumePickCase(
        name="data_scientist",
        job=_job(
            "case-2",
            "Senior Data Scientist",
            ["Python", "PyTorch", "SQL", "MLflow"],
            "Own ML models in Python and PyTorch with SQL and MLflow.",
        ),
        resumes=[
            _resume("A", "Product Manager", ["Roadmaps"], "PM with no ML"),
            _resume(
                "B",
                "Senior Data Scientist",
                ["Python", "PyTorch", "SQL", "MLflow"],
                "Production ML with PyTorch and MLflow",
                bullets=["Deployed PyTorch models tracked in MLflow"],
            ),
            _resume("C", "Data Analyst", ["Excel", "SQL"], "Reporting analyst"),
        ],
        best_resume_index=1,
    ),
    ResumePickCase(
        name="devops",
        job=_job(
            "case-3",
            "DevOps Engineer",
            ["Kubernetes", "Terraform", "AWS", "CI/CD"],
            "Manage Kubernetes clusters with Terraform and AWS CI/CD.",
        ),
        resumes=[
            _resume(
                "A",
                "DevOps Engineer",
                ["Kubernetes", "Terraform", "AWS", "CI/CD"],
                "Operated Kubernetes on AWS with Terraform pipelines",
                bullets=["Managed EKS clusters and Terraform modules"],
            ),
            _resume("B", "Support Engineer", ["Ticketing"], "Helpdesk support"),
            _resume("C", "Backend Engineer", ["Python"], "Application developer"),
        ],
        best_resume_index=0,
    ),
    ResumePickCase(
        name="mobile_ios",
        job=_job(
            "case-4",
            "Senior iOS Engineer",
            ["Swift", "UIKit", "SwiftUI"],
            "Build iOS apps in Swift with UIKit and SwiftUI.",
        ),
        resumes=[
            _resume("A", "Android Engineer", ["Kotlin"], "Android apps"),
            _resume("B", "Web Engineer", ["React"], "React web apps"),
            _resume(
                "C",
                "Senior iOS Engineer",
                ["Swift", "UIKit", "SwiftUI"],
                "Shipped SwiftUI and UIKit features",
                bullets=["Led SwiftUI migration for flagship iOS app"],
            ),
        ],
        best_resume_index=2,
    ),
    ResumePickCase(
        name="security",
        job=_job(
            "case-5",
            "Security Engineer",
            ["AWS", "IAM", "SOC2", "Python"],
            "Own cloud security, IAM, and SOC2 controls with Python automation.",
        ),
        resumes=[
            _resume("A", "Network Admin", ["Cisco"], "Network operations"),
            _resume(
                "B",
                "Security Engineer",
                ["AWS", "IAM", "SOC2", "Python"],
                "Built IAM guardrails and SOC2 automation in Python on AWS",
                bullets=["Automated IAM reviews and SOC2 evidence collection in Python"],
            ),
            _resume("C", "QA Engineer", ["Selenium"], "Manual QA"),
        ],
        best_resume_index=1,
    ),
]