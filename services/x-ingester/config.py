from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str
    redis_url: str = "redis://redis:6379"
    x_poll_interval: int = 300
    x_accounts_db_path: str = "/app/accounts/accounts.db"

    model_config = {"env_file": ".env"}


settings = Settings()
