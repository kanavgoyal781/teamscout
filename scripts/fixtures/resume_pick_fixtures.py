"""Hard near-duplicate resume libraries for requirement-level pick eval.

Each library shares ≥90% of line character-mass across near-dups (measured via
pairwise_shared_text_ratio); exactly one variant carries a decisive evidence
bullet that matches the JD. Asserts measured similarity ≥ 0.9 and that
distinctive decisive tokens do not appear in decoy first-bullets.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile, WorkExperience


@dataclass(frozen=True)
class ResumePickCase:
    name: str
    job: Job
    resumes: list[ResumeProfile]
    best_resume_index: int
    min_near_dup_similarity: float


def _job(job_id: str, title: str, skills: list[str], description: str) -> Job:
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


def pairwise_shared_text_ratio(a: ResumeProfile, b: ResumeProfile) -> float:
    """Character-mass fraction of identical lines (honest ≥90% shared-text measure).

    Near-dup libraries share long identical bullet blocks; only one decisive line differs.
    Token-set Jaccard understates shared mass when decoy lines introduce unique words.
    """
    lines_a = [ln.strip() for ln in a.search_text().splitlines() if ln.strip()]
    lines_b = [ln.strip() for ln in b.search_text().splitlines() if ln.strip()]
    if not lines_a and not lines_b:
        return 1.0
    set_a, set_b = set(lines_a), set(lines_b)
    shared = set_a & set_b
    shared_mass = sum(len(ln) for ln in shared)
    # Count multiplicity: each profile contributes mass of shared lines present
    mass_a = sum(len(ln) for ln in lines_a if ln in shared)
    mass_b = sum(len(ln) for ln in lines_b if ln in shared)
    total = sum(len(ln) for ln in lines_a) + sum(len(ln) for ln in lines_b)
    if total <= 0:
        return 1.0
    return (mass_a + mass_b) / total


def min_pairwise_similarity(resumes: list[ResumeProfile], *, among: list[int] | None = None) -> float:
    idxs = among if among is not None else list(range(len(resumes)))
    best = 1.0
    for i in range(len(idxs)):
        for j in range(i + 1, len(idxs)):
            sim = pairwise_shared_text_ratio(resumes[idxs[i]], resumes[idxs[j]])
            best = min(best, sim)
    return best


_SHARED_PAD = (
    "Professional summary pad: experienced engineer delivering reliable software for enterprise customers across cloud platforms with strong collaboration skills communication ownership and operational excellence. Repeated shared experience block for near-duplicate libraries used in ranking evaluation only. Responsibilities included roadmap planning stakeholder alignment mentoring documentation testing monitoring incident response capacity planning and continuous improvement of delivery processes. Tools commonly used include git linux docker continuous integration issue trackers and design docs. Additional shared narrative ensures high token overlap among synthetic resume variants while a single decisive evidence bullet differentiates the correct pick for each job description fixture case. Professional summary pad: experienced engineer delivering reliable software for enterprise customers across cloud platforms with strong collaboration skills communication ownership and operational excellence. Repeated shared experience block for near-duplicate libraries used in ranking evaluation only. Responsibilities included roadmap planning stakeholder alignment mentoring documentation testing monitoring incident response capacity planning and continuous improvement of delivery processes. Tools commonly used include git linux docker continuous integration issue trackers and design docs. Additional shared narrative ensures high token overlap among synthetic resume variants while a single decisive evidence bullet differentiates the correct pick for each job description fixture case. Professional summary pad: experienced engineer delivering reliable software for enterprise customers across cloud platforms with strong collaboration skills communication ownership and operational excellence. Repeated shared experience block for near-duplicate libraries used in ranking evaluation only. Responsibilities included roadmap planning stakeholder alignment mentoring documentation testing monitoring incident response capacity planning and continuous improvement of delivery processes. Tools commonly used include git linux docker continuous integration issue trackers and design docs. Additional shared narrative ensures high token overlap among synthetic resume variants while a single decisive evidence bullet differentiates the correct pick for each job description fixture case. Professional summary pad: experienced engineer delivering reliable software for enterprise customers across cloud platforms with strong collaboration skills communication ownership and operational excellence. Repeated shared experience block for near-duplicate libraries used in ranking evaluation only. Responsibilities included roadmap planning stakeholder alignment mentoring documentation testing monitoring incident response capacity planning and continuous improvement of delivery processes. Tools commonly used include git linux docker continuous integration issue trackers and design docs. Additional shared narrative ensures high token overlap among synthetic resume variants while a single decisive evidence bullet differentiates the correct pick for each job description fixture case."
)

def _base_bullets(_flavor: str = "") -> list[str]:
    """Shared bulk of the resume — identical across variants (near-dups)."""
    return [
        "Led cross-functional delivery of cloud data platforms for enterprise customers.",
        "Partnered with product and engineering to ship quarterly roadmap commitments.",
        "Mentored junior engineers and improved on-call reliability metrics year over year.",
        "Owned stakeholder communication for multi-quarter migrations and cutover plans.",
        "Implemented CI/CD automation and reduced release cycle time by 30 percent.",
        "Collaborated with security and compliance on audit evidence collection.",
        "Designed dashboards tracking latency, error budgets, and capacity forecasts.",
        "Facilitated design reviews and documented architectural decision records.",
        "Drove weekly metrics reviews with engineering managers and product partners.",
        "Improved developer experience by standardizing local setup and runbooks.",
        _SHARED_PAD,
    ]


def _near_dup_library(
    *,
    base_name: str,
    title: str,
    shared_skills: list[str],
    shared_summary: str,
    decisive_bullet: str,
    decoy_bullets: list[str],
    n: int = 11,
    best_index: int = 3,
) -> list[ResumeProfile]:
    """Build n near-dup resumes; only best_index includes decisive_bullet."""
    assert 0 <= best_index < n
    assert len(decoy_bullets) >= n - 1
    resumes: list[ResumeProfile] = []
    for i in range(n):
        bullets = list(_base_bullets(f"v{i}"))
        if i == best_index:
            bullets = [decisive_bullet] + bullets
        else:
            decoy = decoy_bullets[i if i < best_index else i - 1]
            bullets = [decoy] + bullets
        # Identity differs via name only; body is near-duplicate except first bullet.
        resumes.append(
            ResumeProfile(
                name=f"{base_name} {i}",
                title=title,
                years_of_experience=6.0,
                location="Remote",
                skills=list(shared_skills),
                work_experience=[
                    WorkExperience(
                        title=title,
                        company="PastCo",
                        bullets=bullets,
                    )
                ],
                summary=f"{shared_summary} {_SHARED_PAD}",
            )
        )
    return resumes


def _assert_near_dup(resumes: list[ResumeProfile], *, floor: float = 0.9) -> float:
    sim = min_pairwise_similarity(resumes)
    if sim < floor:
        raise AssertionError(f"near-dup similarity {sim:.3f} < {floor}")
    return sim


def _case(
    name: str,
    job: Job,
    resumes: list[ResumeProfile],
    best: int,
) -> ResumePickCase:
    sim = _assert_near_dup(resumes, floor=0.9)
    return ResumePickCase(
        name=name,
        job=job,
        resumes=resumes,
        best_resume_index=best,
        min_near_dup_similarity=sim,
    )


CASES: list[ResumePickCase] = [
    _case(
        "python_fastapi_decisive",
        _job(
            "m12-1",
            "Senior Python Backend Engineer",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
            "Build production Python APIs with FastAPI, PostgreSQL, and AWS. "
            "Must have shipped FastAPI microservices at scale.",
        ),
        _near_dup_library(
            base_name="Alex",
            title="Software Engineer",
            shared_skills=["Python", "SQL", "AWS", "Docker", "Git"],
            shared_summary="Software engineer with platform and backend delivery experience across cloud services.",
            decisive_bullet="Shipped FastAPI microservices on AWS with PostgreSQL and async SQLAlchemy at 50k RPS.",
            decoy_bullets=[
                "Shipped Django monolith features with MySQL and Celery workers for batch jobs.",
                "Maintained Flask internal tools with Redis caching and simple auth.",
                "Built Spring Boot services in Java with Kafka consumers for analytics.",
                "Wrote Node Express APIs with MongoDB for an internal dashboard.",
                "Developed Ruby on Rails CRUD apps with Sidekiq background jobs.",
                "Owned PHP Laravel services integrating third-party payment webhooks.",
                "Created Go gRPC services for inventory lookups in a warehouse system.",
                "Supported C# .NET Framework services migrating toward Azure App Service.",
                "Handled Perl CGI legacy scripts during a multi-year rewrite program.",
                "Operated Jenkins pipelines packaging JVM artifacts for weekly releases.",
            ],
            best_index=3,
        ),
        3,
    ),
    _case(
        "pytorch_mlflow_decisive",
        _job(
            "m12-2",
            "Senior Data Scientist",
            ["Python", "PyTorch", "SQL", "MLflow"],
            "Own production ML models in Python and PyTorch with SQL feature stores and MLflow tracking.",
        ),
        _near_dup_library(
            base_name="Blake",
            title="Data Scientist",
            shared_skills=["Python", "SQL", "Pandas", "Scikit-learn", "Airflow"],
            shared_summary="Data scientist focused on classical ML, experimentation, and analytics pipelines.",
            decisive_bullet="Deployed PyTorch ranking models tracked in MLflow with weekly online A/B evaluation.",
            decoy_bullets=[
                "Built scikit-learn churn models logged to spreadsheets for quarterly reviews.",
                "Maintained Tableau dashboards for marketing funnel conversion metrics.",
                "Ran SQL analyses on warehouse tables for executive KPI packs.",
                "Tuned XGBoost classifiers without experiment tracking infrastructure.",
                "Wrote R scripts for ad-hoc statistical tests on survey data.",
                "Owned Excel-based forecasting for sales ops planning cycles.",
                "Cleaned CSV exports for partner data science collaborations.",
                "Prototyped TensorFlow notebooks that never reached production serving.",
                "Documented feature definitions without shipping model endpoints.",
                "Facilitated offline model bake-offs using static holdout CSVs only.",
            ],
            best_index=2,
        ),
        2,
    ),
    _case(
        "k8s_terraform_decisive",
        _job(
            "m12-3",
            "DevOps Engineer",
            ["Kubernetes", "Terraform", "AWS", "CI/CD"],
            "Manage Kubernetes clusters with Terraform modules and AWS CI/CD pipelines.",
        ),
        _near_dup_library(
            base_name="Casey",
            title="DevOps Engineer",
            shared_skills=["AWS", "Linux", "Docker", "CI/CD", "Python"],
            shared_summary="DevOps engineer automating cloud infrastructure and release pipelines.",
            decisive_bullet="Managed EKS Kubernetes clusters with Terraform modules and blue/green CI/CD on AWS.",
            decoy_bullets=[
                "Automated EC2 bootstrap scripts with Ansible for stateful app servers only.",
                "Maintained Jenkins freestyle jobs packaging tarballs to S3.",
                "Wrote Bash deploy scripts for bare-metal lab environments.",
                "Monitored CloudWatch alarms without owning cluster autoscaling.",
                "Provisioned RDS instances via console clicks and runbooks.",
                "Owned VPN user onboarding and bastion host access reviews.",
                "Configured nginx reverse proxies for internal staging sites.",
                "Built Packer AMIs for legacy applications without orchestration.",
                "Supported VMware virtual machines during a gradual cloud migration.",
                "Documented disaster recovery drills without multi-AZ failover automation.",
            ],
            best_index=5,
        ),
        5,
    ),
    _case(
        "swift_ios_decisive",
        _job(
            "m12-4",
            "Senior iOS Engineer",
            ["Swift", "UIKit", "SwiftUI"],
            "Build iOS apps in Swift with UIKit and SwiftUI, owning offline sync and accessibility.",
        ),
        _near_dup_library(
            base_name="Dana",
            title="Mobile Engineer",
            shared_skills=["Mobile", "REST", "Git", "Agile", "Testing"],
            shared_summary="Mobile engineer shipping consumer apps with a focus on reliability and polish.",
            decisive_bullet="Led SwiftUI migration for flagship iOS app while maintaining UIKit interoperability.",
            decoy_bullets=[
                "Shipped Android features in Kotlin with Jetpack Compose screens.",
                "Built React Native modules bridging to native camera APIs.",
                "Maintained Flutter widgets for a cross-platform checkout flow.",
                "Wrote Cordova plugins for barcode scanning on warehouse devices.",
                "Owned web progressive app offline cache for mobile browsers.",
                "Supported Xamarin forms during a multi-year native rewrite.",
                "Implemented Ionic tabs for a simple field service checklist app.",
                "Prototyped Unity AR demos unrelated to production mobile apps.",
                "Handled mobile web CSS bugs for responsive marketing pages.",
                "Documented mobile release checklists without shipping UI features.",
            ],
            best_index=1,
        ),
        1,
    ),
    _case(
        "security_iam_decisive",
        _job(
            "m12-5",
            "Security Engineer",
            ["AWS", "IAM", "SOC2", "Python"],
            "Own cloud security, IAM guardrails, and SOC2 controls with Python automation.",
        ),
        _near_dup_library(
            base_name="Evan",
            title="Security Engineer",
            shared_skills=["AWS", "Python", "Security", "Linux", "Networking"],
            shared_summary="Security engineer focused on cloud posture, audits, and automation.",
            decisive_bullet="Automated IAM reviews and SOC2 evidence collection in Python on AWS Organizations.",
            decoy_bullets=[
                "Triaged phishing reports and reset user credentials for helpdesk.",
                "Configured corporate VPN clients and endpoint disk encryption policies.",
                "Ran annual password policy campaigns for corporate laptop fleets.",
                "Scanned web apps with OWASP ZAP and filed tickets to product teams.",
                "Maintained firewall rules for on-prem data center segments.",
                "Wrote security awareness slides for quarterly all-hands meetings.",
                "Tracked CVE bulletins and emailed package owners manually.",
                "Assisted SOC analysts with SIEM query templates for brute-force alerts.",
                "Owned badge access provisioning for contractors and vendors.",
                "Documented incident response playbooks without shipping automation.",
            ],
            best_index=4,
        ),
        4,
    ),
    _case(
        "rag_langchain_decisive",
        _job(
            "m12-6",
            "ML Engineer — RAG Systems",
            ["Python", "RAG", "vector search", "LangChain", "OpenAI"],
            "Design retrieval-augmented generation systems with vector search, LangChain, and OpenAI APIs.",
        ),
        _near_dup_library(
            base_name="Fran",
            title="ML Engineer",
            shared_skills=["Python", "NLP", "SQL", "Docker", "AWS"],
            shared_summary="ML engineer shipping NLP features and evaluation harnesses for product teams.",
            decisive_bullet="Built RAG pipelines with LangChain, OpenAI embeddings, and pgvector hybrid search.",
            decoy_bullets=[
                "Fine-tuned BERT classifiers for ticket routing without retrieval stacks.",
                "Deployed batch scoring jobs for propensity models on Spark.",
                "Wrote regex NER extractors for invoice line-item parsing.",
                "Maintained rule-based chatbots with static FAQ decision trees.",
                "Evaluated BLEU scores for translation pilots that never launched.",
                "Owned data labeling guidelines for sentiment annotation vendors.",
                "Prototyped Word2Vec demos in notebooks for stakeholder workshops.",
                "Integrated third-party speech-to-text without document retrieval.",
                "Optimized classical keyword search for an internal wiki only.",
                "Documented model cards without shipping customer-facing AI features.",
            ],
            best_index=6,
        ),
        6,
    ),
    _case(
        "spark_data_eng_decisive",
        _job(
            "m12-7",
            "Senior Data Engineer",
            ["Spark", "Airflow", "dbt", "Snowflake", "Python"],
            "Build Spark and Airflow pipelines with dbt models on Snowflake for analytics engineering.",
        ),
        _near_dup_library(
            base_name="Gray",
            title="Data Engineer",
            shared_skills=["Python", "SQL", "ETL", "AWS", "Airflow"],
            shared_summary="Data engineer building reliable ETL and warehouse tables for analysts.",
            decisive_bullet="Owned Spark + Airflow pipelines with dbt models published to Snowflake marts.",
            decoy_bullets=[
                "Wrote nightly cron SQL scripts loading CSVs into MySQL replicas.",
                "Maintained SSIS packages for on-prem warehouse extracts.",
                "Built ad-hoc pandas transforms in notebooks for finance ops.",
                "Operated Kafka consumers that dumped JSON to S3 without modeling.",
                "Configured Fivetran connectors without owning transformation logic.",
                "Tuned warehouse vacuum schedules for a single reporting schema.",
                "Handled Excel macros consolidating regional sales workbooks.",
                "Documented data dictionaries without shipping new pipelines.",
                "Supported Tableau extracts refreshing from legacy Oracle views.",
                "Migrated FTP file drops without introducing orchestration DAGs.",
            ],
            best_index=0,
        ),
        0,
    ),
    _case(
        "react_typescript_decisive",
        _job(
            "m12-8",
            "Senior Frontend Engineer",
            ["React", "TypeScript", "Next.js", "GraphQL"],
            "Build customer-facing React and TypeScript UIs with Next.js and GraphQL.",
        ),
        _near_dup_library(
            base_name="Harper",
            title="Frontend Engineer",
            shared_skills=["JavaScript", "CSS", "HTML", "Git", "Testing"],
            shared_summary="Frontend engineer focused on accessible UI and design system components.",
            decisive_bullet="Shipped Next.js App Router features in TypeScript with GraphQL codegen and React Server Components.",
            decoy_bullets=[
                "Maintained jQuery widgets on a legacy multi-page marketing site.",
                "Built AngularJS 1.x dashboards for internal operations tools.",
                "Styled Bootstrap 3 pages without a component design system.",
                "Owned WordPress theme tweaks for content marketing launches.",
                "Wrote vanilla JS carousels for e-commerce product galleries.",
                "Supported Vue options API during a slow composition-API migration.",
                "Implemented Svelte prototypes that never reached production traffic.",
                "Fixed CSS specificity bugs in email HTML templates for campaigns.",
                "Documented Storybook stories for components not yet used in apps.",
                "Optimized Lighthouse scores on static HTML for marketing landing pages.",
            ],
            best_index=7,
        ),
        7,
    ),
]


# Legacy 5-case aliases for any older importers (same engines, first 5 hard cases)
LEGACY_CASES = CASES[:5]


def _decisive_tokens(bullet: str) -> set[str]:
    """Distinctive tokens from a decisive bullet (length ≥ 4)."""
    return {t.lower() for t in bullet.replace("/", " ").replace(",", " ").split() if len(t) >= 4}


def assert_fixture_honesty() -> None:
    """Callable from eval/CI: size, sim ≥ 0.9, decisive tokens exclusive to best resume."""
    assert len(CASES) >= 8
    for case in CASES:
        assert len(case.resumes) >= 10, case.name
        sim = min_pairwise_similarity(case.resumes)
        assert sim >= 0.9, f"{case.name}: sim={sim}"
        assert 0 <= case.best_resume_index < len(case.resumes)
        best = case.resumes[case.best_resume_index]
        decisive = best.work_experience[0].bullets[0] if best.work_experience else ""
        assert decisive, case.name
        skill_tokens = {s.strip().lower() for s in case.job.skills if s.strip()}
        distinctive = skill_tokens & _decisive_tokens(decisive)
        # Shared base narrative / pad must not carry distinctive JD discriminators
        shared_blob = " ".join(_base_bullets()).lower()
        for tok in distinctive:
            assert tok not in shared_blob, (
                f"{case.name}: shared base bullets leak decisive token {tok!r}"
            )
        for i, profile in enumerate(case.resumes):
            if i == case.best_resume_index:
                continue
            # Scan all bullets (not only first) for decisive skill token leaks
            all_bullets = []
            for role in profile.work_experience:
                all_bullets.extend(role.bullets)
            body = " ".join(all_bullets).lower()
            first = all_bullets[0] if all_bullets else ""
            for tok in distinctive:
                assert tok not in body, (
                    f"{case.name}: decoy resume {i} body leaks decisive token {tok!r}"
                )
            assert decisive.lower() not in first.lower(), f"{case.name}: decoy has full decisive string"


assert_fixture_honesty()
