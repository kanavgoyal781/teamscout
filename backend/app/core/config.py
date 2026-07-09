from pathlib import Path

from pydantic import Field, field_validator
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
    # Preferred alias; CORS_ORIGINS kept for backward compatibility.
    ALLOWED_ORIGINS: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Baked at image build time (docker ARG/ENV); fallback for local dev.
    APP_VERSION: str | None = None
    GIT_SHA: str | None = None

    LLM_API_KEY: str | None = None
    LLM_API_BASE: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"

    EMBEDDINGS_API_KEY: str | None = None
    EMBEDDINGS_API: str | None = None
    EMBEDDINGS_MODEL: str = "BAAI/bge-m3"

    JOBS_API_KEY: str | None = None
    JOBS_API_BASE: str | None = "https://jsearch.p.rapidapi.com"
    JOBS_API_HOST: str = "jsearch.p.rapidapi.com"

    RANKING_WEIGHT_LLM: float = 0.5
    RANKING_WEIGHT_RRF: float = 0.3
    RANKING_WEIGHT_SKILLS: float = 0.1
    RANKING_WEIGHT_RECENCY: float = 0.1
    RRF_K: int = 60
    JOBS_FETCH_TARGET: int = 150
    JOBS_RECENCY_DAYS: int = 14
    RERANK_TOP_N: int = 30
    SEARCH_RESULTS_TOP_N: int = 10
    RECENCY_HALF_LIFE_DAYS: int = 7

    SUMBLE_API_KEY: str | None = None
    SUMBLE_BASE_URL: str = "https://api.sumble.com"
    SUMBLE_SEARCH_LIMIT: int = 10
    SUMBLE_JOB_MATCH_LIMIT: int = 30

    GOOGLE_DRIVE_API_KEY: str | None = None
    GOOGLE_DRIVE_CLIENT_ID: str | None = None
    GOOGLE_DRIVE_CLIENT_SECRET: str | None = None
    GOOGLE_DRIVE_REFRESH_TOKEN: str | None = None
    RESUME_RECOMMEND_TOP_N: int = 3

    # API hardening
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MiB
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_UPLOAD: str = "20/minute"
    RATE_LIMIT_SEARCH: str = "30/minute"
    RATE_LIMIT_FIND_TEAM: str = "20/minute"
    RATE_LIMIT_REVEAL_EMAIL: str = "30/minute"
    RATE_LIMIT_LLM: str = "20/minute"

    # Outbound HTTP timeouts (seconds)
    HTTP_TIMEOUT_DEFAULT: float = 60.0
    HTTP_TIMEOUT_EMBEDDINGS_BATCH: float = 120.0
    HTTP_TIMEOUT_DRIVE_DOWNLOAD: float = 120.0

    # Ops dashboard (required for /ops; missing token denies all access)
    OPS_TOKEN: str | None = None

    # Cost guardrails
    LLM_DAILY_COST_CEILING_USD: float = 5.0
    SUMBLE_DAILY_CREDIT_CEILING: int = 1000

    # Per-operation max_tokens budgets
    LLM_MAX_TOKENS_PARSE_RESUME: int = 4096
    LLM_MAX_TOKENS_RERANK: int = 6000
    LLM_MAX_TOKENS_TEAM_EXTRACT: int = 2048
    LLM_MAX_TOKENS_JUSTIFY: int = 6000
    LLM_MAX_TOKENS_DEFAULT: int = 4096

    # Model prices USD per 1M tokens (input/output). Embeddings use input only.
    LLM_PRICE_INPUT_PER_1M: float = 0.15
    LLM_PRICE_OUTPUT_PER_1M: float = 0.60
    EMBEDDINGS_PRICE_PER_1M: float = 0.02

    # Optional OTLP/HTTP JSON traces endpoint (unset = SQLite only)
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
            "justify": self.LLM_MAX_TOKENS_JUSTIFY,
        }
        return mapping.get(operation, self.LLM_MAX_TOKENS_DEFAULT)

    @field_validator("RATE_LIMIT_ENABLED", mode="before")
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
