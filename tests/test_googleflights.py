import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config

try:
    import fast_flights  # noqa: F401
    from flightdeals.providers.googleflights import GoogleFlightsProvider
    HAS_FF = True
except Exception:  # pragma: no cover - depends on env
    HAS_FF = False


class _FakeLeg:
    """Stands in for fast_flights SingleFlight (only length is inspected)."""


class _FakeItin:
    def __init__(self, price, airlines, n_legs):
        self.price = price
        self.airlines = airlines
        self.flights = [_FakeLeg() for _ in range(n_legs)]


class _FakeQuery:
    def params(self):
        return {"tfs": "ABC123", "hl": "", "curr": "MYR"}


@unittest.skipUnless(HAS_FF, "fast-flights not installed")
class GoogleFlightsMappingTest(unittest.TestCase):
    """Validate the Offer mapping without hitting the network."""

    def _provider(self, itineraries):
        c = Config(provider="googleflights", currency="MYR", adults=1)
        p = GoogleFlightsProvider(c)
        # Replace the network calls with deterministic fakes.
        p._create_query = lambda **kw: _FakeQuery()
        p._get_flights = lambda q, proxy=None: itineraries
        return p

    def test_oneway_mapping(self):
        p = self._provider([
            _FakeItin(320, ["AirAsia"], 1),           # direct
            _FakeItin(450, ["Batik Air", "MAS"], 2),  # 1 stop
        ])
        offers = p.search("KUL", "CGK", "2026-09-05")
        self.assertEqual(len(offers), 2)
        # sorted cheapest-first
        self.assertEqual(offers[0].price, 320.0)
        self.assertEqual(offers[0].stops, 0)
        self.assertEqual(offers[0].trip_type, "one_way")
        self.assertEqual(offers[0].currency, "MYR")
        self.assertEqual(offers[0].airline, "AirAsia")
        self.assertEqual(offers[1].stops, 1)
        self.assertEqual(offers[1].airline, "Batik Air, MAS")
        # deep link built from the tfs token
        self.assertIn("tfs=ABC123", offers[0].deep_link)

    def test_round_trip_mapping(self):
        p = self._provider([_FakeItin(680, ["AirAsia"], 2)])
        offers = p.search("KUL", "DPS", "2026-09-05", return_date="2026-09-19")
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].trip_type, "round_trip")
        self.assertEqual(offers[0].return_date, "2026-09-19")
        self.assertEqual(offers[0].price, 680.0)

    def test_drops_zero_and_none_prices(self):
        p = self._provider([
            _FakeItin(0, ["X"], 1),
            _FakeItin(None, ["Y"], 1),
            _FakeItin(199, ["Z"], 1),
        ])
        offers = p.search("KUL", "KNO", "2026-09-05")
        self.assertEqual([o.price for o in offers], [199.0])

    def test_parses_string_price(self):
        p = self._provider([_FakeItin("MYR 1,234", ["X"], 1)])
        offers = p.search("KUL", "UPG", "2026-09-05")
        self.assertEqual(offers[0].price, 1234.0)

    def test_empty_result(self):
        p = self._provider([])
        self.assertEqual(p.search("KUL", "SUB", "2026-09-05"), [])


if __name__ == "__main__":
    unittest.main()
