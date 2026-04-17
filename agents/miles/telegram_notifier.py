"""
Miles — Telegram Notifier
Alfred frames Miles' report before delivering it to the household.
"""

import logging
import os
import sys
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


def _booking_url(dest_iata: str, depart: date, ret: date) -> str:
    """Construct a pre-filled Google Flights search URL for this route and dates."""
    q = (
        f"round trip flights ATL to {dest_iata} "
        f"{depart.strftime('%b %d %Y')} returning {ret.strftime('%b %d %Y')} "
        f"2 adults 1 child economy"
    )
    return f"https://www.google.com/travel/flights?q={quote_plus(q)}"


def _deal_block(d: FlightDeal) -> str:
    flag  = FLAG.get(d.destination_country, "🌍")
    stops = STOPS_LABEL.get(d.outbound_stops, f"{d.outbound_stops} stops")

    depart_fmt = d.depart_date.strftime("%a, %b %d")
    return_fmt = d.return_date.strftime("%a, %b %d")
    holiday_tag = f"  🎉 {d.holiday_label}" if d.holiday_label else ""

    url = _booking_url(d.destination_iata, d.depart_date, d.return_date)

    # Only show time detail when the library actually returned it
    time_known = d.outbound_departs not in ("??", "")
    time_part = f"  ·  out {d.outbound_departs}→{d.outbound_arrives}" if time_known else ""

    airline_part = f"  ·  ✈️ {d.airline}" if d.airline not in ("?", "") else ""

    return "\n".join([
        f"📅 <b>{depart_fmt} – {return_fmt}</b>{holiday_tag}",
        f"{flag} <b>{d.destination_city}</b>  ({d.destination_iata})",
        f"💰 ${d.price_usd}{airline_part}  ·  {stops}{time_part}",
        f'🔗 <a href="{url}">Book on Google Flights</a>',
        "",
    ])


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


def _format(deals: list[FlightDeal]) -> str:
    now = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")

    lines = [
        f"🎩 <b>{greeting()}, Sherenkov household.</b>",
        SEPARATOR,
    ]

    if not deals:
        lines += [
            staff_intro("miles"),
            "",
            no_results_note("miles"),
            "",
            f"<i>ATL → anywhere · Thu/Fri–Sun/Mon · 2 adults + 1 child · $200–$500</i>",
            f"<i>{now}</i>",
            "",
            SIGN_OFF,
        ]
        return "\n".join(lines)

    lines += [
        staff_intro("miles"),
        f"<i>{len(deals)} deal(s) · {now}</i>",
        "",
    ]

    for d in deals:
        lines.append(_deal_block(d))

    lines += [
        SEPARATOR,
        "<i>Prices: economy · 2 adults + 1 child (total) · confirm return arrives ATL before 23:00</i>",
        "",
        SIGN_OFF,
    ]

    return "\n".join(lines)


MAX_MSG_LEN = 4000  # Telegram hard limit is 4096; leave headroom


def _deduplicate(deals: list[FlightDeal]) -> list[FlightDeal]:
    """Keep only the cheapest deal per (destination, depart_date, return_date)."""
    best: dict[tuple, FlightDeal] = {}
    for d in deals:
        key = (d.destination_iata, d.depart_date, d.return_date)
        if key not in best or d.price_usd < best[key].price_usd:
            best[key] = d
    return sorted(best.values(), key=lambda d: (d.depart_date, d.price_usd))


def _split_messages(deals: list[FlightDeal], header: str, footer: str) -> list[str]:
    """
    Build a list of Telegram messages, each under MAX_MSG_LEN chars.
    Header goes on the first message, footer on the last.
    """
    blocks = [_deal_block(d) for d in deals]
    messages = []
    current = header

    for block in blocks:
        if len(current) + len(block) > MAX_MSG_LEN:
            messages.append(current)
            current = block
        else:
            current += block

    current += footer
    messages.append(current)
    return messages


def notify(deals: list[FlightDeal]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    recipients = [
        os.environ.get("TELEGRAM_CHAT_ID_YULIIA", ""),
        os.environ.get("TELEGRAM_CHAT_ID_IVAN", ""),
    ]

    if not deals:
        messages = [_format([])]
    else:
        deals = _deduplicate(deals)
        now = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
        header = "\n".join([
            f"🎩 <b>{greeting()}, Sherenkov household.</b>",
            SEPARATOR,
            staff_intro("miles"),
            f"<i>{len(deals)} deal(s) · {now}</i>",
            "",
        ])
        footer = "\n".join([
            SEPARATOR,
            "<i>Prices: economy · 2 adults + 1 child (total) · confirm return arrives ATL before 23:00</i>",
            "",
            SIGN_OFF,
        ])
        messages = _split_messages(deals, header, footer)

    for chat_id in recipients:
        if not chat_id:
            continue
        for i, msg in enumerate(messages):
            ok = _send(token, chat_id, msg)
            logger.info(
                "Telegram → %s msg %d/%d: %s",
                chat_id, i + 1, len(messages), "sent ✓" if ok else "FAILED ✗",
            )
