"""Runtime configuration.

Everything is driven by environment variables so the same code runs locally,
in CI, or on a server without edits. Sensible defaults are baked in for the
"KL -> anywhere in Indonesia" use case, and any of them can be overridden.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List


# --------------------------------------------------------------------------- #
# Small env helpers
# --------------------------------------------------------------------------- #
def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_int_list(name: str, default: List[int]) -> List[int]:
    raw = _get(name)
    if not raw:
        return list(default)
    out: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            try:
                out.append(int(chunk))
            except ValueError:
                continue
    return out or list(default)


# --------------------------------------------------------------------------- #
# Destinations: every reasonably-served airport in Indonesia from KL.
# IATA code -> human-friendly city label.
# --------------------------------------------------------------------------- #
ALL_INDONESIA_DESTINATIONS: Dict[str, str] = {
    "CGK": "Jakarta",
    "DPS": "Denpasar (Bali)",
    "SUB": "Surabaya",
    "KNO": "Medan",
    "JOG": "Yogyakarta",
    "BDO": "Bandung",
    "UPG": "Makassar",
    "LOP": "Lombok",
    "SRG": "Semarang",
    "PDG": "Padang",
    "PKU": "Pekanbaru",
    "BPN": "Balikpapan",
    "BTH": "Batam",
    "PLM": "Palembang",
    "PNK": "Pontianak",
}

# A conservative default that keeps the daily request count modest (Google
# Flights has no quota, but heavy scraping risks rate-limiting). Widen ROUTES
# once you've confirmed runs stay reliable.
DEFAULT_ROUTES: List[str] = [
    "CGK", "DPS", "SUB", "KNO", "JOG",
    "BDO", "UPG", "LOP", "BTH", "PDG",
]


@dataclass
class Route:
    origin: str
    destination: str
    city: str

    @property
    def key(self) -> str:
        return f"{self.origin}-{self.destination}"

    @property
    def label(self) -> str:
        return f"{self.origin} -> {self.destination} ({self.city})"


@dataclass
class Config:
    # --- Where / what to search ------------------------------------------- #
    origin: str = "KUL"
    routes: List[Route] = field(default_factory=list)
    currency: str = "MYR"
    adults: int = 1
    nonstop_only: bool = False          # direct flights are fine but not required
    max_offers_per_search: int = 3

    # Departure dates to probe, expressed as "days from today". Kept small by
    # default to keep total Google requests modest — widen via
    # DEPARTURE_OFFSETS once you've confirmed runs stay reliable.
    departure_offsets: List[int] = field(default_factory=lambda: [14, 35])

    # Round-trip: for each departure date, try these stay-lengths (days).
    # Capped so the return is always within max_trip_days of departure.
    round_trip: bool = True
    stay_lengths: List[int] = field(default_factory=lambda: [14])
    max_trip_days: int = 30

    # --- What counts as a "deal" ------------------------------------------ #
    deal_threshold: float = 0.20        # >=20% under the usual price
    severe_threshold: float = 0.35      # >=35% under the usual price = "severe"
    min_samples: int = 5                # need this much history before flagging
    history_window_days: int = 90       # how far back "usual price" looks

    # --- Provider / infra -------------------------------------------------- #
    provider: str = "googleflights"     # "googleflights" | "mock"
    fetch_retries: int = 3              # retries on a failed Google fetch
    fetch_proxy: str | None = None      # optional proxy URL for the fetcher
    request_pause_seconds: float = 1.0   # be gentle between Google requests

    # --- Email ------------------------------------------------------------- #
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_app_password: str | None = None
    email_from: str | None = None
    email_to: str | None = None
    always_email: bool = True           # send even on "no deals" days (a digest)
    dry_run: bool = False               # print the email instead of sending it

    # --- Storage ----------------------------------------------------------- #
    history_path: str = "data/price_history.json"

    @classmethod
    def from_env(cls) -> "Config":
        origin = _get("ORIGIN", "KUL")

        route_codes = _get("ROUTES")
        if route_codes:
            codes = [c.strip().upper() for c in route_codes.split(",") if c.strip()]
        else:
            codes = DEFAULT_ROUTES
        routes = [
            Route(origin, code, ALL_INDONESIA_DESTINATIONS.get(code, code))
            for code in codes
        ]

        smtp_user = _get("SMTP_USER")
        return cls(
            origin=origin,
            routes=routes,
            currency=_get("CURRENCY", "MYR"),
            adults=_get_int("ADULTS", 1),
            nonstop_only=_get_bool("NONSTOP_ONLY", False),
            max_offers_per_search=_get_int("MAX_OFFERS_PER_SEARCH", 3),
            departure_offsets=_get_int_list("DEPARTURE_OFFSETS", [14, 35]),
            round_trip=_get_bool("ROUND_TRIP", True),
            stay_lengths=_get_int_list("STAY_LENGTHS", [14]),
            max_trip_days=_get_int("MAX_TRIP_DAYS", 30),
            deal_threshold=_get_float("DEAL_THRESHOLD", 0.20),
            severe_threshold=_get_float("SEVERE_THRESHOLD", 0.35),
            min_samples=_get_int("MIN_SAMPLES", 5),
            history_window_days=_get_int("HISTORY_WINDOW_DAYS", 90),
            provider=_get("PROVIDER", "googleflights"),
            fetch_retries=_get_int("FETCH_RETRIES", 3),
            fetch_proxy=_get("FF_PROXY"),
            request_pause_seconds=_get_float("REQUEST_PAUSE_SECONDS", 1.0),
            smtp_host=_get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=_get_int("SMTP_PORT", 465),
            smtp_user=smtp_user,
            smtp_app_password=_get("SMTP_APP_PASSWORD"),
            email_from=_get("EMAIL_FROM", smtp_user),
            email_to=_get("EMAIL_TO", smtp_user),
            always_email=_get_bool("ALWAYS_EMAIL", True),
            dry_run=_get_bool("DRY_RUN", False),
            history_path=_get("HISTORY_PATH", "data/price_history.json"),
        )
