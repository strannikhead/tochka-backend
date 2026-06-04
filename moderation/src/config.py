"""Application settings for Moderation service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    database_url: str = (
        "postgresql+psycopg://neomarket:neomarket_dev_2026@localhost:5432/neomarket_moderation"
    )
    b2b_to_mod_service_key: str = "dev-b2b-to-mod-key"
    review_timeout_minutes: int = 30

    model_config = SettingsConfigDict(env_nested_delimiter="__")


@lru_cache
def get_settings() -> ApplicationSettings:
    return ApplicationSettings()
