from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str = "redis://redis:6379/0"
    # Used by async click-event publisher in api/messaging.py
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    base_url: str = "http://localhost:8000"
    app_env: str = "development"
    rate_limit_per_minute: int = 60
    cache_ttl_seconds: int = 300


settings = Settings()