"""Core data structures shared across the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    """The "usual price" for a route *and trip type*, from recent history.

    One-way and round-trip fares must never share a baseline: a return ticket
    costs roughly double, so pooling them puts the median between the two and
    makes every one-way look ~50% underpriced.
    """

    route_key: str
    samples: int
    trip_type: str = "one_way"
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
    city: str = ""                 # human name; the digest shows this, not IATA
    maps_url: str = ""             # where in the world this actually is

    # How the discount was established. "date_drop" compares this departure
    # date against what the *same date* cost on earlier days — immune to a
    # cheap date merely scrolling into the rolling window. "route" compares
    # against the route's usual cheapest, used when the date is too new to
    # have its own history; it means "cheap date found", not "price fell".
    basis: str = "route"
    previous_price: Optional[float] = None   # what this date last cost
    previous_date: Optional[str] = None      # ...and when we saw that
    basis_samples: int = 0                   # observations behind the baseline

    # Statistical evidence, so the email can say *why* this is unusual rather
    # than only by how much.
    z_score: float = 0.0            # robust (MAD-based) deviations below usual
    percentile: float = 1.0         # fraction of tracked days this cheap or cheaper
    is_new_low: bool = False        # cheaper than anything on record
    days_since_cheaper: Optional[int] = None
    rarity: str = ""                # short human phrase, e.g. "cheapest in 12 days"

    @property
    def is_price_drop(self) -> bool:
        return self.basis == "date_drop"

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
    # False until the baseline has MIN_SAMPLES days behind it. The digest must
    # not print a "usual" price it is not willing to compute a discount from.
    baseline_trusted: bool = False
    maps_url: str = ""             # where in the world this actually is
    # How much of the scanned window this route actually returned. "Cheapest"
    # over 1 date and over 30 is the same word for very different claims, and
    # the difference is invisible in the price alone.
    dates_seen: int = 0
    dates_scanned: int = 0

    @property
    def coverage(self) -> Optional[float]:
        if not self.dates_scanned:
            return None
        return self.dates_seen / self.dates_scanned


@dataclass
class RunResult:
    run_date: str
    currency: str
    deals: List[Deal]
    summaries: List[RouteSummary]
    offers_checked: int
    errors: List[str]
    # Departure dates probed this run. "Cheapest" always means cheapest among
    # these — Google prices each date separately, so stating the window keeps
    # the digest from reading as "the cheapest date that exists".
    scanned_departures: List[str] = field(default_factory=list)
    # Set when the QA gate withheld alerts it could not stand behind. The
    # digest says so out loud: silently sending a shorter list would look
    # identical to a quiet market, which is how bad statistics went unnoticed
    # for days at a time.
    qa_withheld: List[str] = field(default_factory=list)
