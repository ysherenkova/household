"""
Miles — Telegram Notifier
Alfred frames Miles' report before delivering it to the household.

Message structure:
  1. Summary: header + one line per city with cheapest price
  2. One message per city: all flight options for that city
"""

import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from urllib.parse import quote_plus

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from alfred.persona import greeting, staff_intro, no_results_note, SIGN_OFF, SEPARATOR
from flight_search import FlightDeal

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

FLAG = {
    "US": "🇺🇸", "PR": "🇵🇷", "VI": "🇻🇮", "MX": "🇲🇽", "CA": "🇨🇦",
    "BS": "🇧🇸", "JM": "🇯🇲", "DO": "🇩🇴", "BB": "🇧🇧", "TC": "🇹🇨",
    "KY": "🇰🇾", "LC": "🇱🇨", "SX": "🇸🇽", "AW": "🇦🇼", "BZ": "🇧🇿",
    "CR": "🇨🇷", "PA": "🇵🇦", "GT": "🇬🇹", "HN": "🇭🇳", "TT": "🇹🇹",
}
STOPS_LABEL = {0: "nonstop", 1: "1 stop", 2: "2 stops", -1: "stops unknown"}
MAX_MSG_LEN = 4000  # Telegram hard limit is 4096; leave headroom


def _booking_url(dest_iata: str, depart: date, ret: date) -> str:
    q = (
        f"round trip flights ATL to {dest_iata} "
        f"{depart.strftime('%b %d %Y')} returning {ret.strftime('%b %d %Y')} "
        f"2 adults 1 child economy"
    )
    return f"https://www.google.com/travel/flights?q={quote_plus(q)}"


def _flight_line(d: FlightDeal) -> str:
    """Single compact line for one flight option within a city block."""
    depart_fmt = d.depart_date.strftime("%a, %b %d")
    return_fmt = d.return_date.strftime("%a, %b %d")
    holiday_tag = f"  🎉 {d.holiday_label}" if d.holiday_label else ""

    time_known = d.outbound_departs not in ("??", "")
    depart_time = f", {d.outbound_departs}" if time_known else ""
    arrive_time = f", {d.outbound_arrives}" if time_known else ""

    url = _booking_url(d.destination_iata, d.depart_date, d.return_date)
    airline_part = f" {d.airline}" if d.airline not in ("?", "") else ""

    return "\n".join([
        f"📅 {depart_fmt}{depart_time} – {return_fmt}{arrive_time}{holiday_tag}",
        f"💰 ${d.price_usd}  ·  ✈️{airline_part}  ·  <a href=\"{url}\">Book</a>",
        "",
    ])


def _city_block(iata: str, deals: list[FlightDeal]) -> str:
    """Header + all flights for one city."""
    d0 = deals[0]
    flag = FLAG.get(d0.destination_country, "🌍")
    lines = [f"{flag} <b>{d0.destination_city}  ({iata})</b>", ""]
    for d in deals:
        lines.append(_flight_line(d))
    return "\n".join(lines)


def _summary_line(iata: str, deals: list[FlightDeal]) -> str:
    """One line per city for the summary message."""
    d0 = deals[0]
    flag = FLAG.get(d0.destination_country, "🌍")
    cheapest = min(d.price_usd for d in deals)
    return f"{flag} <b>{d0.destination_city}</b> ({iata}) — from ${cheapest}"


def _deduplicate(deals: list[FlightDeal]) -> list[FlightDeal]:
    """Keep only the cheapest deal per (destination, depart_date, return_date, dep_time, airline)."""
    best: dict[tuple, FlightDeal] = {}
    for d in deals:
        key = (d.destination_iata, d.depart_date, d.return_date, d.outbound_departs, d.airline)
        if key not in best or d.price_usd < best[key].price_usd:
            best[key] = d
    return sorted(best.values(), key=lambda d: (d.destination_iata, d.depart_date, d.outbound_departs))


def _group_by_city(deals: list[FlightDeal]) -> dict[str, list[FlightDeal]]:
    """Group deals by IATA code, each city sorted by depart_date then price."""
    groups: dict[str, list[FlightDeal]] = defaultdict(list)
    for d in deals:
        groups[d.destination_iata].append(d)
    # Sort cities by cheapest price, then sort each city's flights
    return dict(
        sorted(groups.items(), key=lambda kv: min(d.price_usd for d in kv[1]))
    )


def _send(token: str, chat_id: str, text: str) -> bool:
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    if not resp.ok:
        logger.warning("Telegram send to %s failed: %s", chat_id, resp.text[:200])
    return resp.ok


def _build_messages(deals: list[FlightDeal]) -> list[str]:
    """
    Returns a list of Telegram messages:
      [0]   Summary: header + city list with cheapest prices
      [1..] One message per city (split further if over MAX_MSG_LEN)
    """
    now = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    groups = _group_by_city(deals)

    # ── Message 1: summary ──────────────────────────────────────────────────
    summary_lines = [
        f"🎩 <b>{greeting()}, Sherenkov household.</b>",
        SEPARATOR,
        staff_intro("miles"),
        f"<i>{len(deals)} deal(s) · {now}</i>",
        "",
    ]
    for iata, city_deals in groups.items():
        summary_lines.append(_summary_line(iata, city_deals))
    summary_lines += [
        "",
        "<i>Details by city follow ↓</i>",
    ]
    messages = ["\n".join(summary_lines)]

    # ── Messages 2+: one per city (split if needed) ─────────────────────────
    for iata, city_deals in groups.items():
        block = _city_block(iata, city_deals)
        # Split oversized city blocks
        if len(block) <= MAX_MSG_LEN:
            messages.append(block)
        else:
            current = ""
            d0 = city_deals[0]
            flag = FLAG.get(d0.destination_country, "🌍")
            header = f"{flag} <b>{d0.destination_city}  ({iata})</b>\n\n"
            current = header
            for d in city_deals:
                line = _flight_line(d)
                if len(current) + len(line) > MAX_MSG_LEN:
                    messages.append(current)
                    current = header + line
                else:
                    current += line
            if current.strip():
                messages.append(current)

    # ── Footer on last message ───────────────────────────────────────────────
    footer = "\n".join([
        SEPARATOR,
        "<i>Economy · 2 adults + 1 child · nonstop · confirm return before 23:00</i>",
        "",
        SIGN_OFF,
    ])
    messages[-1] += "\n" + footer

    return messages


def notify(deals: list[FlightDeal]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    recipients = [
        os.environ.get("TELEGRAM_CHAT_ID_YULIIA", ""),
        os.environ.get("TELEGRAM_CHAT_ID_IVAN", ""),
    ]

    if not deals:
        now = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
        messages = ["\n".join([
            f"🎩 <b>{greeting()}, Sherenkov household.</b>",
            SEPARATOR,
            staff_intro("miles"),
            "",
            no_results_note("miles"),
            "",
            f"<i>ATL → anywhere · after 18:00 · nonstop · $200–$600</i>",
            f"<i>{now}</i>",
            "",
            SIGN_OFF,
        ])]
    else:
        deals = _deduplicate(deals)
        messages = _build_messages(deals)

    for chat_id in recipients:
        if not chat_id:
            continue
        for i, msg in enumerate(messages):
            ok = _send(token, chat_id, msg)
            logger.info(
                "Telegram → %s msg %d/%d: %s",
                chat_id, i + 1, len(messages), "sent ✓" if ok else "FAILED ✗",
            )
