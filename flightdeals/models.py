"""Core data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class Offer:
    """A single priced flight option returned by a provider."""

    origin: str
    destination: str
    departure_date: str            # YYYY-MM-DD
    price: float
    currency: str
    trip_type: str                 # "one_way" | "round_trip"
    return_date: Optional[str] = None
    airline: Optional[str] = None
    stops: Optional[int] = None    # stops on the outbound leg (0 = direct)
    deep_link: Optional[str] = None
    observed_date: Optional[str] = None

    @property
    def route_key(self) -> str:
        return f"{self.origin}-{self.destination}"

    def to_record(self) -> dict:
        return asdict(self)

    @classmethod
    def from_record(cls, record: dict) -> "Offer":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in record.items() if k in allowed})


@dataclass
class Baseline:
    """The "usual price" for a route, derived from recent history."""

    route_key: str
    samples: int
    median: Optional[float] = None
    mean: Optional[float] = None
    p25: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    @property
    def is_reliable(self) -> bool:
        return self.median is not None and self.samples > 0


@dataclass
class Deal:
    """An offer flagged as cheaper than usual, with the supporting numbers."""

    offer: Offer
    baseline: Baseline
    discount_pct: float            # 0.0 - 1.0, vs. the baseline median
    saving: float                  # currency units off the usual price
    severity: str                  # "severe" | "deal"

    @property
    def is_severe(self) -> bool:
        return self.severity == "severe"


@dataclass
class RouteSummary:
    """Per-route headline for the daily digest (cheapest fare seen today)."""

    route_key: str
    city: str
    cheapest: Optional[Offer]
    baseline: Baseline
    discount_pct: Optional[float]  # None when there's no reliable baseline yet


@dataclass
class RunResult:
    run_date: str
    currency: str
    deals: List[Deal]
    summaries: List[RouteSummary]
    offers_checked: int
    errors: List[str]
