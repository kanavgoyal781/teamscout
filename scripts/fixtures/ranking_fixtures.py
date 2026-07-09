from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile, WorkExperience


@dataclass(frozen=True)
class LabeledJob:
    job: Job
    relevance: float


@dataclass(frozen=True)
class PersonaFixture:
    name: str
    profile: ResumeProfile
    jobs: list[LabeledJob]


def _posted(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _job(
    job_id: str,
    title: str,
    company: str,
    location: str,
    skills: list[str],
    description: str,
    *,
    days_ago: int = 3,
) -> Job:
    return Job(
        id=job_id,
        source="fixture",
        source_job_id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        apply_url=f"https://example.com/jobs/{job_id}",
        posted_at=_posted(days_ago),
        skills=skills,
    )


DATA_SCIENTIST = PersonaFixture(
    name="data_scientist",
    profile=ResumeProfile(
        name="Alex Rivera",
        title="Senior Data Scientist",
        years_of_experience=6,
        location="New York, NY",
        skills=["Python", "SQL", "PyTorch", "scikit-learn", "pandas", "A/B testing", "MLflow"],
        work_experience=[
            WorkExperience(
                title="Data Scientist",
                company="Insight Labs",
                bullets=["Built churn models with gradient boosting", "Ran experiment analysis for product teams"],
            )
        ],
        summary="Data scientist focused on production ML, experimentation, and analytics.",
    ),
    jobs=[
        LabeledJob(
            _job(
                "ds-1",
                "Senior Data Scientist",
                "ModelWorks",
                "New York, NY",
                ["Python", "PyTorch", "SQL", "MLflow"],
                "Own end-to-end ML models in Python and PyTorch. Ship experiments with A/B testing and MLflow.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "ds-2",
                "Machine Learning Engineer",
                "SignalAI",
                "Remote",
                ["Python", "PyTorch", "pandas", "scikit-learn"],
                "Build training pipelines and deploy PyTorch models. Strong SQL and pandas required.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "ds-3",
                "Applied Scientist",
                "RetailML",
                "Boston, MA",
                ["Python", "scikit-learn", "A/B testing"],
                "Develop predictive models and analyze experiments with Python and scikit-learn.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "ds-4",
                "Analytics Engineer",
                "DataHub",
                "Chicago, IL",
                ["SQL", "dbt", "Python"],
                "Build analytics models in SQL and dbt with light Python scripting.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "ds-5",
                "Frontend Engineer",
                "WebCo",
                "Austin, TX",
                ["React", "TypeScript", "CSS"],
                "Build customer-facing React dashboards and design systems.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "ds-6",
                "DevOps Engineer",
                "CloudOps",
                "Seattle, WA",
                ["Terraform", "Kubernetes", "AWS"],
                "Manage infrastructure as code and Kubernetes clusters.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "ds-7",
                "Data Analyst",
                "FinanceCo",
                "New York, NY",
                ["SQL", "Excel", "Tableau"],
                "Produce BI dashboards and SQL reports for finance stakeholders.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "ds-8",
                "Research Scientist",
                "BioAI",
                "San Diego, CA",
                ["Python", "PyTorch", "statistics"],
                "Research deep learning methods for biological sequence modeling.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "ds-9",
                "Product Manager",
                "SaaSCo",
                "Remote",
                ["roadmaps", "stakeholders"],
                "Own product strategy and roadmap for B2B SaaS platform.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "ds-10",
                "MLOps Engineer",
                "PlatformML",
                "Denver, CO",
                ["MLflow", "Python", "Kubernetes"],
                "Operate MLflow model registry and deployment pipelines.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "ds-11",
                "Quantitative Analyst",
                "CapitalOne",
                "New York, NY",
                ["Python", "statistics", "SQL"],
                "Build forecasting models and statistical analyses in Python.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "ds-12",
                "Sales Engineer",
                "AdTech",
                "Remote",
                ["presentations", "CRM"],
                "Support enterprise sales with technical product demos.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "ds-13",
                "NLP Data Scientist",
                "LanguageLab",
                "San Francisco, CA",
                ["Python", "PyTorch", "NLP"],
                "Fine-tune transformer models for text classification and retrieval.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "ds-14",
                "Backend Engineer",
                "APIWorks",
                "Portland, OR",
                ["Java", "Spring", "PostgreSQL"],
                "Build transactional APIs with Java Spring Boot.",
            ),
            0.0,
        ),
    ],
)

BACKEND_ENGINEER = PersonaFixture(
    name="backend_engineer",
    profile=ResumeProfile(
        name="Jordan Lee",
        title="Senior Backend Engineer",
        years_of_experience=8,
        location="San Francisco, CA",
        skills=["Python", "FastAPI", "PostgreSQL", "Redis", "AWS", "Docker", "Kubernetes"],
        work_experience=[
            WorkExperience(
                title="Backend Engineer",
                company="Acme Corp",
                bullets=["Built FastAPI services at scale", "Operated PostgreSQL and Redis clusters"],
            )
        ],
        summary="Backend engineer building reliable APIs, data services, and cloud infrastructure.",
    ),
    jobs=[
        LabeledJob(
            _job(
                "be-1",
                "Senior Backend Engineer",
                "ScaleAPI",
                "San Francisco, CA",
                ["Python", "FastAPI", "PostgreSQL", "Redis"],
                "Design FastAPI microservices backed by PostgreSQL and Redis on AWS.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "be-2",
                "Platform Engineer",
                "CloudNative",
                "Remote",
                ["Kubernetes", "Docker", "AWS"],
                "Run container platforms on Kubernetes with Docker and AWS tooling.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "be-3",
                "Python Backend Developer",
                "FinAPI",
                "New York, NY",
                ["Python", "FastAPI", "PostgreSQL"],
                "Implement payment APIs in Python and FastAPI with PostgreSQL persistence.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "be-4",
                "Site Reliability Engineer",
                "ObserveInc",
                "Seattle, WA",
                ["Kubernetes", "AWS", "monitoring"],
                "Improve reliability of distributed systems and on-call operations.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "be-5",
                "Frontend Engineer",
                "UIWorks",
                "Los Angeles, CA",
                ["React", "Next.js", "TypeScript"],
                "Build responsive web apps with React and Next.js.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "be-6",
                "Data Scientist",
                "ModelTeam",
                "Boston, MA",
                ["Python", "PyTorch", "pandas"],
                "Train ML models for recommendation systems.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "be-7",
                "Backend Engineer",
                "CommerceCo",
                "Austin, TX",
                ["Go", "gRPC", "PostgreSQL"],
                "Build high-throughput commerce services in Go.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "be-8",
                "Infrastructure Engineer",
                "InfraOps",
                "Denver, CO",
                ["AWS", "Terraform", "Docker"],
                "Provision AWS infrastructure with Terraform and Docker.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "be-9",
                "Java Backend Engineer",
                "EnterpriseSoft",
                "Chicago, IL",
                ["Java", "Spring", "Kafka"],
                "Maintain enterprise Java services and Kafka integrations.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "be-10",
                "API Engineer",
                "DevTools",
                "Remote",
                ["Python", "FastAPI", "Redis", "Docker"],
                "Develop developer-facing APIs with FastAPI, Redis caching, and Docker.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "be-11",
                "Mobile Engineer",
                "AppCo",
                "Miami, FL",
                ["Swift", "iOS", "UIKit"],
                "Ship iOS applications and mobile SDKs.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "be-12",
                "Database Administrator",
                "DataStore",
                "Phoenix, AZ",
                ["PostgreSQL", "backups", "replication"],
                "Administer PostgreSQL clusters and replication.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "be-13",
                "Staff Backend Engineer",
                "GrowthCo",
                "San Francisco, CA",
                ["Python", "FastAPI", "Kubernetes", "AWS"],
                "Lead backend architecture for Python FastAPI platform on Kubernetes.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "be-14",
                "Technical Writer",
                "DocsInc",
                "Remote",
                ["documentation", "API guides"],
                "Write API documentation and developer guides.",
            ),
            0.0,
        ),
    ],
)

FRONTEND_ENGINEER = PersonaFixture(
    name="frontend_engineer",
    profile=ResumeProfile(
        name="Sam Patel",
        title="Senior Frontend Engineer",
        years_of_experience=7,
        location="Austin, TX",
        skills=["React", "TypeScript", "Next.js", "CSS", "Tailwind", "testing-library", "GraphQL"],
        work_experience=[
            WorkExperience(
                title="Frontend Engineer",
                company="ProductCo",
                bullets=["Built Next.js apps with TypeScript", "Improved accessibility and test coverage"],
            )
        ],
        summary="Frontend engineer focused on React, TypeScript, and polished product UI.",
    ),
    jobs=[
        LabeledJob(
            _job(
                "fe-1",
                "Senior Frontend Engineer",
                "DesignHub",
                "Austin, TX",
                ["React", "TypeScript", "Next.js", "CSS"],
                "Lead React and Next.js product development with TypeScript and CSS.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "fe-2",
                "Frontend Developer",
                "ShopNow",
                "Remote",
                ["React", "TypeScript", "Tailwind"],
                "Build ecommerce UI with React, TypeScript, and Tailwind CSS.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "fe-3",
                "UI Engineer",
                "MediaStream",
                "Los Angeles, CA",
                ["React", "CSS", "testing-library"],
                "Implement accessible React components with testing-library coverage.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "fe-4",
                "Full Stack Engineer",
                "StartupX",
                "San Francisco, CA",
                ["React", "Node.js", "PostgreSQL"],
                "Ship features across React frontend and Node.js backend.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "fe-5",
                "Backend Engineer",
                "APIWorks",
                "Seattle, WA",
                ["Python", "FastAPI", "PostgreSQL"],
                "Develop backend APIs with Python FastAPI.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "fe-6",
                "Data Engineer",
                "PipelineCo",
                "Denver, CO",
                ["Spark", "Airflow", "SQL"],
                "Build batch data pipelines with Spark and Airflow.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "fe-7",
                "React Native Engineer",
                "MobileFirst",
                "New York, NY",
                ["React", "TypeScript", "mobile"],
                "Build cross-platform mobile apps with React Native and TypeScript.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "fe-8",
                "Web Developer",
                "AgencyCo",
                "Chicago, IL",
                ["HTML", "CSS", "JavaScript"],
                "Create marketing websites with HTML, CSS, and JavaScript.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "fe-9",
                "Design Systems Engineer",
                "SystemUI",
                "Remote",
                ["React", "TypeScript", "Tailwind", "CSS"],
                "Maintain design system components in React and Tailwind.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "fe-10",
                "QA Engineer",
                "QualityLab",
                "Portland, OR",
                ["Selenium", "manual testing"],
                "Execute manual and automated QA test plans.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "fe-11",
                "Frontend Engineer",
                "GraphApp",
                "Boston, MA",
                ["React", "GraphQL", "TypeScript"],
                "Build data-rich React apps consuming GraphQL APIs.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "fe-12",
                "Product Designer",
                "CreativeCo",
                "Miami, FL",
                ["Figma", "prototyping"],
                "Design product flows and prototypes in Figma.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "fe-13",
                "Staff Frontend Engineer",
                "PlatformUI",
                "Austin, TX",
                ["React", "Next.js", "TypeScript", "testing-library"],
                "Own frontend architecture for Next.js platform with strong test coverage.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "fe-14",
                "DevOps Engineer",
                "InfraWorks",
                "Remote",
                ["Kubernetes", "CI/CD"],
                "Manage CI/CD pipelines and Kubernetes deployments.",
            ),
            0.0,
        ),
    ],
)

# Mid-level persona: must prefer mid/senior-appropriate roles over staff/principal
# and must prefer jobs whose hard requirements are covered (not keyword-only titles).
MID_LEVEL_ENGINEER = PersonaFixture(
    name="mid_level_engineer",
    profile=ResumeProfile(
        name="Sam Chen",
        title="Software Engineer",
        years_of_experience=3.0,
        location="Remote",
        skills=["Python", "SQL", "Django", "PostgreSQL", "Docker", "REST APIs"],
        work_experience=[
            WorkExperience(
                title="Software Engineer",
                company="StartupCo",
                bullets=[
                    "Built Django REST APIs on PostgreSQL",
                    "Owned Dockerized services and SQL reporting",
                ],
            )
        ],
        summary="Mid-level software engineer with 3 years building Python web APIs.",
    ),
    jobs=[
        LabeledJob(
            _job(
                "mid-1",
                "Software Engineer",
                "APIStart",
                "Remote",
                ["Python", "Django", "PostgreSQL", "Docker"],
                "Requirements: 2-4 years of experience with Python and Django. "
                "Build REST APIs on PostgreSQL. Docker experience preferred.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "mid-2",
                "Backend Engineer (Mid-level)",
                "CloudSoft",
                "Remote",
                ["Python", "SQL", "REST APIs"],
                "Minimum 3 years experience. Day-to-day: Python services, SQL, REST APIs.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "mid-3",
                "Junior Software Engineer",
                "FreshCode",
                "Austin, TX",
                ["Python", "SQL"],
                "Entry-level friendly. 0-2 years. Mentorship on Python and SQL.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "mid-4",
                "Staff Software Engineer",
                "MegaScale",
                "Remote",
                ["Python", "distributed systems", "leadership"],
                "Staff Software Engineer. Minimum 10+ years of experience. "
                "Lead multi-team architecture and mentor seniors. Python preferred.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "mid-5",
                "Principal Engineer",
                "EnterpriseAI",
                "New York, NY",
                ["Python", "architecture", "strategy"],
                "Principal Engineer. 12+ years required. Set technical strategy org-wide.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "mid-6",
                "Senior Software Engineer",
                "GrowthLabs",
                "Remote",
                ["Python", "Django", "AWS"],
                "Senior role. Requires 6+ years of professional experience with Python and Django.",
            ),
            1.0,
        ),
        LabeledJob(
            _job(
                "mid-7",
                "Python Developer",
                "DataPipe",
                "Chicago, IL",
                ["Python", "PostgreSQL", "Docker"],
                "Requirements: Python, PostgreSQL, Docker. 2+ years of experience. "
                "Build data-adjacent APIs and ETL helpers.",
            ),
            3.0,
        ),
        LabeledJob(
            _job(
                "mid-8",
                "Software Engineer",
                "BuzzwordAI",
                "Remote",
                ["Python"],
                "Software Engineer title only. Looking for Kubernetes operators, Go, "
                "and 8+ years of distributed systems leadership. Python optional.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "mid-9",
                "Director of Engineering",
                "BigCorp",
                "San Francisco, CA",
                ["leadership", "hiring", "roadmap"],
                "Director of Engineering. 15+ years. Own org roadmap and hiring.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "mid-10",
                "Full Stack Engineer",
                "WebShop",
                "Remote",
                ["Python", "Django", "React"],
                "Requirements: Django and React. 3 years minimum. Build product features end-to-end.",
            ),
            2.0,
        ),
        LabeledJob(
            _job(
                "mid-11",
                "ML Engineer",
                "ModelOps",
                "Remote",
                ["PyTorch", "CUDA", "MLOps"],
                "Must have: PyTorch, CUDA, production MLOps. 5+ years ML systems experience.",
            ),
            0.0,
        ),
        LabeledJob(
            _job(
                "mid-12",
                "Backend Engineer",
                "PayAPI",
                "Remote",
                ["Python", "PostgreSQL", "REST APIs", "Docker"],
                "Requirements: Python, PostgreSQL, REST APIs, Docker. "
                "Around 3 years of backend experience preferred.",
            ),
            3.0,
        ),
    ],
)

PERSONAS = [DATA_SCIENTIST, BACKEND_ENGINEER, FRONTEND_ENGINEER, MID_LEVEL_ENGINEER]

# Fit-signal-only corpus (no embeddings required) for seniority + requirements benchmarks.
FIT_SIGNAL_PERSONAS = [MID_LEVEL_ENGINEER]