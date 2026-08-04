import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config, Route
from flightdeals.detector import find_deals
from flightdeals.models import Offer


def _cfg(**kw):
    c = Config()
    c.deal_threshold = 0.20
    c.severe_threshold = 0.35
    c.min_samples = 5
    c.history_window_days = 90
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _history(dest, prices, observed="2026-08-01"):
    recs = []
    for p in prices:
        recs.append({
            "origin": "KUL", "destination": dest, "departure_date": "2026-09-01",
            "price": p, "currency": "MYR", "trip_type": "one_way",
            "observed_date": observed,
        })
    return recs


def _offer(dest, price):
    return Offer(origin="KUL", destination=dest, departure_date="2026-09-10",
                 price=price, currency="MYR", trip_type="one_way")


class DetectorTest(unittest.TestCase):
    def setUp(self):
        self.route = Route("KUL", "CGK", "Jakarta")
        self.today = date(2026, 8, 2)

    def test_no_deal_when_price_is_normal(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 290)]}
        deals, summaries = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].cheapest.price, 290)

    def test_flags_a_deal(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 220)]}  # ~27% off
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].severity, "deal")
        self.assertAlmostEqual(deals[0].discount_pct, (300 - 220) / 300, places=3)
        self.assertEqual(deals[0].saving, 80)

    def test_flags_severe(self):
        hist = _history("CGK", [400, 400, 400, 400, 400])
        offers = {"KUL-CGK": [_offer("CGK", 200)]}  # 50% off
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].severity, "severe")

    def test_thin_history_never_flags(self):
        hist = _history("CGK", [300, 300])  # only 2 < min_samples
        offers = {"KUL-CGK": [_offer("CGK", 50)]}
        deals, summaries = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])
        # baseline not reliable enough -> no discount reported in summary
        self.assertIsNone(summaries[0].discount_pct)

    def test_one_deal_per_route(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        offers = {"KUL-CGK": [_offer("CGK", 100), _offer("CGK", 150)]}
        deals, _ = find_deals(offers, hist, [self.route], _cfg(), self.today)
        self.assertEqual(len(deals), 1)
        self.assertEqual(deals[0].offer.price, 100)  # cheapest wins

    def test_no_offers_route_summary(self):
        hist = _history("CGK", [300, 300, 300, 300, 300])
        deals, summaries = find_deals({"KUL-CGK": []}, hist, [self.route], _cfg(), self.today)
        self.assertEqual(deals, [])
        self.assertIsNone(summaries[0].cheapest)

    def test_deals_sorted_by_discount(self):
        routes = [Route("KUL", "CGK", "Jakarta"), Route("KUL", "DPS", "Bali")]
        hist = _history("CGK", [300] * 5) + _history("DPS", [400] * 5)
        offers = {
            "KUL-CGK": [_offer("CGK", 230)],   # ~23% off
            "KUL-DPS": [_offer("DPS", 200)],   # 50% off
        }
        deals, _ = find_deals(offers, hist, routes, _cfg(), self.today)
        self.assertEqual(len(deals), 2)
        self.assertGreater(deals[0].discount_pct, deals[1].discount_pct)
        self.assertEqual(deals[0].offer.destination, "DPS")


if __name__ == "__main__":
    unittest.main()
