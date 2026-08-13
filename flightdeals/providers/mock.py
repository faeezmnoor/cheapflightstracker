"""Deterministic mock provider.

Generates realistic-looking fares without any API key so the whole pipeline
(search -> baseline -> deal detection -> email) can be exercised in tests,
CI dry-runs, and local demos. Prices are a stable function of the route and
date, with a couple of routes deliberately discounted so a demo run surfaces
a "deal".
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from ..config import Config
from ..models import Offer
from .base import FlightProvider
from .util import google_flights_link


# Rough "typical" one-way MYR fares from KL, used as the mock's center point.
_BASE_FARES = {
    "CGK": 320, "DPS": 430, "SUB": 360, "KNO": 210, "JOG": 380,
    "BDO": 300, "UPG": 560, "LOP": 520, "SRG": 400, "PDG": 260,
    "PKU": 190, "BPN": 610, "BTH": 150, "PLM": 340, "PNK": 330,
}
# Routes/dates the mock will occasionally slash, so demos show underpricing.
_DISCOUNT_ROUTES = {"DPS", "KNO"}


def _jitter(*parts: str) -> float:
    """Stable pseudo-random value in [0, 1) derived from the inputs."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class MockProvider(FlightProvider):
    offline = True
    name = "mock"

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
    ) -> List[Offer]:
        base = _BASE_FARES.get(destination, 350)
        trip_type = "round_trip" if return_date else "one_way"
        link = google_flights_link(origin, destination, departure_date, return_date)

        offers: List[Offer] = []
        for i in range(self.config.max_offers_per_search):
            noise = 0.75 + 0.6 * _jitter(destination, departure_date, str(i))
            price = base * noise
            if return_date:
                price += base * (0.85 + 0.5 * _jitter(destination, return_date, str(i)))

            # Deliberately deep discount on select route/date combos.
            if destination in _DISCOUNT_ROUTES and _jitter(destination, departure_date) < 0.5:
                price *= 0.55

            offers.append(Offer(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                price=round(price, 2),
                currency=self.config.currency,
                trip_type=trip_type,
                airline="XX",
                stops=0 if _jitter(destination, str(i)) > 0.4 else 1,
                deep_link=link,
            ))
        offers.sort(key=lambda o: o.price)
        return offers
