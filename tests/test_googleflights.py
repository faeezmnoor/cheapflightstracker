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


@unittest.skipUnless(HAS_FF, "fast-flights not installed")
class LenientParserTest(unittest.TestCase):
    """The library's parser dies on routes whose pages omit the airline
    metadata block (observed on KUL->JOG and KUL->BDO). We only need price,
    airlines and leg count, so parse those pages leniently instead."""

    @staticmethod
    def _page(payload):
        import json
        return ('<html><body><script class="ds:1">AF_initDataCallback({key: '
                "'ds:1', data:" + json.dumps(payload) +
                ", sideChannel: {}});</script></body></html>")

    @staticmethod
    def _itin(price, n_legs, airlines):
        leg = [None, None, None, "KUL", "Kuala Lumpur", "Dest", "JOG", None,
               [7, 30], None, [9, 45], 125, None, None, None, None, None,
               "Airbus A320", None, None, [2026, 9, 9], [2026, 9, 9]]
        return [["type", airlines, [leg] * n_legs, *([None] * 19), [None] * 9],
                [[None, price]]]

    def test_recovers_when_metadata_block_is_missing(self):
        from flightdeals.providers.googleflights import _parse_itineraries
        # payload[7] is None -> the exact shape that breaks the library parser
        payload = [None, None, None,
                   [[self._itin(342, 1, ["AK"]), self._itin(455, 2, ["JT"])]],
                   None, None, None, None]
        got = _parse_itineraries(self._page(payload))
        self.assertEqual([i.price for i in got], [342.0, 455.0])
        self.assertEqual(len(got[0].flights), 1)   # direct
        self.assertEqual(len(got[1].flights), 2)   # 1 stop
        self.assertEqual(got[0].airlines, ["AK"])

    def test_library_really_fails_on_that_shape(self):
        # Guards the premise: if a future fast-flights handles this, the
        # salvage path is no longer needed and this test will flag it.
        from fast_flights.parser import parse as lib_parse
        payload = [None, None, None, [[self._itin(342, 1, ["AK"])]],
                   None, None, None, None]
        with self.assertRaises(Exception):
            lib_parse(self._page(payload))

    def test_tolerates_junk(self):
        from flightdeals.providers.googleflights import _parse_itineraries
        self.assertEqual(_parse_itineraries("<html></html>"), [])
        self.assertEqual(_parse_itineraries(self._page([None, None, None, [None]])), [])
        # malformed entries are skipped, not fatal
        self.assertEqual(_parse_itineraries(self._page([None, None, None, [[["x"], None]]])), [])

    def test_skips_zero_price_and_legless(self):
        from flightdeals.providers.googleflights import _parse_itineraries
        payload = [None, None, None,
                   [[self._itin(0, 1, ["AK"]), self._itin(200, 0, ["AK"]),
                     self._itin(310, 1, ["AK"])]], None, None, None, None]
        got = _parse_itineraries(self._page(payload))
        self.assertEqual([i.price for i in got], [310.0])


if __name__ == "__main__":
    unittest.main()
