"""Flight-data providers.

A provider turns a search request (route + dates) into a list of priced
``Offer`` objects. Swap providers by setting the ``PROVIDER`` env var.
"""

from __future__ import annotations

from ..config import Config
from .base import FlightProvider, ProviderError


def get_provider(config: Config) -> FlightProvider:
    name = (config.provider or "googleflights").strip().lower()
    if name in ("googleflights", "google", "google-flights"):
        from .googleflights import GoogleFlightsProvider
        return GoogleFlightsProvider(config)
    if name == "mock":
        from .mock import MockProvider
        return MockProvider(config)
    raise ProviderError(f"Unknown provider: {config.provider!r}")


__all__ = ["FlightProvider", "ProviderError", "get_provider"]
