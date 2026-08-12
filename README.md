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

### How "underpriced" is decided

Airfare distributions are **right-skewed**: a hard floor at the carrier's base
fare, a long tail of flexible and multi-stop fares, and the occasional scrape
that misses the cheap itineraries entirely and records several times the norm.
Mean and standard deviation are the wrong tools for that shape — a single
9,475 reading inflates the scale enough to hide every genuine dip afterwards.

So the service uses **median and MAD** (median absolute deviation), which an
outlier cannot move, and asks three questions of the route's own history of
daily-cheapest fares:

| Question | Measure | Why it matters |
|---|---|---|
| **Is it rare?** | percentile rank — *"only 20% of tracked days were this cheap"* | No distributional assumptions. The honest measure of unusual. |
| **Is it anomalous?** | modified z-score (MAD-based) | Comparable across routes: −3 means the same on a 200 fare and a 2,000 one. |
| **Is it a new low?** | cheaper than anything on record | Strongest signal, and naturally noise-resistant — artifacts push prices *up*, so they cannot fake a low. |

A fare qualifies on **any** of those, or on a plain large discount, always
behind two floors: **≥12% off and ≥MYR 40 saved**. Without them a route sitting
at one fare all week scores z = −4.75 on a dip most travellers would shrug at.

**Severe** requires *rare **and** large* — ≥35% off, or ≥25% off while also
being a new low or in the rare tail. A big z-score alone is never enough.

Only the route's **own cheapest fare** is ever a candidate, so an alert can
never quote a worse price than the table beneath it.

### Not saying the same thing twice

Statistics decide whether a fare is *unusual*; they cannot decide whether it is
*news*. A fare that stays cheap stays unusual, and would be re-sent every
morning until the median caught up with it. `data/alert_state.json` records
what was sent, and a route is only mentioned again once the fare drops a
further `REPEAT_IMPROVEMENT` (5%) or `REPEAT_COOLDOWN_DAYS` (7) have passed.

Every departure date's price is also tracked in
[`data/date_prices.json`](data/date_prices.json), used to annotate an alert
with what that same date previously cost. It is annotation only: roughly 7% of
dates swing more than 2× day to day from scrape noise, which is far too
unreliable to originate an alert.

---

## How it works

```
 GitHub Actions (daily cron)
        │
        ▼
   run.py ──► flightdeals.main.run()
        │
        ├─ search.py       every route x every date in the window
        ├─ baseline.py     route "usual price" + per-departure-date series
        ├─ detector.py     confirmed price drops, then merely cheap dates
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

- **Which cities** — `ROUTES=CGK,DPS,SUB,...`. The default is all **26 airports
  confirmed reachable from KL** by `scripts/probe_destinations.py` (8 direct,
  18 via a connection); airports with no KL service are deliberately excluded.
- **Which dates** — every date in the next `DEPARTURE_WINDOW_DAYS` (default 30)
  is scanned, **exhaustively, not sampled**: Google prices each date
  separately, so a date you don't probe is a price you can't see. Set
  `DEPARTURE_OFFSETS` to override with an explicit list.
- **Point of sale** — `REGION=my`, `LANGUAGE=en`. Google prices by market, so
  these make the runner see the fares a Malaysian shopper sees.
- **One-way vs round-trip** — round trips are **off** by default (a return
  prices as two one-ways). `ROUND_TRIP=true` adds them, on their own
  `ROUND_TRIP_OFFSETS` grid, capped by `MAX_TRIP_DAYS=30`.
- **Sensitivity** — `DEAL_THRESHOLD=0.20`, `SEVERE_THRESHOLD=0.35`.

### Request volume
Google Flights has **no quota**, but it's an unofficial data source, so hammering
it risks being rate-limited/blocked. The defaults make ~**780 requests/day**
(26 routes × 30 dates), paced ~3s apart with jitter. That is hours in one
process, so scanning is split across **4 parallel CI shards** (~15 min wall
clock, and each shard gets its own runner IP, keeping the per-IP rate low).
Watch the run logs: they print the offer count, a sample of any errors, and
which routes came back empty.

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
  *days* of history, it shows "building baseline" and won't flag deals — by
  design, to avoid false alarms on thin data.
- **Always verify before booking.** The email links to Google Flights for each
  deal; treat the alert as a heads-up, not a booking.
- **Swapping providers** is a one-file job — implement `FlightProvider.search`
  in `flightdeals/providers/` and set `PROVIDER=<name>`.
