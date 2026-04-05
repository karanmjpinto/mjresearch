"""Provider registry with fallback chains, caching, and rate limiting."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from hedge_fund.data.cache import DataCategory, TTLCache
from hedge_fund.data.rate_limiter import RateLimiter
from hedge_fund.data.providers.base import BaseProvider, get_provider_classes

logger = logging.getLogger(__name__)

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

                # Configure rate limiting from config
                cfg = self._config.get(provider.name, {})
                rpm = cfg.get("rate_limit_per_minute", 0)
                if rpm > 0:
                    self.limiter.configure(provider.name, rpm)

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
            providers = [
                p for p in self._providers if cat in p.categories and p.available()
            ]
            providers.sort(key=lambda p: p.priority)
            self._chains[cat] = providers
            if providers:
                logger.debug(
                    "Chain for %s: %s",
                    cat.value,
                    [p.name for p in providers],
                )

    def get(self, category: DataCategory, key: str, **kwargs: Any) -> Any:
        """Fetch data with caching and fallback.

        Tries providers in priority order. Returns first successful result.
        Returns None if all providers fail.
        """
        cache_key = key
        if kwargs.get("end_date") is not None:
            cache_key = f"{key}|end={kwargs['end_date']}|days={kwargs.get('days', 365)}"

        # Check cache first
        cached = self.cache.get(category, cache_key)
        if cached is not None:
            return cached

        chain = self._chains.get(category, [])
        if not chain:
            logger.warning("No providers available for category %s", category.value)
            return None

        for provider in chain:
            # Rate limit check
            if not self.limiter.acquire(provider.name):
                logger.debug("Rate limited: %s", provider.name)
                continue

            try:
                result = provider.fetch(category, key, **kwargs)
                if result is not None:
                    self.cache.set(category, cache_key, result)
                    return result
            except Exception as e:
                logger.warning(
                    "Provider %s failed for %s/%s: %s",
                    provider.name,
                    category.value,
                    key,
                    e,
                )
                continue

        return None

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
