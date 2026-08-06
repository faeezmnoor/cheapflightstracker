"""Compose and send the daily digest email."""

from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import List, Optional

from .config import Config
from .models import Deal, Offer, RouteSummary, RunResult


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _money(amount: Optional[float], currency: str) -> str:
    if amount is None:
        return "-"
    return f"{currency} {amount:,.0f}"


def _pct(fraction: Optional[float]) -> str:
    if fraction is None:
        return "-"
    return f"{fraction * 100:.0f}%"


def _trip_desc(offer: Offer) -> str:
    if offer.return_date:
        return f"{offer.departure_date} → {offer.return_date} (round trip)"
    return f"{offer.departure_date} (one way)"


def _stops_desc(offer: Offer) -> str:
    if offer.stops is None:
        return ""
    return "direct" if offer.stops == 0 else f"{offer.stops} stop(s)"


def _short_date(value: Optional[str]) -> str:
    """'2026-09-09' -> '9 Sep'. Falls back to the raw string if unparseable."""
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return value
    return f"{parsed.day} {parsed.strftime('%b')}"


def _short_when(offer: Offer) -> str:
    """Compact date + trip type for the digest table.

    The trip type must be visible: a return fare costs about double a one-way,
    so an unlabelled round-trip price in a column of one-ways reads as a route
    being wildly expensive.
    """
    if offer.return_date:
        return (f"{_short_date(offer.departure_date)} → "
                f"{_short_date(offer.return_date)} · return")
    return f"{_short_date(offer.departure_date)} · one-way"


# --------------------------------------------------------------------------- #
# Subject
# --------------------------------------------------------------------------- #
def build_subject(result: RunResult) -> str:
    deals = result.deals
    if not deals:
        return f"✈️ No KL→Indonesia deals today ({result.run_date})"
    severe = [d for d in deals if d.is_severe]
    best = deals[0]
    city = best.offer.destination
    lead = f"{len(deals)} underpriced KL→Indonesia flight(s)"
    if severe:
        lead = f"\U0001f525 {len(severe)} severely underpriced + {lead}"
    return (f"✈️ {lead} — best: KL→{city} "
            f"{_pct(best.discount_pct)} off")


# --------------------------------------------------------------------------- #
# Bodies
# --------------------------------------------------------------------------- #
def _scanned_window(result: RunResult) -> str:
    """e.g. '10 dates, 13 Aug - 5 Oct' — what 'cheapest' is cheapest *of*."""
    dates = result.scanned_departures
    if not dates:
        return ""
    if len(dates) == 1:
        return f"1 departure date ({_short_date(dates[0])})"
    return (f"{len(dates)} departure dates "
            f"({_short_date(dates[0])} – {_short_date(dates[-1])})")


def build_text(result: RunResult) -> str:
    lines: List[str] = []
    lines.append(f"Daily flight-deal scan  —  {result.run_date}")
    lines.append(f"Origin: KL   Currency: {result.currency}   "
                 f"Offers checked: {result.offers_checked}")
    lines.append("=" * 60)

    if result.deals:
        lines.append("")
        lines.append(f"UNDERPRICED FLIGHTS ({len(result.deals)})")
        lines.append("-" * 60)
        for d in result.deals:
            o = d.offer
            tag = "*** SEVERE *** " if d.is_severe else ""
            lines.append(
                f"{tag}KL -> {o.destination}  {_money(o.price, o.currency)}  "
                f"({_pct(d.discount_pct)} off usual {_money(d.baseline.median, o.currency)}, "
                f"save {_money(d.saving, o.currency)})"
            )
            lines.append(f"    {_trip_desc(o)}  {_stops_desc(o)}  {o.airline or ''}")
            if o.deep_link:
                lines.append(f"    {o.deep_link}")
    else:
        lines.append("")
        lines.append("No underpriced flights today. Cheapest fares below.")

    lines.append("")
    lines.append("CHEAPEST TODAY (per route)")
    lines.append("-" * 60)
    for s in result.summaries:
        if not s.cheapest:
            lines.append(f"KL -> {s.city}: no offers")
            continue
        o = s.cheapest
        usual = (_money(s.baseline.median, result.currency)
                 if s.baseline.is_reliable else "building baseline")
        # Only advertise a saving when the fare is genuinely below usual.
        disc = (f" ({_pct(s.discount_pct)} off)"
                if s.discount_pct and s.discount_pct > 0 else "")
        lines.append(
            f"KL -> {s.city}: {_money(o.price, o.currency)}{disc}  "
            f"usual {usual}  [{_trip_desc(o)}]"
        )

    if result.errors:
        lines.append("")
        lines.append(f"Notes: {len(result.errors)} search error(s) this run.")
    lines.append("")
    window = _scanned_window(result)
    if window:
        lines.append("")
        lines.append(f"Cheapest = cheapest across the {window} scanned.")
    lines.append("")
    lines.append("Baselines strengthen as history accumulates. "
                 "Fares via Google Flights. Automated daily scan.")
    return "\n".join(lines)


def _deal_card(d: Deal) -> str:
    o = d.offer
    border = "#c0392b" if d.is_severe else "#e67e22"
    badge = ("SEVERELY UNDERPRICED" if d.is_severe else "UNDERPRICED")
    badge_bg = "#c0392b" if d.is_severe else "#e67e22"
    link = (f'<a href="{escape(o.deep_link)}" style="color:#2c7be5;'
            f'text-decoration:none;">View on Google Flights &rarr;</a>'
            if o.deep_link else "")
    return f"""
    <tr><td style="padding:0 0 14px 0;">
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #eee;border-left:5px solid {border};
                    border-radius:6px;background:#fff;">
        <tr><td style="padding:14px 18px;">
          <span style="display:inline-block;background:{badge_bg};color:#fff;
                       font-size:11px;font-weight:700;letter-spacing:.5px;
                       padding:3px 8px;border-radius:3px;">{badge}</span>
          <span style="font-size:13px;color:#999;float:right;">
                {escape(_stops_desc(o))} {escape(o.airline or '')}</span>
          <div style="font-size:20px;font-weight:700;color:#1a1a1a;margin:10px 0 2px;">
                KL &rarr; {escape(o.destination)}</div>
          <div style="font-size:13px;color:#666;">{escape(_trip_desc(o))}</div>
          <div style="margin-top:10px;">
            <span style="font-size:26px;font-weight:800;color:#111;">
                  {escape(_money(o.price, o.currency))}</span>
            <span style="font-size:14px;color:#27ae60;font-weight:700;
                         margin-left:10px;">
                  {escape(_pct(d.discount_pct))} off &middot;
                  save {escape(_money(d.saving, o.currency))}</span>
            <span style="font-size:12px;color:#999;margin-left:8px;
                         text-decoration:line-through;">
                  usual {escape(_money(d.baseline.median, o.currency))}</span>
          </div>
          <div style="margin-top:10px;font-size:14px;">{link}</div>
        </td></tr>
      </table>
    </td></tr>"""


def _summary_row(s: RouteSummary, currency: str) -> str:
    if not s.cheapest:
        return (f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">'
                f'KL &rarr; {escape(s.city)}</td>'
                f'<td colspan="4" style="padding:8px 12px;color:#999;'
                f'border-bottom:1px solid #f0f0f0;">no offers</td></tr>')
    o = s.cheapest
    usual = (_money(s.baseline.median, currency)
             if s.baseline.is_reliable else "building…")
    # A negative "discount" means it's pricier than usual — don't call it "off".
    has_saving = bool(s.discount_pct and s.discount_pct > 0)
    disc = _pct(s.discount_pct) if has_saving else ""
    disc_color = "#27ae60" if has_saving else "#999"
    return (
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">'
        f'KL &rarr; {escape(s.city)}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;'
        f'font-weight:700;white-space:nowrap;">{escape(_money(o.price, currency))}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;'
        f'color:#666;font-size:13px;white-space:nowrap;">'
        f'{escape(_short_when(o))}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;'
        f'color:{disc_color};">{escape(disc)}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;'
        f'color:#999;">{escape(usual)}</td>'
        f'</tr>'
    )


def build_html(result: RunResult) -> str:
    deals_html = "".join(_deal_card(d) for d in result.deals)
    if not deals_html:
        deals_html = (
            '<tr><td style="padding:14px 18px;background:#f8f9fa;border-radius:6px;'
            'color:#555;">No underpriced flights today. The cheapest fares per '
            'route are below — baselines keep learning what "usual" looks '
            'like.</td></tr>'
        )
    summary_html = "".join(_summary_row(s, result.currency) for s in result.summaries)
    window = _scanned_window(result)
    scanned_note = (f"&#9432; <strong>Cheapest</strong> means cheapest across "
                    f"the {escape(window)} scanned — not every possible date."
                    if window else "")

    return f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f5f7;
             font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;">
<tr><td align="center" style="padding:24px 12px;">
  <table width="600" cellpadding="0" cellspacing="0"
         style="max-width:600px;width:100%;">
    <tr><td style="padding:0 0 18px 0;">
      <div style="font-size:22px;font-weight:800;color:#111;">
        &#9992;&#65039; KL &rarr; Indonesia flight deals</div>
      <div style="font-size:13px;color:#888;margin-top:4px;">
        {escape(result.run_date)} &middot; {len(result.deals)} deal(s) &middot;
        {result.offers_checked} fares checked &middot; {escape(result.currency)}</div>
    </td></tr>

    <tr><td style="font-size:15px;font-weight:700;color:#333;padding:6px 0 10px;">
      Underpriced flights</td></tr>
    <tr><td><table width="100%" cellpadding="0" cellspacing="0">{deals_html}</table></td></tr>

    <tr><td style="font-size:15px;font-weight:700;color:#333;padding:22px 0 8px;">
      Cheapest today, every route</td></tr>
    <tr><td>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #eee;border-radius:6px;background:#fff;
                    font-size:14px;color:#333;border-collapse:collapse;">
        <tr style="background:#fafafa;">
          <th align="left" style="padding:8px 12px;font-size:12px;color:#888;
              border-bottom:1px solid #eee;">Route</th>
          <th align="left" style="padding:8px 12px;font-size:12px;color:#888;
              border-bottom:1px solid #eee;">Cheapest</th>
          <th align="left" style="padding:8px 12px;font-size:12px;color:#888;
              border-bottom:1px solid #eee;">When</th>
          <th align="left" style="padding:8px 12px;font-size:12px;color:#888;
              border-bottom:1px solid #eee;">Off usual</th>
          <th align="left" style="padding:8px 12px;font-size:12px;color:#888;
              border-bottom:1px solid #eee;">Usual</th>
        </tr>
        {summary_html}
      </table>
    </td></tr>

    <tr><td style="padding:10px 0 0;font-size:12px;color:#888;">
      {scanned_note}
    </td></tr>
    <tr><td style="padding:14px 0 8px;font-size:12px;color:#aaa;line-height:1.6;">
      A fare is flagged when it drops well below the usual <em>cheapest</em>
      fare for that route and trip type (one-way and return are compared
      separately). Baselines strengthen as history accumulates. Fares via
      Google Flights; always verify and book with the airline.
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def send_email(result: RunResult, config: Config) -> bool:
    """Send the digest. Returns True if actually sent, False if skipped."""
    if not result.deals and not config.always_email:
        print("[email] No deals and ALWAYS_EMAIL is off — skipping send.")
        return False

    subject = build_subject(result)
    text_body = build_text(result)
    html_body = build_html(result)

    if config.dry_run:
        print("[email] DRY_RUN — not sending. Preview:")
        print(f"Subject: {subject}")
        print(text_body)
        return False

    missing = [n for n, v in {
        "SMTP_USER": config.smtp_user,
        "SMTP_APP_PASSWORD": config.smtp_app_password,
        "EMAIL_TO": config.email_to,
    }.items() if not v]
    if missing:
        print(f"[email] Missing {', '.join(missing)} — printing instead:")
        print(f"Subject: {subject}")
        print(text_body)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.email_from or config.smtp_user
    msg["To"] = config.email_to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, context=context) as server:
        server.login(config.smtp_user, config.smtp_app_password)
        server.sendmail(msg["From"], [config.email_to], msg.as_string())
    print(f"[email] Sent to {config.email_to}: {subject}")
    return True
