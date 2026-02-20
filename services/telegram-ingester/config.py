from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str
    redis_url: str = "redis://redis:6379"
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_path: str = "/app/sessions/osint_monitor"

    model_config = {"env_file": ".env"}


settings = Settings()
