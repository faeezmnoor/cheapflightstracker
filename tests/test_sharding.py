import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import daily_cheapest
from flightdeals.config import ALL_INDONESIA_DESTINATIONS, Config, Route, shard_routes
from flightdeals.main import read_shards, write_shard
from flightdeals.models import Offer


def _routes(n):
    codes = list(ALL_INDONESIA_DESTINATIONS)[:n]
    return [Route("KUL", c, ALL_INDONESIA_DESTINATIONS[c]) for c in codes]


class ShardRoutesTest(unittest.TestCase):
    def test_every_route_appears_exactly_once(self):
        routes = _routes(26)
        seen = []
        for s in range(4):
            seen += [r.destination for r in shard_routes(routes, s, 4)]
        self.assertEqual(sorted(seen), sorted(r.destination for r in routes))
        self.assertEqual(len(seen), len(set(seen)), "a route was duplicated")

    def test_shards_are_balanced(self):
        routes = _routes(26)
        sizes = [len(shard_routes(routes, s, 4)) for s in range(4)]
        self.assertLessEqual(max(sizes) - min(sizes), 1)

    def test_single_shard_returns_everything(self):
        routes = _routes(5)
        self.assertEqual(len(shard_routes(routes, 0, 1)), 5)

    def test_more_shards_than_routes_is_safe(self):
        routes = _routes(2)
        collected = [r for s in range(4) for r in shard_routes(routes, s, 4)]
        self.assertEqual(len(collected), 2)   # two shards simply get nothing

    def test_rejects_bad_shard_index(self):
        with self.assertRaises(ValueError):
            shard_routes(_routes(3), 4, 4)


class DailyCheapestTest(unittest.TestCase):
    """Exhaustive scanning yields thousands of offers a day; only the cheapest
    per route/trip-type is persisted, which is all the baseline reads."""

    def test_keeps_only_cheapest_per_route_and_trip_type(self):
        offers = [
            Offer("KUL", "CGK", "2026-09-01", 400, "MYR", "one_way"),
            Offer("KUL", "CGK", "2026-09-05", 320, "MYR", "one_way"),   # winner
            Offer("KUL", "CGK", "2026-09-09", 380, "MYR", "one_way"),
            Offer("KUL", "CGK", "2026-09-01", 700, "MYR", "round_trip",
                  return_date="2026-09-15"),                            # winner
            Offer("KUL", "DPS", "2026-09-02", 500, "MYR", "one_way"),   # winner
        ]
        kept = daily_cheapest(offers)
        self.assertEqual(len(kept), 3)
        prices = {(o.route_key, o.trip_type): o.price for o in kept}
        self.assertEqual(prices[("KUL-CGK", "one_way")], 320)
        self.assertEqual(prices[("KUL-CGK", "round_trip")], 700)
        self.assertEqual(prices[("KUL-DPS", "one_way")], 500)

    def test_preserves_the_winning_offer_details(self):
        kept = daily_cheapest([
            Offer("KUL", "CGK", "2026-09-01", 400, "MYR", "one_way"),
            Offer("KUL", "CGK", "2026-09-05", 320, "MYR", "one_way",
                  airline="AK", stops=0),
        ])
        self.assertEqual(kept[0].departure_date, "2026-09-05")
        self.assertEqual(kept[0].airline, "AK")

    def test_empty(self):
        self.assertEqual(daily_cheapest([]), [])


class ShardRoundTripTest(unittest.TestCase):
    """A shard writes what the report step must be able to read back."""

    def test_write_then_read(self):
        cfg = Config(routes=_routes(3), round_trip=False,
                     departure_offsets=[1, 2])
        today = date(2026, 8, 7)
        offers = {
            "KUL-CGK": [Offer("KUL", "CGK", "2026-08-08", 350, "MYR", "one_way"),
                        Offer("KUL", "CGK", "2026-08-09", 300, "MYR", "one_way")],
            "KUL-DPS": [Offer("KUL", "DPS", "2026-08-08", 500, "MYR", "one_way")],
        }
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "obs-0.json")
            write_shard(p, today, offers, ["boom"], cfg)

            with open(p, encoding="utf-8") as fh:
                payload = json.load(fh)
            self.assertEqual(payload["run_date"], "2026-08-07")
            self.assertEqual(len(payload["offers"]), 2)   # reduced to cheapest

            merged, errors, scanned, run_date, scanned_count = read_shards([p])
            self.assertEqual(run_date, "2026-08-07")
            self.assertEqual(errors, ["boom"])
            self.assertEqual(scanned, ["2026-08-08", "2026-08-09"])
            self.assertEqual(merged["KUL-CGK"][0].price, 300)
            self.assertEqual(merged["KUL-DPS"][0].price, 500)
            # raw count survives compaction so the digest can report it
            self.assertEqual(scanned_count, 3)

    def test_merges_multiple_shards(self):
        cfg = Config(routes=_routes(2), round_trip=False, departure_offsets=[1])
        today = date(2026, 8, 7)
        with tempfile.TemporaryDirectory() as d:
            write_shard(os.path.join(d, "a.json"), today,
                        {"KUL-CGK": [Offer("KUL", "CGK", "2026-08-08", 350,
                                           "MYR", "one_way")]}, [], cfg)
            write_shard(os.path.join(d, "b.json"), today,
                        {"KUL-DPS": [Offer("KUL", "DPS", "2026-08-08", 500,
                                           "MYR", "one_way")]}, ["err"], cfg)
            merged, errors, _, _, _ = read_shards([os.path.join(d, "*.json")])
            self.assertEqual(sorted(merged), ["KUL-CGK", "KUL-DPS"])
            self.assertEqual(errors, ["err"])

    def test_missing_files_fail_loudly(self):
        with self.assertRaises(SystemExit):
            read_shards(["/nonexistent/none-*.json"])


class RouteListTest(unittest.TestCase):
    def test_only_reachable_airports_are_listed(self):
        """Airports the probe found unreachable from KL must stay out — each
        would burn 30 searches a day to find nothing."""
        unreachable = {"HLP", "JOG", "KJT", "DTB", "TNJ", "PGK", "TJQ", "BKS",
                       "BWX", "PKY", "TRK", "BEJ", "PLW", "GTO", "TTE", "DJJ",
                       "TIM", "BIK", "MKW", "KOE", "MOF", "ENE", "TMC", "WGP"}
        self.assertEqual(set(ALL_INDONESIA_DESTINATIONS) & unreachable, set())

    def test_cheap_direct_routes_present(self):
        for code in ("CGK", "DPS", "KNO", "PDG", "PKU", "PNK", "SUB", "LOP"):
            self.assertIn(code, ALL_INDONESIA_DESTINATIONS)


if __name__ == "__main__":
    unittest.main()
