"""Provider interface."""

from __future__ import annotations

from typing import List, Optional

from ..config import Config
from ..models import Offer


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request."""


class FlightProvider:
    """Base class. Subclasses implement :meth:`search`."""

    name = "base"

    # Whether requests leave the machine. The inter-request pause exists to
    # keep a remote service from throttling us; a provider that talks to
    # nobody has nothing to be polite to, and pausing anyway turns an offline
    # smoke test into a 39-minute one (26 routes x 30 dates x 3s).
    offline = False

    def __init__(self, config: Config):
        self.config = config

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
    ) -> List[Offer]:
        """Return priced offers for one route/date, cheapest first.

        Implementations should never raise for an "empty" result; return an
        empty list instead. Raise :class:`ProviderError` only for genuine
        failures (auth, network, malformed response).
        """
        raise NotImplementedError
