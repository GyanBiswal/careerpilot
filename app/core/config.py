from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or .env."""

    app_name: str = "CareerPilot"
    app_env: str = "development"
    app_version: str = "0.1.0"

    # Required: no default, so a missing value fails loudly at startup.
    database_url: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()