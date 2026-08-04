import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flightdeals.config import Config, Route
from flightdeals.detector import find_deals
from flightdeals.emailer import build_html, build_subject, build_text
from flightdeals.models import Baseline, Deal, Offer, RouteSummary, RunResult
from flightdeals.providers.mock import MockProvider
from flightdeals.search import plan_date_pairs, run_searches


class SearchPlanTest(unittest.TestCase):
    def test_oneway_only(self):
        c = Config(departure_offsets=[10, 20], round_trip=False)
        pairs = plan_date_pairs(c, date(2026, 8, 1))
        self.assertEqual(pairs, [("2026-08-11", None), ("2026-08-21", None)])

    def test_round_trip_within_window(self):
        c = Config(departure_offsets=[10], round_trip=True,
                   stay_lengths=[7, 40], max_trip_days=30)
        pairs = plan_date_pairs(c, date(2026, 8, 1))
        # stay of 40 is dropped (> max_trip_days); 7 kept
        self.assertIn(("2026-08-11", None), pairs)
        self.assertIn(("2026-08-11", "2026-08-18"), pairs)
        self.assertNotIn(("2026-08-11", "2026-09-20"), pairs)

    def test_run_searches_with_mock(self):
        routes = [Route("KUL", "CGK", "Jakarta")]
        c = Config(routes=routes, provider="mock", round_trip=False,
                   departure_offsets=[14], request_pause_seconds=0.0)
        offers, errors = run_searches(MockProvider(c), c, date(2026, 8, 1))
        self.assertEqual(errors, [])
        self.assertGreater(len(offers["KUL-CGK"]), 0)
        self.assertTrue(all(o.price > 0 for o in offers["KUL-CGK"]))


class EmailTest(unittest.TestCase):
    def _result(self, with_deals=True):
        offer = Offer("KUL", "DPS", "2026-09-01", 200.0, "MYR", "one_way",
                      airline="AK", stops=0,
                      deep_link="https://example.com/x")
        baseline = Baseline("KUL-DPS", 10, median=400.0, mean=410.0,
                            p25=350.0, minimum=200.0, maximum=600.0)
        deals = []
        if with_deals:
            deals = [Deal(offer=offer, baseline=baseline,
                          discount_pct=0.5, saving=200.0, severity="severe")]
        summaries = [RouteSummary("KUL-DPS", "Bali", offer, baseline, 0.5)]
        return RunResult("2026-08-04", "MYR", deals, summaries, 42, [])

    def test_subject_with_deals(self):
        subj = build_subject(self._result(True))
        self.assertIn("DPS", subj)
        self.assertIn("off", subj)

    def test_subject_no_deals(self):
        subj = build_subject(self._result(False))
        self.assertIn("No", subj)

    def test_text_body_contains_key_numbers(self):
        text = build_text(self._result(True))
        self.assertIn("MYR 200", text)
        self.assertIn("DPS", text)
        self.assertIn("SEVERE", text)

    def test_html_is_wellformed_ish(self):
        html = build_html(self._result(True))
        self.assertIn("<html>", html)
        self.assertIn("</html>", html)
        self.assertIn("KL &rarr; DPS", html)
        self.assertIn("SEVERELY UNDERPRICED", html)

    def test_html_handles_no_deals(self):
        html = build_html(self._result(False))
        self.assertIn("No underpriced flights today", html)


class EndToEndMockTest(unittest.TestCase):
    def test_full_pipeline_runs(self):
        routes = [Route("KUL", "CGK", "Jakarta"), Route("KUL", "DPS", "Bali")]
        c = Config(routes=routes, provider="mock", round_trip=False,
                   departure_offsets=[14, 30], request_pause_seconds=0.0,
                   min_samples=1)
        today = date(2026, 8, 1)
        offers, _ = run_searches(MockProvider(c), c, today)
        # seed a baseline so detection has something to compare against
        history = []
        for rk, offs in offers.items():
            for o in offs:
                r = o.to_record()
                r["observed_date"] = "2026-07-15"
                r["price"] = 500  # pretend usual was pricey
                history.append(r)
        deals, summaries = find_deals(offers, history, routes, c, today)
        self.assertEqual(len(summaries), 2)
        # with a 500 baseline and mock fares well under that, expect deals
        self.assertGreater(len(deals), 0)


if __name__ == "__main__":
    unittest.main()
