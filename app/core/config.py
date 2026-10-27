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

    # File upload limits
    max_upload_size_mb: int = 5
    max_resume_pages: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()