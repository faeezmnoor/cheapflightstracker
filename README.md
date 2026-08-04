# ✈️ KL → Indonesia flight-deal watcher

An automated daily service that scans flights from **Kuala Lumpur (KUL)** to
**every major city in Indonesia**, learns each route's *usual* price over time,
and **emails you the fares that are underpriced** — highlighting the severely
underpriced ones. One-way **and** round-trip (return within 30 days) are both
covered.

It runs on **GitHub Actions** (free), pulls live fares from **Google Flights**
(via the [`fast-flights`](https://github.com/AWeirdDev/flights) library — **no
API key required**), and emails the digest via **Gmail SMTP**.

---

## What you get

Every morning (09:00 Malaysia time) an email like this:

> **✈️ 🔥 1 severely underpriced + 2 underpriced KL→Indonesia flights — best: KL→KNO 50% off**
>
> - **KL → Medan** — **MYR 89** · 50% off · save MYR 90 · usual ~MYR 179 *(direct)*
> - **KL → Jakarta** — **MYR 247** · 30% off · save MYR 107 *(1 stop)*
> - …plus a **cheapest-today table** for every route.

Deals are found by comparing today's cheapest fare against the **median of that
route's recently-observed fares**. A fare ≥20% below usual is a **deal**; ≥35%
below is **severely underpriced**. The baseline lives in
[`data/price_history.json`](data/price_history.json) and is committed back after
each run, so it gets smarter every day.

---

## How it works

```
 GitHub Actions (daily cron)
        │
        ▼
   run.py ──► flightdeals.main.run()
        │
        ├─ search.py       plan date combos, query Google Flights per route
        ├─ baseline.py     load history, compute each route's "usual price"
        ├─ detector.py     flag fares that beat usual by the threshold
        ├─ emailer.py      build + send the HTML/text digest via Gmail SMTP
        └─ baseline.py     append today's fares, commit history back to the repo
```

| File | Responsibility |
|------|----------------|
| `flightdeals/config.py`   | All settings, read from env vars |
| `flightdeals/providers/`  | Pluggable data sources — `googleflights` (live) and `mock` (offline demo/tests) |
| `flightdeals/search.py`   | Which routes × dates to probe |
| `flightdeals/baseline.py` | Price-history storage + "usual price" stats |
| `flightdeals/detector.py` | Deal / severe-deal classification |
| `flightdeals/emailer.py`  | Email composition + SMTP send |
| `flightdeals/main.py`     | Orchestration + CLI |
| `.github/workflows/daily-flight-alerts.yml` | The daily schedule |

---

## Setup (about 5 minutes — only email credentials needed)

Because the data source needs **no API key**, the only thing to configure is how
the email is sent.

### 1. Create a Gmail app password
1. Enable 2-Step Verification on your Google account.
2. Go to **https://myaccount.google.com/apppasswords** and generate a
   16-character app password (name it e.g. "flight deals").

### 2. Add the secrets to GitHub
In this repo: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `SMTP_USER` | `faeezmnoor@gmail.com` |
| `SMTP_APP_PASSWORD` | the 16-char Gmail app password (no spaces) |
| `EMAIL_TO` | where to send the digest (defaults to `SMTP_USER`) |

*(Optional)* tune behaviour without touching code via **Variables** (same page):
`ROUTES`, `DEPARTURE_OFFSETS`, `ROUND_TRIP`, `STAY_LENGTHS`, `DEAL_THRESHOLD`,
`SEVERE_THRESHOLD`, `MIN_SAMPLES`, `CURRENCY`.

### 3. Turn it on
The workflow runs automatically every day. To test it immediately:
**Actions → "Daily flight deals (KL → Indonesia)" → Run workflow**
(tick *dry_run* to preview without emailing / without committing history).

---

## Run it locally

```bash
pip install -r requirements.txt

# Offline demo — no network needed, prints the email it would send:
python run.py --provider mock --dry-run

# Real run against Google Flights (prints, doesn't send):
python run.py --dry-run

# Real run that sends the email (load your .env first):
cp .env.example .env      # then fill in your Gmail app password
set -a; source .env; set +a
python run.py
```

Run the tests (they use the mock provider — no network):

```bash
python -m unittest discover -s tests -v
```

---

## Tuning

Everything is an env var (see [`.env.example`](.env.example)). The most useful:

- **Which cities** — `ROUTES=CGK,DPS,SUB,...` (default is the 10 busiest; the
  full list of 15 is in `config.py`).
- **Which dates** — `DEPARTURE_OFFSETS=14,35` (days from today; default). Add
  more like `14,30,45,60` to probe further out.
- **One-way vs round-trip** — `ROUND_TRIP=true`, `STAY_LENGTHS=14`,
  `MAX_TRIP_DAYS=30`.
- **Sensitivity** — `DEAL_THRESHOLD=0.20`, `SEVERE_THRESHOLD=0.35`.

### Request volume
Google Flights has **no quota**, but it's an unofficial data source, so hammering
it risks being rate-limited/blocked. The defaults make ~**40 requests/day**
(10 routes × 2 departure dates × [one-way + round-trip]), spaced out by a short
pause. Widen gradually and watch the run logs (they print how many offers came
back) before scaling up.

---

## Notes & limitations

- **Unofficial data source.** `fast-flights` reads Google Flights' internal
  endpoint; there's no official free flight API. It works well but can break if
  Google changes their page format — pin/upgrade the version in
  `requirements.txt` if a run suddenly returns nothing. Using it for personal,
  low-volume monitoring is the intended use; respect Google's terms.
- **Datacenter IPs can occasionally be throttled.** If a run logs lots of
  "search error(s)" or zero offers across every route, Google likely rate
  -limited the GitHub runner. The service fails soft (records the error, still
  emails what it has) and usually recovers next run. You can set an `FF_PROXY`
  env var to route the fetcher through a proxy if this becomes persistent.
- **Baseline needs a few days.** Until a route has `MIN_SAMPLES` (default 5)
  observations, it shows "building baseline" and won't flag deals — by design,
  to avoid false alarms on thin data.
- **Always verify before booking.** The email links to Google Flights for each
  deal; treat the alert as a heads-up, not a booking.
- **Swapping providers** is a one-file job — implement `FlightProvider.search`
  in `flightdeals/providers/` and set `PROVIDER=<name>`.
