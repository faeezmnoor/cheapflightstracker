"""Proof that the auditor catches the bugs that actually shipped.

An untested checker is just more code that can be silently wrong — which is
the exact failure mode this package exists to stop. So every check is
exercised by reconstructing the incident that motivated it and asserting the
auditor blocks, plus one clean digest that must pass everything, because a
checker that cries wolf gets switched off within a week.
"""

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qa.checks import audit
from qa.findings import BLOCK

RUN_DATE = "2026-08-13"


def days_before(n: int, run_date: str = RUN_DATE) -> str:
    return (date.fromisoformat(run_date) - timedelta(days=n)).isoformat()


def obs(route_key: str, day: str, price: float, trip_type: str = "one_way",
        departure_date: str = "2026-09-01") -> dict:
    origin, destination = route_key.split("-")
    return {"origin": origin, "destination": destination, "observed_date": day,
            "price": price, "trip_type": trip_type, "currency": "MYR",
            "departure_date": departure_date}


def history_for(route_key: str, prices, trip_type: str = "one_way") -> list:
    """One observation per day, most recent last, ending yesterday."""
    return [obs(route_key, days_before(len(prices) - i), p, trip_type)
            for i, p in enumerate(prices)]


def summary(route_key: str, price, city="Somewhere", median=None,
            trip_type="one_way", currency="MYR") -> dict:
    return {"route_key": route_key, "city": city, "price": price,
            "currency": currency if price is not None else None,
            "trip_type": trip_type if price is not None else None,
            "departure_date": "2026-09-01", "median": median, "samples": 7,
            "baseline_trusted": median is not None, "discount_pct": None,
            "maps_url": "https://www.google.com/maps/search/?api=1&query=x"}


def deal(route_key: str, price, median, samples=7, city="Somewhere",
         trip_type="one_way", currency="MYR", is_new_low=False,
         percentile=0.1, saving=None, discount=None) -> dict:
    saving = (median - price) if saving is None else saving
    discount = (saving / median) if discount is None else discount
    return {"route_key": route_key, "city": city, "price": price,
            "currency": currency, "trip_type": trip_type,
            "departure_date": "2026-09-01", "return_date": None,
            "severity": "deal", "basis": "route", "discount_pct": discount,
            "saving": saving, "median": median, "samples": samples,
            "baseline_trip_type": trip_type, "z_score": -2.5,
            "percentile": percentile, "is_new_low": is_new_low,
            "maps_url": "https://www.google.com/maps/search/?api=1&query=x"}


def digest(deals, summaries, **overrides) -> dict:
    payload = {"run_date": RUN_DATE, "currency": "MYR", "offers_checked": 3000,
               "scanned_departures": [days_before(-n) for n in range(1, 31)],
               "errors": [], "min_samples": 5, "departure_window_days": 30,
               "deals": deals, "summaries": summaries}
    payload.update(overrides)
    return payload


def blocking_checks(report) -> set:
    return {f.check for f in report.findings if f.severity == BLOCK}


class CleanDigestTest(unittest.TestCase):
    """The false-positive guard. If this ever fails, the suite is useless —
    an auditor that blocks good digests will be disabled, not debugged."""

    def test_a_correct_digest_passes_every_check(self):
        # A low outlier already on record, so today's 360 is cheap but not a
        # new low — the ordinary shape of a genuine deal.
        history = (history_for("KUL-CGK", [340, 410, 395, 405, 400, 398, 402])
                   + history_for("KUL-DPS", [300, 310, 305, 300, 302, 298, 301]))
        d = digest(
            [deal("KUL-CGK", 360.0, 400.0, samples=7, percentile=1 / 7)],
            [summary("KUL-CGK", 360.0, median=400.0),
             summary("KUL-DPS", 299.0, median=301.0)])
        html = ("maps/search " * 3) + "360.00 "
        report = audit(d, history, html)
        self.assertTrue(report.ok, report.render())


class IndependenceTest(unittest.TestCase):
    """The auditor's whole value is that it does not share code with the thing
    it audits. That property is one tidy-up commit away from being lost, and
    losing it is invisible — the tests would still pass, which is exactly the
    failure mode this package exists to catch. So it is asserted."""

    def test_qa_package_does_not_import_the_code_it_audits(self):
        import pathlib
        qa_dir = pathlib.Path(__file__).resolve().parent.parent / "qa"
        offenders = []
        for path in sorted(qa_dir.glob("*.py")):
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if not stripped.startswith(("import ", "from ")):
                    continue
                if "flightdeals" in stripped:
                    offenders.append(f"{path.name}:{number}: {stripped}")
        self.assertEqual(
            offenders, [],
            "qa/ must re-derive its own numbers, never import flightdeals — "
            "see CLAUDE.md")


class DryRunTest(unittest.TestCase):
    """A preview must not change the thing it previews.

    `--dry-run` used to persist anyway, so `run.py --provider mock --dry-run`
    wrote invented fares into the real price history — poisoning the baselines
    every future alert is judged against, from the one command documented as
    safe to run whenever you like.
    """

    def test_dry_run_leaves_every_data_file_untouched(self):
        import json
        import tempfile
        from datetime import date as _date

        from flightdeals.config import Config, Route
        from flightdeals.main import report
        from flightdeals.models import Offer

        with tempfile.TemporaryDirectory() as tmp:
            paths = {name: os.path.join(tmp, f"{name}.json")
                     for name in ("history", "series", "alerts")}
            sentinel = {"observations": [], "count": 0, "schema_version": 1}
            for path in paths.values():
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(sentinel, fh)
            before = {p: open(p, encoding="utf-8").read() for p in paths.values()}

            config = Config(
                routes=[Route("KUL", "CGK", "Jakarta")], provider="mock",
                dry_run=True, digest_artifact_path="",
                history_path=paths["history"],
                date_history_path=paths["series"],
                alert_state_path=paths["alerts"])
            offer = Offer("KUL", "CGK", "2026-09-01", 300.0, "MYR", "one_way")
            report(config, _date.fromisoformat(RUN_DATE), {"KUL-CGK": [offer]},
                   [], ["2026-09-01"], 1)

            for path, original in before.items():
                self.assertEqual(open(path, encoding="utf-8").read(), original,
                                 f"dry run modified {os.path.basename(path)}")


class DigestCheckTest(unittest.TestCase):
    def test_c1_alert_may_not_beat_the_table(self):
        """12 Aug: an alert quoted 309 while the table showed 279 for the same
        route, because the detector chose by discount instead of by price."""
        history = history_for("KUL-PNK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([deal("KUL-PNK", 309.0, 401.0)],
                   [summary("KUL-PNK", 279.0, median=401.0)])
        self.assertIn("C1", blocking_checks(audit(d, history)))

    def test_c2_most_routes_alerting_is_a_bug_not_a_sale(self):
        """12 Aug: 21 of 26 routes alerted in one morning."""
        routes = [f"KUL-R{i:02d}" for i in range(26)]
        history = [o for r in routes
                   for o in history_for(r, [400, 410, 395, 405, 400, 398, 402])]
        d = digest([deal(r, 300.0, 401.0) for r in routes[:21]],
                   [summary(r, 300.0, median=401.0) for r in routes])
        self.assertIn("C2", blocking_checks(audit(d, history)))

    def test_c3_one_observation_is_not_a_baseline(self):
        """12 Aug: a lone 2,110 reading produced an '85% off' alert."""
        history = history_for("KUL-BTH", [2110.0])
        d = digest([deal("KUL-BTH", 316.0, 2110.0, samples=1)],
                   [summary("KUL-BTH", 316.0, median=2110.0)])
        self.assertIn("C3", blocking_checks(audit(d, history)))

    def test_c4_numbers_in_the_email_must_agree(self):
        history = history_for("KUL-CGK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([deal("KUL-CGK", 300.0, 401.0, saving=250.0)],
                   [summary("KUL-CGK", 300.0, median=401.0)])
        self.assertIn("C4", blocking_checks(audit(d, history)))

    def test_c5_catches_trip_type_pooling(self):
        """A shared one-way/round-trip baseline sits between the two, making
        every one-way look about half price."""
        history = (history_for("KUL-UPG", [400, 410, 395, 405, 400, 398, 402])
                   + history_for("KUL-UPG", [900, 910, 890, 905, 900, 895, 902],
                                 trip_type="round_trip"))
        # The pooled median of both populations is ~650; the truth for one-way
        # fares is ~400, so a "38% off" alert is really an ordinary fare.
        d = digest([deal("KUL-UPG", 400.0, 650.0)],
                   [summary("KUL-UPG", 400.0, median=650.0)])
        self.assertIn("C5", blocking_checks(audit(d, history)))

    def test_c5_catches_baseline_built_from_every_offer(self):
        """Averaging all offers rather than each day's cheapest drags the
        baseline upward and makes ordinary fares look underpriced."""
        history = []
        for i, cheapest in enumerate([400, 410, 395, 405, 400, 398, 402]):
            day = days_before(7 - i)
            # Each day also has worse offers, as a real scrape returns.
            for price in (cheapest, cheapest + 200, cheapest + 500):
                history.append(obs("KUL-CGK", day, price))
        d = digest([deal("KUL-CGK", 380.0, 633.0)],     # median of ALL offers
                   [summary("KUL-CGK", 380.0, median=633.0)])
        self.assertIn("C5", blocking_checks(audit(d, history)))

    def test_c5_catches_a_new_low_that_is_not_one(self):
        history = history_for("KUL-DPS", [300, 250, 310, 305, 300, 298, 301])
        d = digest([deal("KUL-DPS", 280.0, 301.0, is_new_low=True)],
                   [summary("KUL-DPS", 280.0, median=301.0)])
        self.assertIn("C5", blocking_checks(audit(d, history)))

    def test_c6_currencies_must_not_mix(self):
        history = history_for("KUL-CGK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([deal("KUL-CGK", 300.0, 401.0)],
                   [summary("KUL-CGK", 300.0, median=401.0, currency="USD")])
        self.assertIn("C6", blocking_checks(audit(d, history)))

    def test_c7_notices_map_links_that_never_rendered(self):
        """12 Aug: two edits meant to add map links matched nothing and were
        silently skipped. Tests passed; the links were simply absent."""
        history = history_for("KUL-CGK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([deal("KUL-CGK", 300.0, 401.0)],
                   [summary("KUL-CGK", 300.0, median=401.0),
                    summary("KUL-DPS", 250.0, median=260.0)])
        report = audit(d, history, html="<html>300.00 no links here</html>")
        self.assertIn("C7", {f.check for f in report.findings})


class DataCheckTest(unittest.TestCase):
    def test_d1_notices_a_missed_run(self):
        """13 Aug: renaming the default branch dropped the cron. No run fired
        and nothing complained until a human noticed the silence."""
        history = [obs("KUL-CGK", days_before(4), 400.0)]
        report = audit(digest([], [summary("KUL-CGK", 390.0, median=400.0)]),
                       history)
        self.assertIn("D1", {f.check for f in report.findings})

    def test_d2_notices_a_hole_in_the_window(self):
        history = ([obs("KUL-CGK", days_before(n), 400.0) for n in (1, 2, 5, 6)])
        report = audit(digest([], [summary("KUL-CGK", 390.0, median=400.0)]),
                       history)
        self.assertIn("D2", {f.check for f in report.findings})

    def test_d3_notices_a_permanently_empty_route(self):
        """Yogyakarta was configured as JOG, a domestic-only airport, so the
        route returned nothing every day without ever erroring."""
        history = history_for("KUL-CGK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([], [summary("KUL-CGK", 390.0, median=400.0),
                        summary("KUL-JOG", None, city="Yogyakarta")])
        report = audit(d, history)
        self.assertIn("D3", {f.check for f in report.findings})

    def test_d4_notices_a_sampled_window(self):
        """Early Aug: only two departure dates per route were probed, so a
        cheaper date simply could not be seen."""
        history = history_for("KUL-CGK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([], [summary("KUL-CGK", 390.0, median=400.0)],
                   scanned_departures=["2026-08-20", "2026-09-01"])
        report = audit(d, history)
        self.assertIn("D4", {f.check for f in report.findings})

    def test_d6_notices_a_provider_outage(self):
        """The near miss: if the scraper breaks, every route comes back empty,
        the digest sends a hollow table, and nothing else fires — the alerts
        are absent rather than wrong."""
        routes = [f"KUL-R{i:02d}" for i in range(10)]
        history = [o for r in routes
                   for o in history_for(r, [400, 410, 395, 405, 400, 398, 402])]
        d = digest([], [summary(r, None) for r in routes[:8]]
                   + [summary(r, 390.0, median=400.0) for r in routes[8:]])
        report = audit(d, history)
        self.assertIn("D6", {f.check for f in report.findings})

    def test_d5_surfaces_implausible_overnight_moves(self):
        history = history_for("KUL-CGK", [400, 410, 395, 405, 400, 398, 402])
        d = digest([], [summary("KUL-CGK", 2400.0, median=400.0)])
        report = audit(d, history)
        self.assertIn("D5", {f.check for f in report.findings})


class GateBehaviourTest(unittest.TestCase):
    """The gate must degrade loudly: suppress the alerts, keep the table, and
    say so. A silently shorter email is indistinguishable from a quiet day."""

    def test_blocking_findings_withhold_alerts_and_announce_it(self):
        from flightdeals.config import Config
        from flightdeals.emailer import build_html, build_subject, build_text
        from flightdeals.main import _qa_gate
        from flightdeals.models import Baseline, Deal, Offer, RouteSummary, RunResult

        offer = Offer("KUL", "BTH", "2026-09-01", 316.0, "MYR", "one_way")
        base = Baseline("KUL-BTH", 1, median=2110.0)
        result = RunResult(
            RUN_DATE, "MYR",
            [Deal(offer=offer, baseline=base, discount_pct=0.85,
                  saving=1794.0, severity="severe", city="Batam")],
            [RouteSummary("KUL-BTH", "Batam", offer, base, 0.85,
                          baseline_trusted=True)],
            100, [])

        config = Config(digest_artifact_path="")     # don't write files in tests
        _qa_gate(result, history_for("KUL-BTH", [2110.0]), config)

        self.assertEqual(result.deals, [], "one-sample alert must be withheld")
        self.assertTrue(result.qa_withheld)
        self.assertIn("withheld", build_subject(result).lower())
        self.assertIn("Alerts withheld by QA", build_html(result))
        self.assertIn("WITHHELD", build_text(result))
        # the useful half of the email survives
        self.assertIn("Batam", build_html(result))

    def test_a_sound_digest_passes_the_gate_untouched(self):
        from flightdeals.config import Config
        from flightdeals.main import _qa_gate
        from flightdeals.models import Baseline, Deal, Offer, RouteSummary, RunResult

        offer = Offer("KUL", "CGK", "2026-09-01", 360.0, "MYR", "one_way")
        base = Baseline("KUL-CGK", 7, median=400.0)
        deal_ = Deal(offer=offer, baseline=base, discount_pct=0.1,
                     saving=40.0, severity="deal", city="Jakarta",
                     percentile=1 / 7, maps_url="https://maps/search?q=1")
        result = RunResult(
            RUN_DATE, "MYR", [deal_],
            [RouteSummary("KUL-CGK", "Jakarta", offer, base, 0.1,
                          baseline_trusted=True,
                          maps_url="https://maps/search?q=1")],
            100, [], scanned_departures=[days_before(-n) for n in range(1, 31)])

        config = Config(digest_artifact_path="")
        _qa_gate(result, history_for("KUL-CGK", [340, 410, 395, 405, 400, 398, 402]),
                 config)
        self.assertEqual(len(result.deals), 1)
        self.assertEqual(result.qa_withheld, [])


if __name__ == "__main__":
    unittest.main()
