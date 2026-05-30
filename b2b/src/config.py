from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModerationServiceConfig(BaseModel):
    url: str = "http://moderation:8000"
    service_key: str = "dev-b2b-to-mod-key"


class ApplicationSettings(BaseSettings):
    moderation: ModerationServiceConfig = ModerationServiceConfig()
    model_config = SettingsConfigDict(env_nested_delimiter="__")


@lru_cache
def get_settings() -> ApplicationSettings:
    return ApplicationSettings()
