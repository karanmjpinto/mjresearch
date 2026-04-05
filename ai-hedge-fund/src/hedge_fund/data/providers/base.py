"""Abstract base class for data providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from hedge_fund.data.cache import DataCategory

logger = logging.getLogger(__name__)

# Global registry of provider classes (populated by __init_subclass__)
_PROVIDER_CLASSES: list[type[BaseProvider]] = []


class BaseProvider(ABC):
    """Abstract base for all data providers.

    Subclasses must define:
        name: str           — unique provider name
        priority: int       — lower = tried first (1=primary, 4=last resort)
        categories: set     — which DataCategory values this provider supports

    And implement:
        available() -> bool — whether this provider can be used (keys present, etc.)
        fetch(category, ticker, **kwargs) -> Any — fetch data for a category
    """

    name: str = "base"
    priority: int = 99
    categories: set[DataCategory] = set()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.name != "base":
            _PROVIDER_CLASSES.append(cls)
            logger.debug("Registered provider class: %s", cls.name)

    @abstractmethod
    def available(self) -> bool:
        """Return True if this provider is ready (API keys set, package installed)."""
        ...

    @abstractmethod
    def fetch(self, category: DataCategory, ticker: str, **kwargs: Any) -> Any:
        """Fetch data for the given category and ticker."""
        ...

    def status(self) -> dict:
        """Return provider status info."""
        return {
            "name": self.name,
            "available": self.available(),
            "categories": [c.value for c in self.categories],
            "priority": self.priority,
        }


def get_provider_classes() -> list[type[BaseProvider]]:
    """Return all registered provider classes."""
    return list(_PROVIDER_CLASSES)
