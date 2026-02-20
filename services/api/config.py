from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str
    redis_url: str = "redis://redis:6379"
    host: str = "0.0.0.0"
    port: int = 8080

    model_config = {"env_file": ".env"}


settings = Settings()
