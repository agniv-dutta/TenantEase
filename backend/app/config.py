"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings. Env vars override defaults."""

    database_url: str = f"sqlite:///{BACKEND_ROOT / 'data' / 'khata.db'}"
    seed: int = 42
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Risk tiers
    tier_low_max: float = 0.20
    tier_medium_max: float = 0.50

    # Model features
    use_occupation: bool = True

    # LLM
    llm_provider: str = "none"  # anthropic | openai | ollama | none
    llm_model: str = "claude-3-5-haiku-latest"

    # Admin
    enable_admin_reseed: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
