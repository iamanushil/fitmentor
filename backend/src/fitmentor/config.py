from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None

    # LLM
    portkey_api_key: str | None = None
    portkey_virtual_key_openai: str | None = None
    openai_model: str = "gpt-4o-mini"

    # AWS
    aws_region: str = "ap-south-1"
    sqs_workout_plan_queue_url: str | None = None
    s3_bucket: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
