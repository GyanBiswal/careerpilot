from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or .env."""

    app_name: str = "CareerPilot"
    app_env: str = "development"
    app_version: str = "0.1.0"

    # Required: no defaults, so missing values fail loudly at startup.
    database_url: str
    secret_key: str

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Only used by pytest; must point at a different database.
    test_database_url: str | None = None

    # Document (resume / job description) upload limits
    max_upload_size_mb: int = 5
    max_document_pages: int = 20

    # LLM (Groq). The key is optional so the app still starts without it;
    # AI endpoints return 503 until it is configured.
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    llm_timeout_seconds: int = 60

    # Question banks: relative paths are resolved from the project root.
    question_bank_dir: str = "data/question_banks"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()