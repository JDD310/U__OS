from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str
    redis_url: str = "redis://redis:6379"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_rate_limit: float = 1.0  # requests per second
    spacy_model: str = "en_core_web_sm"
    classification_threshold: float = 0.8
    batch_size: int = 50
    backlog_poll_interval: int = 30  # seconds between backlog sweeps

    model_config = {"env_file": ".env"}


settings = Settings()
