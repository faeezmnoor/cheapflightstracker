"""Runtime configuration.

Everything is driven by environment variables so the same code runs locally,
in CI, or on a server without edits. Sensible defaults are baked in for the
"KL -> anywhere in Indonesia" use case, and any of them can be overridden.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List
from urllib.parse import quote_plus


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
# Every Indonesian airport confirmed reachable from KL by
# scripts/probe_destinations.py (49 candidates probed, 26 reachable).
# Airports with no KL service at all are deliberately absent — each one would
# burn 30 searches a day to find nothing. Re-run the probe to refresh this.
ALL_INDONESIA_DESTINATIONS: Dict[str, str] = {
    # --- Direct from KUL ---------------------------------------------- #
    "CGK": "Jakarta",
    "DPS": "Denpasar (Bali)",
    "SUB": "Surabaya",
    "KNO": "Medan",
    "PDG": "Padang",
    "PKU": "Pekanbaru",
    "PNK": "Pontianak",
    "LOP": "Lombok",
    # --- Reachable with a connection (international + domestic) -------- #
    # Yogyakarta's international traffic moved to YIA (Kulon Progo); JOG
    # (Adisutjipto) is domestic-only, so KUL->JOG returns nothing at all.
    "YIA": "Yogyakarta",
    "SOC": "Solo",
    "SRG": "Semarang",
    "MLG": "Malang",
    "BDO": "Bandung",
    "BTJ": "Banda Aceh",
    "PLM": "Palembang",
    "DJB": "Jambi",
    "TKG": "Bandar Lampung",
    "BTH": "Batam",
    "UPG": "Makassar",
    "MDC": "Manado",
    "KDI": "Kendari",
    "BPN": "Balikpapan",
    "BDJ": "Banjarmasin",
    "LBJ": "Labuan Bajo (Komodo)",
    "AMQ": "Ambon",
    "SOQ": "Sorong (Raja Ampat)",
}

# Scan everything reachable. Work is split across parallel CI shards, so the
# cost of breadth is more shards rather than a longer run.
DEFAULT_ROUTES: List[str] = list(ALL_INDONESIA_DESTINATIONS)


# What to drop into Google Maps for each destination. Spelled out rather than
# derived from the display name: "Solo" is formally Surakarta, and several
# labels carry a parenthetical that would confuse a search ("Sorong (Raja
# Ampat)"). Adding the country disambiguates the rest.
DESTINATION_MAP_QUERIES: Dict[str, str] = {
    "CGK": "Jakarta, Indonesia",
    "DPS": "Denpasar, Bali, Indonesia",
    "SUB": "Surabaya, Indonesia",
    "KNO": "Medan, Indonesia",
    "PDG": "Padang, West Sumatra, Indonesia",
    "PKU": "Pekanbaru, Indonesia",
    "PNK": "Pontianak, Indonesia",
    "LOP": "Lombok, Indonesia",
    "YIA": "Yogyakarta, Indonesia",
    "SOC": "Surakarta, Indonesia",
    "SRG": "Semarang, Indonesia",
    "MLG": "Malang, Indonesia",
    "BDO": "Bandung, Indonesia",
    "BTJ": "Banda Aceh, Indonesia",
    "PLM": "Palembang, Indonesia",
    "DJB": "Jambi, Indonesia",
    "TKG": "Bandar Lampung, Indonesia",
    "BTH": "Batam, Indonesia",
    "UPG": "Makassar, Indonesia",
    "MDC": "Manado, Indonesia",
    "KDI": "Kendari, Indonesia",
    "BPN": "Balikpapan, Indonesia",
    "BDJ": "Banjarmasin, Indonesia",
    "LBJ": "Labuan Bajo, Indonesia",
    "AMQ": "Ambon, Indonesia",
    "SOQ": "Sorong, West Papua, Indonesia",
}


def google_maps_url(query: str) -> str:
    """A map link that works everywhere.

    Google's Maps URLs API is the documented cross-platform form: it renders
    in any browser and deep-links into the Maps app on iOS and Android, so one
    link serves desktop and phone.
    """
    return ("https://www.google.com/maps/search/?api=1&query="
            + quote_plus(query))


def shard_routes(routes: List["Route"], shard: int, shards: int) -> List["Route"]:
    """Deal routes round-robin across CI shards.

    Round-robin rather than contiguous blocks so each shard gets a mix of
    fast and slow routes instead of one shard drawing all the heavy ones.
    """
    if shards <= 1:
        return list(routes)
    if not 0 <= shard < shards:
        raise ValueError(f"shard {shard} out of range for {shards} shards")
    return [r for i, r in enumerate(routes) if i % shards == shard]


@dataclass
class Route:
    origin: str
    destination: str
    city: str
    maps_query: str = ""

    @property
    def key(self) -> str:
        return f"{self.origin}-{self.destination}"

    @property
    def maps_url(self) -> str:
        """Falls back to the display name minus any parenthetical, so a route
        supplied via ROUTES still gets a usable link."""
        query = self.maps_query or self.city.split("(")[0].strip()
        return google_maps_url(query)

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

    # One-way departures: EVERY date in the window, not a sample. Google prices
    # each date separately, so an unprobed date is a price we cannot see, and
    # sampling means "cheapest" only ever meant "cheapest of the days we
    # happened to look at". Window is the next 30 days.
    departure_window_days: int = 30
    departure_start_offset: int = 1
    departure_offsets: List[int] = field(
        default_factory=lambda: list(range(1, 31))
    )

    # Round trips are off by default: exhaustive one-way coverage is what
    # surfaces underpriced fares, and a return can be priced as two one-ways.
    # Enable with ROUND_TRIP=true; returns are then capped by max_trip_days
    # (the "30 days from go to from date" rule).
    round_trip: bool = False
    round_trip_offsets: List[int] = field(
        default_factory=lambda: list(range(2, 31, 3))
    )
    stay_lengths: List[int] = field(default_factory=lambda: [7, 14])
    max_trip_days: int = 30

    # --- What counts as a "deal" ------------------------------------------ #
    # A fare qualifies on ANY of: a new low, a robust z-score, sitting in the
    # rare tail, or a large plain discount — but always subject to the two
    # floors below, so trivial dips never reach the inbox.
    deal_threshold: float = 0.20        # plain discount that qualifies alone
    severe_threshold: float = 0.35      # discount that makes a new low "severe"
    deal_z: float = -2.0                # robust deviations below usual
    severe_z: float = -3.0
    rare_percentile: float = 0.10       # bottom 10% of prices ever seen
    severe_percentile: float = 0.02
    severe_discount_floor: float = 0.25  # "severe" needs a big saving, not just a big z
    z_percentile_guard: float = 0.25     # a z-score only counts if rarity agrees
    min_discount: float = 0.12          # floor: never alert on noise
    min_saving: float = 40.0            # floor: cash worth an email
    min_samples: int = 5                # days of route history before flagging
    # Prior sightings of the *same departure date* before that date's own
    # history is quoted alongside an alert. Purely annotation now: per-date
    # readings are too noisy to originate an alert, so this only controls
    # whether we can say what this date used to cost.
    min_date_samples: int = 3
    history_window_days: int = 90       # how far back "usual price" looks

    # --- Provider / infra -------------------------------------------------- #
    provider: str = "googleflights"     # "googleflights" | "mock"
    # Point-of-sale. Google prices by market, so querying without these from a
    # US datacenter can return different fares than a shopper in Malaysia sees.
    region: str = "my"                  # gl= (country)
    language: str = "en"                # hl= (language)
    fetch_retries: int = 4              # retries on a failed Google fetch
    fetch_proxy: str | None = None      # optional proxy URL for the fetcher
    # Google throttles bursts hard: at ~1s spacing roughly a third of searches
    # failed. Pausing longer (plus jitter in search.py) trades a slower run for
    # far better coverage — a daily job has all the time it needs.
    request_pause_seconds: float = 3.0

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
    date_history_path: str = "data/date_prices.json"
    alert_state_path: str = "data/alert_state.json"
    # Re-alerting the same route: needs this much further off the last alerted
    # price, or this many days elapsed, whichever comes first.
    repeat_improvement: float = 0.05
    repeat_cooldown_days: int = 7

    @classmethod
    def from_env(cls) -> "Config":
        origin = _get("ORIGIN", "KUL")

        route_codes = _get("ROUTES")
        if route_codes:
            codes = [c.strip().upper() for c in route_codes.split(",") if c.strip()]
        else:
            codes = DEFAULT_ROUTES
        routes = [
            Route(origin, code, ALL_INDONESIA_DESTINATIONS.get(code, code),
                  DESTINATION_MAP_QUERIES.get(code, ""))
            for code in codes
        ]

        smtp_user = _get("SMTP_USER")
        window = _get_int("DEPARTURE_WINDOW_DAYS", 30)
        start = _get_int("DEPARTURE_START_OFFSET", 1)
        return cls(
            origin=origin,
            routes=routes,
            currency=_get("CURRENCY", "MYR"),
            adults=_get_int("ADULTS", 1),
            nonstop_only=_get_bool("NONSTOP_ONLY", False),
            max_offers_per_search=_get_int("MAX_OFFERS_PER_SEARCH", 3),
            departure_window_days=window,
            departure_start_offset=start,
            # Explicit DEPARTURE_OFFSETS still wins; otherwise scan every date
            # in [start, window] so coverage is exhaustive rather than sampled.
            departure_offsets=_get_int_list(
                "DEPARTURE_OFFSETS", list(range(start, window + 1))),
            round_trip=_get_bool("ROUND_TRIP", False),
            round_trip_offsets=_get_int_list(
                "ROUND_TRIP_OFFSETS", list(range(start + 1, window + 1, 3))),
            stay_lengths=_get_int_list("STAY_LENGTHS", [7, 14]),
            max_trip_days=_get_int("MAX_TRIP_DAYS", 30),
            deal_threshold=_get_float("DEAL_THRESHOLD", 0.20),
            severe_threshold=_get_float("SEVERE_THRESHOLD", 0.35),
            min_samples=_get_int("MIN_SAMPLES", 5),
            deal_z=_get_float("DEAL_Z", -2.0),
            severe_z=_get_float("SEVERE_Z", -3.0),
            rare_percentile=_get_float("RARE_PERCENTILE", 0.10),
            severe_percentile=_get_float("SEVERE_PERCENTILE", 0.02),
            severe_discount_floor=_get_float("SEVERE_DISCOUNT_FLOOR", 0.25),
            z_percentile_guard=_get_float("Z_PERCENTILE_GUARD", 0.25),
            min_discount=_get_float("MIN_DISCOUNT", 0.12),
            min_saving=_get_float("MIN_SAVING", 40.0),
            min_date_samples=_get_int("MIN_DATE_SAMPLES", 3),
            history_window_days=_get_int("HISTORY_WINDOW_DAYS", 90),
            provider=_get("PROVIDER", "googleflights"),
            region=_get("REGION", "my"),
            language=_get("LANGUAGE", "en"),
            fetch_retries=_get_int("FETCH_RETRIES", 4),
            fetch_proxy=_get("FF_PROXY"),
            request_pause_seconds=_get_float("REQUEST_PAUSE_SECONDS", 3.0),
            smtp_host=_get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=_get_int("SMTP_PORT", 465),
            smtp_user=smtp_user,
            smtp_app_password=_get("SMTP_APP_PASSWORD"),
            email_from=_get("EMAIL_FROM", smtp_user),
            email_to=_get("EMAIL_TO", smtp_user),
            always_email=_get_bool("ALWAYS_EMAIL", True),
            dry_run=_get_bool("DRY_RUN", False),
            history_path=_get("HISTORY_PATH", "data/price_history.json"),
            date_history_path=_get("DATE_HISTORY_PATH", "data/date_prices.json"),
            alert_state_path=_get("ALERT_STATE_PATH", "data/alert_state.json"),
            repeat_improvement=_get_float("REPEAT_IMPROVEMENT", 0.05),
            repeat_cooldown_days=_get_int("REPEAT_COOLDOWN_DAYS", 7),
        )
