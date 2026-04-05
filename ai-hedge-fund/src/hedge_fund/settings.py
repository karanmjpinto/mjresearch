"""Application settings — env-driven (see `.env.example`)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = f"sqlite:///{_PROJECT_ROOT / 'data' / 'fund.db'}"

    # LLM: default is local Ollama (free, open weights). Optional: OpenAI via `uv sync --extra openai`.
    llm_provider: Literal["ollama", "openai"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_s: float = 600.0

    openai_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"  # used when llm_provider=openai
    llm_max_output_tokens: int = 2500
    research_max_context_chars: int = 24_000

    # FinBERT news sentiment (optional: `uv sync --extra sentiment`)
    news_sentiment_enabled: bool = True
    finbert_model_id: str = "ProsusAI/finbert"

    # Sentry (optional — set SENTRY_DSN in production)
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1


settings = Settings()
