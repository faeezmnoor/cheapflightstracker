import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import (append_observations, compute_baseline,
                                  load_history, prune_history, save_history)
from flightdeals.models import Offer


def _offer(dest, price, dep="2026-09-01"):
    return Offer(origin="KUL", destination=dest, departure_date=dep,
                 price=price, currency="MYR", trip_type="one_way")


class BaselineTest(unittest.TestCase):
    def _records(self, prices, route_dest="CGK", observed="2026-08-01"):
        recs = []
        for p in prices:
            o = _offer(route_dest, p)
            r = o.to_record()
            r["observed_date"] = observed
            recs.append(r)
        return recs

    def test_empty_history_gives_no_baseline(self):
        b = compute_baseline([], "KUL-CGK", 90, date(2026, 8, 1))
        self.assertEqual(b.samples, 0)
        self.assertFalse(b.is_reliable)

    def test_median_and_percentile(self):
        recs = self._records([100, 200, 300, 400, 500])
        b = compute_baseline(recs, "KUL-CGK", 90, date(2026, 8, 2))
        self.assertEqual(b.samples, 5)
        self.assertEqual(b.median, 300)
        self.assertEqual(b.minimum, 100)
        self.assertEqual(b.maximum, 500)
        self.assertEqual(b.p25, 200)  # linear-interp p25 of 1..5 evenly spaced

    def test_window_excludes_old_records(self):
        today = date(2026, 8, 1)
        old = (today - timedelta(days=200)).isoformat()
        recs = self._records([100, 100], observed=old)
        recs += self._records([500], observed=today.isoformat())
        b = compute_baseline(recs, "KUL-CGK", 90, today)
        self.assertEqual(b.samples, 1)
        self.assertEqual(b.median, 500)

    def test_route_isolation(self):
        recs = self._records([100], route_dest="CGK")
        recs += self._records([900], route_dest="DPS")
        b = compute_baseline(recs, "KUL-DPS", 90, date(2026, 8, 2))
        self.assertEqual(b.samples, 1)
        self.assertEqual(b.median, 900)

    def test_prune_drops_old(self):
        today = date(2026, 8, 1)
        recs = self._records([1], observed=(today - timedelta(days=400)).isoformat())
        recs += self._records([2], observed=today.isoformat())
        kept = prune_history(recs, 120, today)
        self.assertEqual(len(kept), 1)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "history.json")
            recs = append_observations([], [_offer("CGK", 250)], "2026-08-01")
            save_history(path, recs)
            self.assertTrue(os.path.exists(path))
            loaded = load_history(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["price"], 250)

    def test_load_missing_file(self):
        self.assertEqual(load_history("/nonexistent/path/x.json"), [])


if __name__ == "__main__":
    unittest.main()
