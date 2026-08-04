"""Shared provider helpers."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote


def google_flights_link(origin: str, destination: str,
                        departure_date: str, return_date: Optional[str] = None,
                        tfs: Optional[str] = None, currency: str = "MYR") -> str:
    """A Google Flights URL a human can click through to.

    If ``tfs`` (the base64 protobuf token from a fast-flights query) is given,
    build the exact deep link to that search; otherwise fall back to a plain
    text search query.
    """
    if tfs:
        return (f"https://www.google.com/travel/flights?tfs={quote(tfs)}"
                f"&curr={quote(currency)}&hl=en")
    if return_date:
        q = (f"Flights from {origin} to {destination} on {departure_date} "
             f"returning {return_date}")
    else:
        q = f"One-way flights from {origin} to {destination} on {departure_date}"
    return "https://www.google.com/travel/flights?q=" + quote(q)
