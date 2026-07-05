from pathlib import Path

from pydantic import Field
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
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

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

    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()