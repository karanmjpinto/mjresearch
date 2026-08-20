"""Provider registry with fallback chains, caching, and rate limiting."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from hedge_fund.data.cache import CachedValue, DataCategory, TTLCache
from hedge_fund.data.provenance import ProviderMeta, new_meta, record, verify
from hedge_fund.data.rate_limiter import RateLimiter
from hedge_fund.data.providers.base import BaseProvider, get_provider_classes

logger = logging.getLogger(__name__)


def _age_seconds(fetched_at: str, served_at: str) -> int | None:
    """Whole seconds between two ISO-8601 timestamps, or None if unparseable."""
    try:
        return max(
            0,
            int(
                (
                    datetime.fromisoformat(served_at) - datetime.fromisoformat(fetched_at)
                ).total_seconds()
            ),
        )
    except (ValueError, TypeError):
        return None


CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "providers.json"


class ProviderRegistry:
    """Manages providers, fallback chains, caching, and rate limiting.

    Usage:
        registry = ProviderRegistry()
        data = registry.get(DataCategory.ESG, "AAPL")
    """

    def __init__(self) -> None:
        self.cache = TTLCache()
        self.limiter = RateLimiter()
        self._providers: list[BaseProvider] = []
        self._chains: dict[DataCategory, list[BaseProvider]] = {}

        self._load_config()
        self._init_providers()
        self._build_chains()

    def _load_config(self) -> None:
        """Load provider config for rate limits."""
        self._config: dict = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                self._config = json.load(f).get("providers", {})

    def _init_providers(self) -> None:
        """Instantiate all registered provider classes."""
        # Import providers package to trigger registration
        import hedge_fund.data.providers  # noqa: F401

        for cls in get_provider_classes():
            try:
                provider = cls()
                self._providers.append(provider)

                # Configure rate limiting from config; allow config to override priority
                cfg = self._config.get(provider.name, {})
                rpm = cfg.get("rate_limit_per_minute", 0)
                if rpm > 0:
                    self.limiter.configure(provider.name, rpm)
                if "priority" in cfg:
                    provider.priority = cfg["priority"]

                logger.info(
                    "Provider %s: available=%s, categories=%s",
                    provider.name,
                    provider.available(),
                    [c.value for c in provider.categories],
                )
            except Exception as e:
                logger.warning("Failed to init provider %s: %s", cls.name, e)

    def _build_chains(self) -> None:
        """Build fallback chains: for each category, sort available providers by priority."""
        for cat in DataCategory:
            providers = [p for p in self._providers if cat in p.categories and p.available()]
            providers.sort(key=lambda p: p.priority)
            self._chains[cat] = providers
            if providers:
                logger.debug(
                    "Chain for %s: %s",
                    cat.value,
                    [p.name for p in providers],
                )

    @staticmethod
    def _cache_key(key: str, kwargs: dict[str, Any]) -> str:
        """Cache key covering every argument that changes the result.

        Omitting ``days``/``limit``/``interval`` here makes a 365-day fetch
        satisfy a later 30-day request from cache, so the window a caller asked
        for and the window it receives silently diverge.
        """
        if not kwargs:
            return key
        parts = [f"{k}={kwargs[k]}" for k in sorted(kwargs) if kwargs[k] is not None]
        return key if not parts else f"{key}|" + "|".join(parts)

    def get(self, category: DataCategory, key: str, **kwargs: Any) -> Any:
        """Fetch data with caching and fallback.

        Tries providers in priority order. Returns first successful result.
        Returns None if all providers fail.
        """
        value, _meta = self.get_with_meta(category, key, **kwargs)
        return value

    def get_with_meta(
        self, category: DataCategory, key: str, **kwargs: Any
    ) -> tuple[Any, ProviderMeta]:
        """Like :meth:`get`, but also returns (and records) the provenance.

        The metadata is appended to whatever :func:`hedge_fund.data.provenance.capture`
        block is active, so callers that want provenance for a whole snapshot do
        not have to thread it through every call site.
        """
        cache_key = self._cache_key(key, kwargs)

        cached = self.cache.get(category, cache_key)
        if cached is not None:
            if isinstance(cached, CachedValue):
                meta = new_meta(
                    category, key, provider=cached.provider, from_cache=True, params=kwargs
                )
                meta.checks = dict(cached.checks)
                if cached.fetched_at:
                    meta.served_at = meta.fetched_at
                    meta.fetched_at = cached.fetched_at
                    meta.age_seconds = _age_seconds(cached.fetched_at, meta.served_at)
                record(meta)
                return cached.value, meta
            # Pre-envelope entry (or a cache populated by other code) — source unknown.
            meta = new_meta(category, key, provider=None, from_cache=True, params=kwargs)
            record(meta)
            return cached, meta

        chain = self._chains.get(category, [])
        if not chain:
            logger.warning("No providers available for category %s", category.value)
            meta = new_meta(category, key, provider=None, from_cache=False, params=kwargs)
            meta.error = "no providers available for this category"
            record(meta)
            return None, meta

        attempted: list[str] = []
        last_error: str | None = None

        for provider in chain:
            # Rate limit check
            if not self.limiter.acquire(provider.name):
                logger.debug("Rate limited: %s", provider.name)
                attempted.append(f"{provider.name}:rate_limited")
                continue

            try:
                result = provider.fetch(category, key, **kwargs)
                if result is None:
                    attempted.append(f"{provider.name}:no_data")
                    continue

                meta = new_meta(
                    category, key, provider=provider.name, from_cache=False, params=kwargs
                )
                meta.attempted = attempted
                try:
                    meta.checks = verify(category, result, **kwargs).as_dict()
                except Exception as e:  # verification must never break a fetch
                    logger.debug("Verification failed for %s/%s: %s", category.value, key, e)
                    meta.checks = {"warnings": [f"verification raised: {e}"]}

                self.cache.set(
                    category,
                    cache_key,
                    CachedValue(
                        value=result,
                        provider=provider.name,
                        fetched_at=meta.fetched_at,
                        checks=meta.checks,
                    ),
                )
                record(meta)
                return result, meta
            except Exception as e:
                logger.warning(
                    "Provider %s failed for %s/%s: %s",
                    provider.name,
                    category.value,
                    key,
                    e,
                )
                attempted.append(f"{provider.name}:error")
                last_error = f"{provider.name}: {e}"
                continue

        meta = new_meta(category, key, provider=None, from_cache=False, params=kwargs)
        meta.attempted = attempted
        meta.error = last_error or "all providers returned no data"
        record(meta)
        return None, meta

    def get_provider_status(self) -> list[dict]:
        """Return status of all providers."""
        statuses = []
        for provider in self._providers:
            info = provider.status()
            info["rate_limit"] = self.limiter.status().get(provider.name)
            statuses.append(info)
        return statuses

    def get_chain(self, category: DataCategory) -> list[str]:
        """Return provider names in the fallback chain for a category."""
        return [p.name for p in self._chains.get(category, [])]

    def rebuild_chains(self) -> None:
        """Rebuild fallback chains (call after config changes)."""
        self._build_chains()
