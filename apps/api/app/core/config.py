from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACTIONDESK_", extra="ignore")
    environment: Literal["local", "test"] = "local"
    database_url: str = (
        "postgresql+psycopg://actiondesk:local-development-only@localhost:5432/actiondesk"
    )
    redis_url: str = "redis://localhost:6379/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
