"""Google Flights provider, backed by the ``fast-flights`` library.

``fast-flights`` reads Google Flights' internal endpoint directly (base64
protobuf query -> the ``ds:1`` hydration script in the page), so it returns
real fares with **no API key**. Trade-off: it's an unofficial scraper, so it
can break if Google changes their page format, and heavy use risks being rate
-limited. We keep request volume modest and fail soft (an empty/failed search
never kills the run — it's recorded as an error and the other routes proceed).

Pinned to fast-flights==3.0.2 (see requirements.txt); the API used here:
    create_query(flights=[FlightQuery(...)], trip=, seat=, passengers=,
                 currency=) -> Query
    get_flights(query, *, proxy=None) -> ResultList[Flights]
    Flights: .type .price(int, in currency) .airlines(list[str])
             .flights(list[SingleFlight]) .carbon
"""

from __future__ import annotations

import time
from typing import List, Optional

from ..config import Config
from ..models import Offer
from .base import FlightProvider, ProviderError
from .util import google_flights_link


class GoogleFlightsProvider(FlightProvider):
    name = "googleflights"

    def __init__(self, config: Config):
        super().__init__(config)
        try:
            # Imported lazily so the rest of the app (and the mock provider)
            # works even when fast-flights isn't installed.
            from fast_flights import (FlightQuery, Passengers,  # noqa: F401
                                      create_query, get_flights)
            from fast_flights.exceptions import FlightsNotFound
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ProviderError(
                "The 'fast-flights' package is required for the googleflights "
                "provider. Install it with: pip install fast-flights "
                "typing_extensions. Or set PROVIDER=mock to run without it."
            ) from exc
        self._create_query = create_query
        self._get_flights = get_flights
        self._FlightQuery = FlightQuery
        self._Passengers = Passengers
        self._FlightsNotFound = FlightsNotFound

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
    ) -> List[Offer]:
        legs = [self._FlightQuery(date=departure_date, from_airport=origin,
                                  to_airport=destination)]
        trip = "one-way"
        if return_date:
            legs.append(self._FlightQuery(date=return_date, from_airport=destination,
                                          to_airport=origin))
            trip = "round-trip"

        query = self._create_query(
            flights=legs,
            trip=trip,
            seat="economy",
            passengers=self._Passengers(adults=self.config.adults),
            currency=self.config.currency,
            max_stops=0 if self.config.nonstop_only else None,
        )

        result = self._fetch(query)
        tfs = None
        try:
            tfs = query.params().get("tfs")
        except Exception:  # noqa: BLE001 - deep link is best-effort
            tfs = None
        link = google_flights_link(origin, destination, departure_date,
                                   return_date, tfs=tfs,
                                   currency=self.config.currency)

        offers: List[Offer] = []
        trip_type = "round_trip" if return_date else "one_way"
        for itin in result:
            price = self._price(itin)
            if price is None or price <= 0:
                continue
            legs_list = getattr(itin, "flights", []) or []
            stops = max(len(legs_list) - 1, 0) if legs_list else None
            airlines = getattr(itin, "airlines", None) or []
            airline = ", ".join(airlines) if airlines else None
            offers.append(Offer(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                price=round(float(price), 2),
                currency=self.config.currency,
                trip_type=trip_type,
                airline=airline,
                stops=stops,
                deep_link=link,
            ))
        offers.sort(key=lambda o: o.price)
        return offers

    def _fetch(self, query):
        """Call get_flights with retries; empty result -> [] (not an error)."""
        last_exc = None
        for attempt in range(self.config.fetch_retries):
            try:
                return self._get_flights(query, proxy=self.config.fetch_proxy)
            except self._FlightsNotFound:
                return []
            except Exception as exc:  # noqa: BLE001 - network / parse hiccups
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise ProviderError(f"Google Flights fetch failed: {last_exc}")

    @staticmethod
    def _price(itin) -> Optional[float]:
        raw = getattr(itin, "price", None)
        if raw is None:
            return None
        # price is normally an int in the requested currency; be defensive
        # in case a build returns a "MYR 1,234"-style string.
        if isinstance(raw, (int, float)):
            return float(raw)
        digits = "".join(ch for ch in str(raw) if ch.isdigit() or ch == ".")
        try:
            return float(digits) if digits else None
        except ValueError:
            return None
