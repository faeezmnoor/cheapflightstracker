import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.baseline import (date_baseline, load_date_series,
                                  prune_date_series, record_date_prices,
                                  save_date_series, series_key)
from flightdeals.config import Config, Route
from flightdeals.detector import find_deals
from flightdeals.models import Offer


def _cfg(**kw):
    c = Config(min_samples=5, min_date_samples=2, deal_threshold=0.20,
               severe_threshold=0.35, history_window_days=90)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _route_history(dest, prices, start=date(2026, 8, 1)):
    """Route-level daily-cheapest records, one per day."""
    from datetime import timedelta
    return [{
        "origin": "KUL", "destination": dest, "departure_date": "2026-09-08",
        "price": p, "currency": "MYR", "trip_type": "one_way",
        "observed_date": (start + timedelta(days=i)).isoformat(),
    } for i, p in enumerate(prices)]


def _offer(dest, price, dep="2026-09-08"):
    return Offer("KUL", dest, dep, price, "MYR", "one_way")


class DateSeriesStoreTest(unittest.TestCase):
    def test_record_and_read_back(self):
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-09")
        series = record_date_prices(series, [_offer("UPG", 469)], "2026-08-10")
        key = series_key("KUL-UPG", "one_way", "2026-09-08")
        self.assertEqual(series[key], {"2026-08-09": 608.0, "2026-08-10": 469.0})

    def test_keeps_cheapest_within_a_day(self):
        series = record_date_prices({}, [_offer("UPG", 700), _offer("UPG", 480)],
                                    "2026-08-10")
        key = series_key("KUL-UPG", "one_way", "2026-09-08")
        self.assertEqual(series[key], {"2026-08-10": 480.0})

    def test_baseline_excludes_today(self):
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-09")
        series = record_date_prices(series, [_offer("UPG", 469)], "2026-08-10")
        median, samples, prev, prev_date = date_baseline(
            series, "KUL-UPG", "one_way", "2026-09-08", date(2026, 8, 10))
        self.assertEqual((median, samples), (608.0, 1))
        self.assertEqual((prev, prev_date), (608.0, "2026-08-09"))

    def test_baseline_absent_for_unseen_date(self):
        median, samples, _, _ = date_baseline(
            {}, "KUL-UPG", "one_way", "2026-09-08", date(2026, 8, 10))
        self.assertEqual((median, samples), (None, 0))

    def test_prune_drops_past_departures(self):
        series = record_date_prices({}, [_offer("UPG", 500, dep="2026-08-01")],
                                    "2026-07-30")
        series = record_date_prices(series, [_offer("UPG", 500, dep="2026-09-08")],
                                    "2026-08-10")
        pruned = prune_date_series(series, date(2026, 8, 10))
        self.assertEqual(list(pruned), [series_key("KUL-UPG", "one_way",
                                                   "2026-09-08")])

    def test_prune_trims_old_observations(self):
        series = {}
        for i in range(1, 20):
            series = record_date_prices(series, [_offer("UPG", 500 + i)],
                                        f"2026-08-{i:02d}")
        pruned = prune_date_series(series, date(2026, 8, 1), keep_observations=5)
        self.assertEqual(len(pruned[series_key("KUL-UPG", "one_way",
                                               "2026-09-08")]), 5)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "dates.json")
            series = record_date_prices({}, [_offer("UPG", 469)], "2026-08-10")
            save_date_series(p, series)
            self.assertEqual(load_date_series(p), series)

    def test_load_missing_file(self):
        self.assertEqual(load_date_series("/nonexistent/x.json"), {})


class WindowDriftTest(unittest.TestCase):
    """The rolling 30-day window brings a new departure date into view every
    day. Without per-date history, a cheap date appearing looks identical to a
    fare falling — this is the distinction the series exists to draw."""

    def setUp(self):
        self.route = Route("KUL", "UPG", "Makassar")
        self.today = date(2026, 8, 10)
        # Route has looked like ~608 for five days.
        self.history = _route_history("UPG", [608, 608, 608, 608, 608])

    def test_new_date_is_reported_as_cheap_date_not_a_drop(self):
        """A date never seen before cannot be called a price drop."""
        offers = {"KUL-UPG": [_offer("UPG", 400, dep="2026-09-09")]}
        deals, _ = find_deals(offers, self.history, [self.route], _cfg(),
                              self.today, date_series={})
        self.assertEqual(len(deals), 1)
        self.assertFalse(deals[0].is_price_drop)
        self.assertEqual(deals[0].basis, "route")

    def test_same_date_getting_cheaper_is_a_confirmed_drop(self):
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-08")
        series = record_date_prices(series, [_offer("UPG", 608)], "2026-08-09")
        offers = {"KUL-UPG": [_offer("UPG", 469)]}
        deals, _ = find_deals(offers, self.history, [self.route], _cfg(),
                              self.today, series)
        self.assertEqual(len(deals), 1)
        d = deals[0]
        self.assertTrue(d.is_price_drop)
        self.assertEqual(d.basis, "date_drop")
        self.assertEqual(d.previous_price, 608.0)
        self.assertEqual(d.previous_date, "2026-08-09")
        self.assertAlmostEqual(d.discount_pct, (608 - 469) / 608, places=3)

    def test_date_with_history_is_judged_on_its_own_price_not_the_route(self):
        """The key anti-false-alarm case: a date that has always been cheap is
        NOT a deal, even though it sits far below the route's usual cheapest."""
        series = record_date_prices({}, [_offer("UPG", 400)], "2026-08-08")
        series = record_date_prices(series, [_offer("UPG", 398)], "2026-08-09")
        offers = {"KUL-UPG": [_offer("UPG", 399)]}   # unchanged, still cheap
        deals, _ = find_deals(offers, self.history, [self.route], _cfg(),
                              self.today, series)
        self.assertEqual(deals, [],
                         "a persistently cheap date must not alert daily")

    def test_confirmed_drop_beats_a_bigger_cheap_date(self):
        """Trustworthiness wins over headline size when both are available."""
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-08")
        series = record_date_prices(series, [_offer("UPG", 608)], "2026-08-09")
        offers = {"KUL-UPG": [
            _offer("UPG", 469),                        # 23% confirmed drop
            _offer("UPG", 300, dep="2026-09-09"),      # 51% but unseen date
        ]}
        deals, _ = find_deals(offers, self.history, [self.route], _cfg(),
                              self.today, series)
        self.assertEqual(len(deals), 1)
        self.assertTrue(deals[0].is_price_drop)
        self.assertEqual(deals[0].offer.price, 469)

    def test_thin_date_history_falls_back_to_route(self):
        series = record_date_prices({}, [_offer("UPG", 608)], "2026-08-09")
        offers = {"KUL-UPG": [_offer("UPG", 400)]}
        deals, _ = find_deals(offers, self.history, [self.route],
                              _cfg(min_date_samples=3), self.today, series)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].basis, "route")


if __name__ == "__main__":
    unittest.main()
