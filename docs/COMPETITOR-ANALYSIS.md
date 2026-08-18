# How the industry finds cheap flights, and which of it applies here

A survey of the techniques used by Skiplagged, Kiwi, Going, Secret Flying,
Jack's Flight Club, Google Flights and others — and an explicit decision on
each, tested against this project's own recorded data wherever that was
possible.

The bias throughout: **this is a personal tool for one traveller flying
KL→Indonesia, mostly on low-cost carriers, over short sectors.** A technique
that transforms transatlantic premium-cabin pricing may be worth nothing here,
and several are.

---

## Summary of decisions

| Technique | Who uses it | Verdict |
|---|---|---|
| **Longer booking horizon** | Going, Jack's Flight Club, every fare-trend study | **Adopt** — our single biggest miss |
| Price-position context ("low/typical/high") | Google Flights | **Already have it** (percentile + z-score) |
| Exhaustive date scanning | Skyscanner, Google date grid | **Already have it** |
| Error/mistake-fare hunting | Secret Flying, Going, Fly4Free | **Partially have it** — see below |
| Nearby / alternate airports | Google multi-airport search | **Already evaluated and rejected on evidence** |
| Day-of-week optimisation | Expedia Air Hacks, KAYAK, endless blogs | **Reject — measured at 1.8% on our routes** |
| Point-of-sale / VPN arbitrage | "travel hacking" blogs | **Reject — myth for LCCs, and we already set the market** |
| Hidden-city / skiplagging | Skiplagged | **Reject — legal and account risk, negligible upside here** |
| Virtual interlining / self-transfer | Kiwi.com | **Defer — needs a second data source** |
| Round-trip vs two one-ways | all OTAs | **Untested — worth one experiment** |
| Award/points availability | Thrifty Traveler, Point.me | **Out of scope** |

---

## 1. Booking horizon — the biggest finding

Every fare-trend study puts the sweet spot for **Southeast Asia at 3 to 6
months** before departure. Going puts international generally at 2–8 months.

**We scan the next 30 days. That is the wrong end of the curve**, and it is not
a small effect. Bucketing every per-date price we have recorded, normalised
against each route's own median:

| Days before departure | Relative price |
|---|---|
| 1–5 | **1.077** |
| 6–10 | 1.014 |
| 11–15 | 1.040 |
| 16–20 | 1.000 |
| 21–25 | **0.937** |
| 26–30 | 0.972 |

Two things follow. Fares 3–4 weeks out are ~10% below fares booked within the
week — and **the curve has not clearly bottomed by day 30, which is exactly
where we stop looking.** We have no data whatsoever on days 31–180 because we
have never probed them.

The other half of the argument is promotional. AirAsia — the dominant carrier
on almost every route we track — runs "BIG SALE" / "FREE SEATS" campaigns a few
times a year, and those sales sell travel **6 to 12 months out**. A 30-day
window cannot see a single one of them, ever. The best fares on these exact
routes are structurally invisible to this service.

**Decision: adopt.** Implemented as a *separate* slow lane rather than by
widening the daily window — see "How it is built" below.

## 2. Price-position context — already solved

Google Flights labels a fare low/typical/high against recent prices on that
route. This is the same job our percentile rank and modified z-score do, and
ours is arguably stricter: Google's band is opaque, while the digest states
"only 1% of tracked days were this cheap" and "5.1 robust deviations below
usual" and can be audited against raw history.

**No change.**

## 3. Error and mistake fares

Secret Flying, Fly4Free and The Flight Deal are largely **community-submission**
aggregators; Going does active monitoring. The published advice is that mistake
fares last hours, so automation beats watching.

We already have the detection half — a genuine new low with a large discount is
exactly what a mistake fare looks like in our statistics. What we lack is
**latency**: one scan a day, and an email that arrives ~09:00 MYT. A fare that
appears at 10:00 and dies by 14:00 is invisible to us.

**Decision: no change now.** Closing the latency gap means scanning several
times a day, and we are currently *throttled* — coverage has fallen to 67% at
one scan a day. Adding frequency would make the core product worse to chase a
rare event. Revisit if coverage recovers.

## 4. Nearby and alternate airports

Google's multi-airport search is genuinely powerful — up to seven airports a
side. For us it is already closed: `scripts/probe_destinations.py` tested 58
candidates including **Jakarta Halim (HLP)** as an alternative to CGK, and the
26 that survived are the ones with real KL service. There is no second Bali
airport, no second Surabaya.

On the origin side, Subang (SZB) carries turboprops and almost no international
service; positioning via Singapore is a different trip, not a cheaper fare.

**No change. This was already done properly.**

## 5. Day-of-week — a myth on these routes

Expedia's Air Hacks Report claims flying Friday instead of Sunday saves up to
8%; "fly Tuesday" is the oldest advice in the category. Measured on our own
data, by departure weekday, normalised per route:

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|
| 1.000 | 1.000 | 0.983 | 1.000 | 1.000 | 1.000 | 1.000 |

**A 1.8% spread, with six of seven days identical to three decimal places.**
That is what flat low-cost-carrier pricing looks like: AirAsia and Batik do not
run the revenue-management surfaces that make weekday effects appear on legacy
long-haul.

**Decision: reject, and record it** — so that nobody later "improves" the
service by weighting weekdays, on advice that is true elsewhere and false here.

## 6. Point-of-sale and VPN arbitrage

The 2026 testing consensus is that this is mostly folklore: one study found
geo-IP price variance on only 4 of 18 airlines, and **low-cost carriers
specifically use flat, non-regionalised pricing** because they monetise
ancillaries rather than currency segmentation. IP is also the weakest of the
signals airlines fingerprint.

We already pass `gl=my`, `hl=en`, `curr=MYR`, which is the part that genuinely
matters — asking for the Malaysian market rather than whatever market the CI
runner's IP suggests.

**Decision: reject.** Nothing to gain, and rotating point-of-sale would corrupt
the baselines, which assume one market.

## 7. Hidden-city ticketing (Skiplagged)

You buy A→B→C and get off at B, because the connecting fare undercuts the
direct fare to B. Real savings — commonly cited at 40–60%.

**Decision: reject, firmly.** The reasons compound:

- It breaches the contract of carriage of essentially every major airline.
  Skiplagged itself lost a **$9.4M judgment** in October 2024, and airlines now
  run automated detection against no-show patterns.
- Enforcement lands on the *passenger*: forfeited miles, lost elite status,
  closed accounts, or being billed the higher direct fare. Skiplagged has
  acknowledged hundreds of its own customers being made to pay the difference.
- It requires carry-on only and one-way tickets.
- **The upside here is close to zero anyway.** Hidden-city arbitrage needs a hub
  structure where the through fare is cheaper than the local fare. KL→Indonesia
  is short-haul point-to-point on carriers that price each sector directly.

Recommending this to a real traveller with an AirAsia account, to save perhaps
nothing on a 2-hour flight, is a bad trade.

## 8. Virtual interlining (Kiwi.com)

Kiwi stitches unconnected carriers into one itinerary — reportedly 15–40%
cheaper on unconventional routes. The cost is that the traveller owns the
connection risk: miss it and neither airline is responsible.

Relevant in principle for the awkward routes we already carry (Ambon, Sorong,
Kendari are all 1–2 stops). But it needs a second data source, and a fare we
cannot verify is a fare we should not alert on.

**Decision: defer.** Recorded as a possible second provider, not built.

## 9. Round-trip versus two one-ways

`ROUND_TRIP` is off, on the reasoning that a return prices as two one-ways.
That is usually true on low-cost carriers and often false on full-service ones,
and **we have no data either way** because we have never scanned returns.

**Decision: worth one bounded experiment**, not a standing doubling of the
request budget. Not now — we are throttled.

## 10. Award availability and points

Thrifty Traveler and Point.me cover award space alongside cash. Genuinely
valuable, and entirely out of scope: no free API, and the user is buying cash
tickets.

**Out of scope.**

---

## How the horizon lane is built

The obvious implementation — widen `DEPARTURE_WINDOW_DAYS` from 30 to 180 —
is wrong twice over.

1. It would multiply the daily request budget sixfold, **while we are already
   being throttled** at 67% coverage. The core product would degrade to chase
   an improvement.
2. It would break the invariant that the scanned window is covered
   *exhaustively*. Sampling 180 days would make "cheapest" a claim we could not
   support, which is the defect recorded as incident 3.

So the far horizon is a **separate lane** with different rules, and the digest
never mixes the two:

| | Near window | Far horizon |
|---|---|---|
| Range | next 30 days | two 30-day blocks, 3 and 5 months out |
| Coverage | every date, exhaustive | **every date, exhaustive** |
| Frequency | daily | weekly |
| Baseline | route history | **none — compared against the near window** |
| Claim | "cheapest in the next 30 days" | "cheaper to *fly* then" |

The first version of this lane sampled every 15th day, and that was wrong. On
our own recorded data, taking 10 of 30 dates **misses the true cheapest fare
41% of the time and reads a mean 13.9% high** — the same magnitude as the 15%
discount it was built to detect, so bias and signal cancelled. Sparse probes
also land on peak dates by luck: 3 of the original 10 fell in Christmas/New
Year or the Chinese New Year window, which are expensive for calendar reasons
that have nothing to do with booking early.

Coverage *is* the bias, and it scales predictably:

| Coverage | 30% | 50% | 70% | 80% | 90% |
|---|---|---|---|---|---|
| Minimum reads high by | +22% | +11.7% | +5.0% | +3.6% | +0.9% |

So the two windows are compared only when **both** clear 80%. Otherwise a
well-covered near window against a thin far block finds a difference in the
measurement rather than in the market — the 17 Aug defect, relocated.

**What this lane cannot do is separate season from lead time.** A block five
months out is also a different time of year, so "February is cheaper to fly
than September" is supportable and "book earlier and save" is not. The digest
wording follows the weaker claim. Keeping the data eventually settles it for
free: the same calendar dates age into the near window, and comparing a date
against itself at two lead times isolates the curve from the season.

Keeping the baselines separate is not fussiness. Pooling a 30-day fare with a
150-day fare is the same error as pooling one-way with round-trip (incident 1):
two populations with different means, one median between them, and every
near-window fare suddenly looking like a bargain.

It runs as its own workflow so that if the far lane gets throttled, the daily
digest is untouched.

---

## What was rejected, and why that matters

Five of the eleven techniques were rejected, and two of those on *measurements
of our own data* rather than on argument — the weekday effect and the booking
curve. That is the useful output of a survey like this: not only what to build,
but what to stop considering.

The temptation with a competitor list is to treat every item as a gap. Most of
these were designed for a different problem — long-haul, legacy carriers,
flexible destinations, US origins. The one that transfers cleanly is the
booking horizon, and it transfers because it is about *when we look*, not about
who we are looking at.
