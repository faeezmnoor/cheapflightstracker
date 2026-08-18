# ✈️ Cheap Flights Tracker

**Finds genuinely underpriced flights out of Kuala Lumpur — not just cheap ones.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![No API key](https://img.shields.io/badge/API%20key-not%20required-brightgreen)

Every morning it prices **26 Indonesian airports** from **KL**, across **every
departure date in the next 30 days**, and emails you the fares that are unusual
*for that route* — not the ones that happen to be low.

It runs on GitHub Actions, reads live fares from Google Flights with **no API key**,
and sends the digest over SMTP. Nothing to host, nothing to pay for.

---

## The problem

"Cheap" is not a useful signal. KL→Medan at MYR 150 is ordinary; KL→Jakarta at
MYR 150 is a genuinely good deal. A single price threshold either floods you with
short-haul noise or hides every real bargain on the longer routes.

So the only question worth asking is whether a fare is cheap **relative to that
route's own history** — which means every route needs its own baseline, and the
baseline has to survive bad data.

## How it decides

Airfare distributions are **right-skewed**: a hard floor at the carrier's base
fare, a long tail of flexible and multi-stop fares, and the occasional scrape that
misses the cheap itineraries and records several times the norm. Mean and standard
deviation are the wrong tools for that shape — one reading at 9,475 inflates the
scale enough to hide every genuine dip afterwards.

So it uses **median and MAD** (median absolute deviation), which an outlier cannot
move, and asks three questions of the route's own history of daily-cheapest fares:

| Question | Measure | Why it matters |
|---|---|---|
| **Is it rare?** | percentile rank — *"only 20% of tracked days were this cheap"* | No distributional assumptions. The honest measure of unusual. |
| **Is it anomalous?** | modified z-score (MAD-based) | Comparable across routes: −3 means the same on a MYR 200 fare and a MYR 2,000 one. |
| **Is it a new low?** | cheaper than anything on record | Strongest signal, and naturally noise-resistant — bad scrapes push prices *up*, so they cannot fake a low. |

A fare qualifies on **any** of those, behind two floors: **≥12% off and ≥MYR 40
saved**. Without them, a route sitting at one price all week scores z = −4.75 on a
dip most travellers would shrug at. **Severe** requires *rare **and** large* — a
big z-score alone is never enough.

## Not saying the same thing twice

Statistics decide whether a fare is *unusual*. They cannot decide whether it is
*news*. A fare that stays cheap stays unusual, and would otherwise be re-sent every
morning until the median caught up with it.

So each alert is recorded, and a route is only mentioned again once the fare drops
a further 5% or a week has passed.

## What you get

> **✈️ 🔥 3 underpriced KL→Indonesia flights (1 severe) — best: KL→Medan 50% off**
>
> - **KL → Medan** — **MYR 89** · 50% off · save MYR 90 *(direct, 12 Sep)*
>   <br><sub>cheapest in 31 days of tracking · only 2% of tracked days were this
>   cheap · 4.1 robust deviations below usual</sub>
> - **KL → Jakarta** — **MYR 247** · 30% off · save MYR 107 *(1 stop)*
> - …plus a cheapest-today table for all 26 routes.

Every city carries a 📍 map link, because an IATA code tells you nothing about
whether a place is a beach or the middle of Kalimantan.

## How it works

```
 GitHub Actions (daily cron)
        │
        ▼
   run.py ──► flightdeals.main.run()
        │
        ├─ search.py       every route × every date in the window
        ├─ baseline.py     route "usual price" + per-departure-date series
        ├─ detector.py     confirmed price drops, then merely cheap dates
        ├─ emailer.py      build + send the HTML/text digest via SMTP
        └─ baseline.py     append today's fares, commit history back to the repo
```

Price history lives in the repo itself, committed by the daily job — no database.
The data source is pluggable: implement `search()` on `FlightProvider` in
[`flightdeals/providers/`](flightdeals/providers/) and select it with `PROVIDER=`.
A `mock` provider ships for offline demos and tests.

## Setup (about 5 minutes)

Because the data source needs no API key, the only thing to configure is email.

1. **Create a Gmail app password** — enable 2-Step Verification, then generate one
   at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
2. **Add repository secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |--------|-------|
   | `SMTP_USER` | the Gmail address the digest is sent *from* |
   | `SMTP_APP_PASSWORD` | the 16-character app password |
   | `EMAIL_TO` | where to send it (defaults to `SMTP_USER`) |

3. **Turn it on** — the workflow runs daily. To test now: Actions → *Daily flight
   deals* → Run workflow (tick *dry_run* to preview without sending).

## Run it locally

```bash
pip install -r requirements.txt

python run.py --provider mock --dry-run   # offline demo, prints the email
python run.py --dry-run                   # real fares, still doesn't send
python -m unittest discover -s tests      # stdlib only, no network
```

## Pointing it somewhere else

Nothing about the machinery is specific to Indonesia — only the default route list.

```bash
ORIGIN=SIN                       # any IATA origin
ROUTES=BKK,HKT,CNX,DMK           # any destinations
CURRENCY=SGD  REGION=sg          # price it in the market you buy from
```

Google prices by market, so `REGION` and `LANGUAGE` make the runner see the fares a
local shopper sees. Every setting is an env var — see [`.env.example`](.env.example).

## Notes

- **Unofficial data source.** Fares come from Google Flights' public web endpoint
  via [`fast-flights`](https://github.com/AWeirdDev/flights). There is no free
  official flight-price API, and this can break if Google changes their page
  format. Intended for personal, low-volume monitoring — please respect Google's
  terms and don't point it at a route list large enough to be a nuisance.
- **Baselines need a few days.** Until a route has 5 days of history it shows
  "building baseline" and won't flag anything, by design.
- **Always confirm before booking.** An alert is a prompt to look, not a quote.

## License

[MIT](LICENSE)
