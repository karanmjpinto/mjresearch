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
    ollama_model: str = "qwen3:30b"
    ollama_timeout_s: float = 600.0

    openai_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"  # used when llm_provider=openai
    llm_max_output_tokens: int = 2500
    research_max_context_chars: int = 24_000

    # Determinism. Sampling is greedy and seeded by default: without reproducible
    # runs there is nothing to diff, so no evals, no regression tests on research
    # quality, and no way to tell a real change of view from sampling noise.
    # Raise llm_temperature only for deliberately exploratory work.
    llm_temperature: float = 0.0
    llm_seed: int = 7
    llm_top_p: float = 1.0

    # Hybrid reasoning models (Qwen3, DeepSeek-R1) emit a thinking trace before
    # answering. For structured JSON research output that trace is pure cost: it
    # consumes the token budget and adds nondeterminism without improving the
    # schema-constrained result. Set to None to leave the model's default alone.
    ollama_think: bool | None = False

    # Context window. Ollama otherwise uses the model's maximum, and for a
    # long-context model that is ruinous: qwen3:30b defaults to 262144 tokens and
    # allocates ~44GB of KV cache, which swaps even a 48GB machine into
    # uselessness. Our largest prompt is research_max_context_chars (~7k tokens)
    # plus the metric catalog and the output budget, so 16k is ample headroom.
    ollama_num_ctx: int = 16384

    # Greedy decoding (temperature 0) is unusually prone to degenerate
    # repetition. Ollama's own default is 1.1; it is set explicitly here so the
    # value is recorded on every run rather than inherited silently.
    ollama_repeat_penalty: float = 1.1

    # Persist every research run (snapshot, prompts, params, output) for replay.
    research_run_persistence: bool = True
    research_run_retention: int = 2000

    # FinBERT news sentiment (optional: `uv sync --extra sentiment`)
    news_sentiment_enabled: bool = True
    finbert_model_id: str = "ProsusAI/finbert"

    # Sentry (optional — set SENTRY_DSN in production)
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1


settings = Settings()
