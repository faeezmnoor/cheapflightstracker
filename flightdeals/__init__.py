"""Murah — statistical fare-anomaly alerts.

Scans an origin against a list of destinations across every departure date in
a rolling window, and reports only the fares that are unusual against each
route's own price history. Defaults target KL -> Indonesia; set ORIGIN and
ROUTES to point it anywhere else.
"""

__version__ = "1.0.0"
