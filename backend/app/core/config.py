from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolve_env_files() -> tuple[str, ...]:
    candidates = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")
    found = tuple(str(path) for path in candidates if path.is_file())
    return found or (str(_REPO_ROOT / ".env"),)


class Settings(BaseSettings):
    DATABASE_URL: str = Field(default="sqlite:///./teamscout.db")
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    ALLOWED_ORIGINS: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    APP_VERSION: str | None = None
    GIT_SHA: str | None = None
    LLM_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY"),
    )
    LLM_API_BASE: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_BASE", "OPENAI_BASE_URL"),
    )
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDINGS_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDINGS_API_KEY", "OPENAI_API_KEY"),
    )
    EMBEDDINGS_API: str | None = None
    EMBEDDINGS_MODEL: str = "BAAI/bge-m3"
    JOBS_API_KEY: str | None = None
    JOBS_API_BASE: str | None = "https://jsearch.p.rapidapi.com"
    JOBS_API_HOST: str = "jsearch.p.rapidapi.com"
    JOBS_EXTRA_SOURCES_ENABLED: bool = True
    JOBS_SOURCE_ATS_ENABLED: bool = True
    JOBS_SOURCE_REMOTIVE_ENABLED: bool = True
    JOBS_SOURCE_REMOTEOK_ENABLED: bool = True
    ADZUNA_APP_ID: str | None = None
    ADZUNA_APP_KEY: str | None = None
    RANKING_DIRECT_ATS_BOOST: float = 0.0
    RANKING_WEIGHT_LLM: float = 0.38
    RANKING_WEIGHT_RRF: float = 0.20
    RANKING_WEIGHT_SKILLS: float = 0.12
    RANKING_WEIGHT_RECENCY: float = 0.08
    RANKING_WEIGHT_EXPERIENCE: float = 0.12
    RANKING_WEIGHT_REQUIREMENTS: float = 0.10
    RANKING_WEIGHT_CROSS_ENCODER: float = 0.0
    RRF_K: int = 60
    JOBS_FETCH_TARGET: int = 150
    JOBS_RECENCY_DAYS: int = 14
    RERANK_TOP_N: int = 30
    SEARCH_RESULTS_TOP_N: int = 10
    RECENCY_HALF_LIFE_DAYS: int = 7
    RANKING_USE_CROSS_ENCODER: bool = False
    CROSS_ENCODER_SHORTLIST: bool = False
    RERANKER_MODEL: str = "Qwen/Qwen3-Reranker-4B"
    CROSS_ENCODER_POOL: int = 50
    LLM_RERANK_TOP_N: int = 15
    RANKING_LLM_LISTWISE: bool = False
    RANKING_USE_CALIBRATION: bool = False
    SUMBLE_API_KEY: str | None = None
    SUMBLE_BASE_URL: str = "https://api.sumble.com"
    SUMBLE_SEARCH_LIMIT: int = 10
    SUMBLE_JOB_MATCH_LIMIT: int = 30
    GOOGLE_DRIVE_API_KEY: str | None = None
    GOOGLE_DRIVE_CLIENT_ID: str | None = None
    GOOGLE_DRIVE_CLIENT_SECRET: str | None = None
    GOOGLE_DRIVE_REFRESH_TOKEN: str | None = None
    RESUME_RECOMMEND_TOP_N: int = 3
    EVIDENCE_FLOOR: float = 0.55  # MaxSim floor; keep == ranking_math_align.DEFAULT_EVIDENCE_FLOOR
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MiB
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_UPLOAD: str = "20/minute"
    RATE_LIMIT_SEARCH: str = "30/minute"
    RATE_LIMIT_FIND_TEAM: str = "20/minute"
    RATE_LIMIT_REVEAL_EMAIL: str = "30/minute"
    RATE_LIMIT_LLM: str = "20/minute"
    HTTP_TIMEOUT_DEFAULT: float = 60.0
    HTTP_TIMEOUT_EMBEDDINGS_BATCH: float = 120.0
    HTTP_TIMEOUT_DRIVE_DOWNLOAD: float = 120.0
    OPS_TOKEN: str | None = None
    EVALS_DIR: str | None = None
    RATE_LIMIT_FEEDBACK: str = "60/hour"
    LLM_DAILY_COST_CEILING_USD: float = 5.0
    SUMBLE_DAILY_CREDIT_CEILING: int = 1000
    WORKSPACE_TTL_DAYS: int = 7
    WORKSPACE_DAILY_LLM_USD: float = 1.0
    WORKSPACE_DAILY_SUMBLE_CREDITS: int = 100
    # empty=auto (Lax in dev, None+Secure in prod for Vercel→Fly)
    WORKSPACE_COOKIE_SAMESITE: str | None = None
    LLM_MAX_TOKENS_PARSE_RESUME: int = 4096
    LLM_MAX_TOKENS_RERANK: int = 6000
    LLM_MAX_TOKENS_TEAM_EXTRACT: int = 2048
    LLM_MAX_TOKENS_JUSTIFY: int = 6000
    LLM_MAX_TOKENS_JD_DECOMPOSE: int = 3000
    LLM_MAX_TOKENS_PAIRWISE_JUDGE: int = 1200
    LLM_MAX_TOKENS_OUTREACH_DRAFT: int = 800
    LLM_MAX_TOKENS_DEFAULT: int = 4096
    LLM_PRICE_INPUT_PER_1M: float = 0.15
    LLM_PRICE_OUTPUT_PER_1M: float = 0.60
    EMBEDDINGS_PRICE_PER_1M: float = 0.02
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def max_tokens_for_operation(self, operation: str) -> int:
        mapping = {
            "parse_resume": self.LLM_MAX_TOKENS_PARSE_RESUME,
            "rerank": self.LLM_MAX_TOKENS_RERANK,
            "team_extract": self.LLM_MAX_TOKENS_TEAM_EXTRACT,
            "jd_metadata": self.LLM_MAX_TOKENS_TEAM_EXTRACT,
            "justify": self.LLM_MAX_TOKENS_JUSTIFY,
            "jd_decompose": self.LLM_MAX_TOKENS_JD_DECOMPOSE,
            "pairwise_judge": self.LLM_MAX_TOKENS_PAIRWISE_JUDGE,
            "outreach_draft": self.LLM_MAX_TOKENS_OUTREACH_DRAFT,
        }
        return mapping.get(operation, self.LLM_MAX_TOKENS_DEFAULT)

    @field_validator(
        "RATE_LIMIT_ENABLED",
        "JOBS_EXTRA_SOURCES_ENABLED",
        "JOBS_SOURCE_ATS_ENABLED",
        "JOBS_SOURCE_REMOTIVE_ENABLED",
        "JOBS_SOURCE_REMOTEOK_ENABLED",
        "RANKING_USE_CROSS_ENCODER",
        "CROSS_ENCODER_SHORTLIST",
        "RANKING_LLM_LISTWISE",
        "RANKING_USE_CALIBRATION",
        mode="before",
    )
    @classmethod
    def _parse_bool(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off", ""}:
                return False
        return value

    @property
    def is_prod(self) -> bool:
        return self.ENV.strip().lower() in {"prod", "production"}

    @property
    def app_version(self) -> str:
        for candidate in (self.APP_VERSION, self.GIT_SHA):
            if candidate and candidate.strip():
                return candidate.strip()
        return "dev"

    @property
    def allowed_origins_list(self) -> list[str]:
        raw = self.ALLOWED_ORIGINS if (self.ALLOWED_ORIGINS and self.ALLOWED_ORIGINS.strip()) else self.CORS_ORIGINS
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


settings = Settings()
