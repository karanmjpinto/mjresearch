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

    # --- who is allowed to spend money on this deployment ------------------
    #
    # Only four routes invoke a model (see api/guards.py). Locally they are
    # free, because the default provider is Ollama on this machine. Hosted with
    # `llm_provider=openai` they bill a real account, and a public deployment
    # with all three of these left at their defaults is an anonymous LLM proxy
    # paid for by whoever deployed it.
    #
    # Defaults are deliberately the permissive ones so a local checkout is
    # unchanged; it is the hosted environment that has to say otherwise.

    #: Set False on a public deployment that should not run models at all —
    #: the honest setting when the site already tells visitors the analysis
    #: runs on their own machine. Checked before the key, so it cannot be
    #: bypassed with one.
    llm_endpoints_enabled: bool = True
    #: Shared secret required on the model routes when set. Compared in
    #: constant time.
    llm_access_key: str | None = None
    #: Model runs allowed per client per hour. 0 disables the limit. Bounds the
    #: damage from a leaked key, which a key alone does nothing about.
    llm_rate_limit_per_hour: int = 0

    openai_api_key: str | None = None
    # Any OpenAI-compatible endpoint: OpenRouter, Together, a self-hosted vLLM.
    # Left unset the SDK talks to api.openai.com. Set it and the same client
    # drives the gateway instead — the wire format is identical, so the only
    # things that change are the key, the base URL, and the model id, which
    # becomes the gateway's namespaced form (e.g. "anthropic/claude-sonnet-4.5"
    # on OpenRouter rather than a bare "gpt-4o-mini").
    openai_base_url: str | None = None
    # Attribution headers OpenRouter reads for its public model rankings. Purely
    # optional, ignored by every other endpoint, and only sent when a base URL is
    # set — an unset gateway is OpenAI itself, which has no use for them.
    openrouter_site_url: str | None = None
    openrouter_site_name: str | None = None
    llm_model: str = "gpt-4o-mini"  # used when llm_provider=openai
    llm_max_output_tokens: int = 2500
    research_max_context_chars: int = 24_000

    #: Put the shared market bundle in front of the per-persona instruction.
    #:
    #: Off by default, and the reason is a measurement that contradicted the
    #: one that motivated building it.
    #:
    #: The promise: a prefix cache can only reuse a prefix, and with the
    #: investor's style in the system message the text that differs sat in
    #: front of ~11k identical tokens. Measured in isolation on an M4 Max,
    #: reordering turned a second 22-second prefill into 0.17 s — a 130x
    #: saving on that component.
    #:
    #: What it was actually worth end to end: **1.28x** (93.3 s -> 73.1 s on a
    #: seven-member committee). The microbenchmark measured prefill alone; a
    #: real run is dominated by generation, which does not cache, and includes
    #: a rebuttal round whose prompts differ anyway.
    #:
    #: What it cost: the verdicts moved materially. On the same KSS snapshot
    #: Burry went SELL 15 -> BUY 75, Buffett BUY 100 -> HOLD 50, and the
    #: conviction spread narrowed from 85 to 55. Moving an instruction to the
    #: end of an 11k-token prompt changes how well it is followed, and for a
    #: tool whose whole claim is "read the spread, not the average", twenty
    #: seconds is not worth a bear that turns bullish.
    #:
    #: Settled with the golden set (`scripts/run_eval.py`), and the answer is
    #: no. Scored over 20 cases on the shipped path, the reorder moved **11 of
    #: 20 verdicts** — Buffett on KSS BUY 100 -> HOLD 50, reproducing the
    #: observation above; Burry on LULU SELL 15 -> BUY 75; Buffett on LULU BUY
    #: 100 -> SELL 35 — and pulled eight separate cases onto the identical
    #: answer, "BUY 75". Concentration on one verdict rose 25% -> 40%.
    #:
    #: The trap worth recording: the reorder **scored better**, 20/20 against
    #: the baseline's 19/20, because every per-case grader sees a well-formed
    #: answer and none of them can see homogenisation across cases. That is
    #: what `MAX_VERDICT_SHARE` in the runner now exists to catch. A score is
    #: not the goal; the spread is the product.
    #:
    #: Leave it off. Turn it on only for a bulk re-scoring job where nothing
    #: downstream reads the disagreement.
    llm_shared_prefix: bool = False

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

    # Per-stage model selection. A persona analysis and the synthesis that
    # reconciles four of them are different jobs: the first is bulk reading of a
    # bundle, the second is the one call whose output a person actually acts on.
    # Left unset, both use the active provider's model and behaviour is exactly
    # as before. Set, they name a model for the active provider (an Ollama tag
    # under LLM_PROVIDER=ollama, an OpenAI model id under openai).
    llm_persona_model: str | None = None
    llm_synthesis_model: str | None = None
    # The autoresearch proposer picks a strategy and parameters from a fixed
    # catalog; the harness, not the model, decides whether the idea was any
    # good. A cheaper model there buys more experiments per hour, and the
    # trials-adjusted hurdle is what protects the result either way.
    llm_proposer_model: str | None = None

    # When the committee splits materially, put the analysts back in the room
    # once before synthesizing. Costs a second round of calls on contested
    # tickers only; see agents.research_agent.run_committee_analysis.
    committee_refine_on_dissent: bool = True

    # Persist every research run (snapshot, prompts, params, output) for replay.
    research_run_persistence: bool = True
    research_run_retention: int = 2000

    # FinBERT news sentiment (optional: `uv sync --extra sentiment`)
    news_sentiment_enabled: bool = True
    finbert_model_id: str = "ProsusAI/finbert"

    # Your own notes (stage 04). Left unset the stage reports that no vault is
    # connected and the rest of the flow is unaffected. Never given a default:
    # this repository is public, and a personal directory path is not something
    # to publish for the convenience of one.
    vault_path: str | None = None

    # Sentry (optional — set SENTRY_DSN in production)
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1


settings = Settings()
