"""Setup — what is configured, what is missing, and what each key unlocks.

Keys are write-only over this API. A configured secret is reported as a boolean
and never echoed back, so the value cannot be recovered by anything that can
reach the endpoint. Writes are refused from anywhere but loopback: the rest of
the app is unauthenticated by design because it is local-only, and an endpoint
that rewrites credentials is where that assumption has to be enforced rather
than assumed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from hedge_fund.data.service import get_data_service
from hedge_fund.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

ENV_PATH = Path(__file__).resolve().parents[4] / ".env"

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@dataclass(frozen=True)
class KeySpec:
    """One configurable credential, and what it is worth."""

    env: str
    label: str
    provider: str | None
    unlocks: str
    signup: str
    free_tier: bool
    secret: bool = True
    required: bool = False


# Ordered by how much each one actually adds, so the highest-value gap is first.
KEY_SPECS: tuple[KeySpec, ...] = (
    KeySpec(
        env="FINNHUB_API_KEY",
        label="Finnhub",
        provider="finnhub",
        unlocks=(
            "Insider transactions, institutional holders, analyst ratings, earnings "
            "estimates, ESG scores, provider sentiment and congressional trades."
        ),
        signup="https://finnhub.io/register",
        free_tier=True,
    ),
    KeySpec(
        env="TWELVEDATA_API_KEY",
        label="Twelve Data",
        provider="twelvedata",
        unlocks="A second source for prices and technicals, used when the primary provider fails.",
        signup="https://twelvedata.com/pricing",
        free_tier=True,
    ),
    KeySpec(
        env="FINANCIAL_DATASETS_API_KEY",
        label="Financial Datasets",
        provider="financial_datasets",
        unlocks="Additional fundamentals coverage, mainly for names the default providers miss.",
        signup="https://financialdatasets.ai",
        free_tier=False,
    ),
    KeySpec(
        env="ALPHA_VANTAGE_API_KEY",
        label="Alpha Vantage",
        provider="alpha_vantage",
        unlocks="Real-time sector performance rankings.",
        signup="https://www.alphavantage.co/support/#api-key",
        free_tier=True,
    ),
    KeySpec(
        env="SEC_USER_AGENT",
        label="SEC user agent",
        provider="edgar",
        unlocks=(
            "Identifies you to SEC EDGAR. Not a secret — a contact string such as "
            "'Your Name your@email.com'. EDGAR works without it but may rate-limit."
        ),
        signup="https://www.sec.gov/os/webmaster-faq#developers",
        free_tier=True,
        secret=False,
    ),
    KeySpec(
        env="TCMB_EVDS_KEY",
        label="TCMB EVDS",
        provider=None,
        unlocks="Turkish central bank macro series. Only needed for BIST coverage.",
        signup="https://evds2.tcmb.gov.tr/index.php?/evds/login",
        free_tier=True,
    ),
    KeySpec(
        env="OPENAI_API_KEY",
        label="OpenAI",
        provider=None,
        unlocks=(
            "Optional cloud model instead of local Ollama. Not needed — and sends your "
            "research context off your machine, which the local default does not."
        ),
        signup="https://platform.openai.com/api-keys",
        free_tier=False,
    ),
)

_VALID_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
_KEYS_BY_ENV = {k.env: k for k in KEY_SPECS}


def _read_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for raw in ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _configured(env_values: dict[str, str], spec: KeySpec) -> bool:
    """A key counts as configured only if it has a non-placeholder value."""
    value = (env_values.get(spec.env) or "").strip()
    if not value:
        return False
    return value.lower() not in {"your_key_here", "changeme", "todo", "none", "null"}


@router.get("")
async def get_setup() -> dict[str, Any]:
    """Everything needed to finish setting the app up.

    Secret values are never included — only whether each one is present.
    """
    env_values = _read_env_file()
    statuses = {p["name"]: p for p in get_data_service().get_provider_status()}

    keys: list[dict[str, Any]] = []
    for spec in KEY_SPECS:
        provider = statuses.get(spec.provider or "", {})
        keys.append(
            {
                "env": spec.env,
                "label": spec.label,
                "unlocks": spec.unlocks,
                "signup": spec.signup,
                "free_tier": spec.free_tier,
                "secret": spec.secret,
                "configured": _configured(env_values, spec),
                "provider": spec.provider,
                "provider_available": provider.get("available"),
                "categories": provider.get("categories") or [],
            }
        )

    working = [p for p in statuses.values() if p.get("available")]
    return {
        "keys": keys,
        "providers": sorted(statuses.values(), key=lambda p: (not p.get("available"), p["name"])),
        "summary": {
            "providers_working": len(working),
            "providers_total": len(statuses),
            "keys_configured": sum(1 for k in keys if k["configured"]),
            "keys_total": len(keys),
            # Nothing here is required — that is the point of the local-first
            # default, and the UI should say so rather than nagging.
            "usable_without_keys": True,
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.ollama_model
            if settings.llm_provider == "ollama"
            else settings.llm_model,
            "base_url": settings.ollama_base_url,
            "num_ctx": settings.ollama_num_ctx,
            "temperature": settings.llm_temperature,
            "seed": settings.llm_seed,
            "thinking_disabled": settings.ollama_think is False,
        },
        "env_path": str(ENV_PATH),
    }


class KeyUpdate(BaseModel):
    """A key to write. An empty value removes it."""

    env: str = Field(max_length=64)
    value: str = Field(default="", max_length=512)


class KeyUpdateRequest(BaseModel):
    updates: list[KeyUpdate] = Field(default_factory=list, max_length=20)


def _require_loopback(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in _LOOPBACK:
        raise HTTPException(
            status_code=403,
            detail="Credentials can only be changed from this machine.",
        )


def _write_env(updates: dict[str, str]) -> None:
    """Merge updates into .env, preserving comments, order and unrelated keys."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    out: list[str] = []

    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(raw)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            seen.add(key)
            if updates[key]:
                out.append(f"{key}={updates[key]}")
            # An empty value drops the line entirely rather than leaving a
            # blank assignment, which some loaders read as an empty string.
        else:
            out.append(raw)

    added = [f"{k}={v}" for k, v in updates.items() if k not in seen and v]
    if added:
        if out and out[-1].strip():
            out.append("")
        out.append("# Added from the setup screen")
        out.extend(added)

    ENV_PATH.write_text("\n".join(out) + "\n")


@router.post("/keys")
async def update_keys(req: KeyUpdateRequest, request: Request) -> dict[str, Any]:
    """Write credentials to .env. Values are never read back out.

    A restart is required for providers to pick the change up, since keys are
    read once at import time.
    """
    _require_loopback(request)

    updates: dict[str, str] = {}
    for item in req.updates:
        env = item.env.strip().upper()
        if not _VALID_ENV_NAME.match(env):
            raise HTTPException(status_code=400, detail=f"invalid variable name: {item.env!r}")
        if env not in _KEYS_BY_ENV:
            raise HTTPException(status_code=400, detail=f"unknown setting: {env}")
        value = item.value.strip()
        if "\n" in value or "\r" in value:
            raise HTTPException(status_code=400, detail=f"{env} value must be a single line")
        updates[env] = value

    if not updates:
        raise HTTPException(status_code=400, detail="no updates supplied")

    try:
        _write_env(updates)
    except OSError as e:
        logger.exception("Failed writing %s", ENV_PATH)
        raise HTTPException(status_code=500, detail=f"could not write .env: {e}") from e

    return {
        "ok": True,
        "written": sorted(updates),
        "cleared": sorted(k for k, v in updates.items() if not v),
        "restart_required": True,
        "note": "Restart the API for providers to pick these up.",
    }
