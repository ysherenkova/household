"""
Alfred - Telegram Notifier
Formats flight deals into a readable message and delivers it to all recipients.
"""

import logging
import os
from datetime import datetime

import requests

from flight_search import FlightDeal

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

AIRLINE_NAMES: dict[str, str] = {
    "AA": "American", "DL": "Delta", "UA": "United", "WN": "Southwest",
    "B6": "JetBlue", "AS": "Alaska", "NK": "Spirit", "F9": "Frontier",
    "G4": "Allegiant", "SY": "Sun Country", "HA": "Hawaiian",
}


def _send(token: str, chat_id: str, text: str) -> bool:
    url = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    if not resp.ok:
        logger.warning("Telegram send failed for %s: %s", chat_id, resp.text)
    return resp.ok


def _airline_label(code: str) -> str:
    return AIRLINE_NAMES.get(code, code)


def _format_message(deals: list[FlightDeal]) -> str:
    now = datetime.now().strftime("%b %d, %Y %H:%M")

    if not deals:
        return (
            "✈️ <b>Alfred's Flight Report</b>\n"
            f"<i>{now}</i>\n\n"
            "No flights found matching all your criteria this run.\n"
            "Criteria: ATL → anywhere • Fri after 17:00 • back Sun before 23:00 "
            "• 2 adults + 1 child • $200–$500\n\n"
            "— Alfred 🎩"
        )

    # Group by weekend
    by_weekend: dict[str, list[FlightDeal]] = {}
    for deal in deals:
        by_weekend.setdefault(deal.weekend_label, []).append(deal)

    lines = [
        "✈️ <b>Alfred's Flight Report</b>",
        f"<i>{now} · {len(deals)} deal(s) found · next 8 weekends</i>",
        "",
    ]

    for weekend_label, weekend_deals in by_weekend.items():
        lines.append(f"📅 <b>{weekend_label}</b>")
        # Show top 3 cheapest per weekend
        for d in sorted(weekend_deals, key=lambda x: x.price)[:3]:
            airline = _airline_label(d.airline)
            lines += [
                f"  🏙 <b>{d.destination_name}</b>  •  <b>${d.price:.0f}</b>  ({airline})",
                f"  ┣ Out: {d.outbound_summary}",
                f"  ┗ Back: {d.return_summary}",
                "",
            ]

    lines += [
        "<i>Prices shown are total for 2 adults + 1 child. "
        "Search on Google Flights or your preferred booking site to confirm.</i>",
        "",
        "— Alfred 🎩",
    ]
    return "\n".join(lines)


def notify(deals: list[FlightDeal]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    recipient_ids = [
        os.environ.get("TELEGRAM_CHAT_ID_YULIIA", ""),
        os.environ.get("TELEGRAM_CHAT_ID_IVAN", ""),
    ]

    message = _format_message(deals)

    for chat_id in recipient_ids:
        if not chat_id:
            continue
        ok = _send(token, chat_id, message)
        logger.info("Telegram → %s: %s", chat_id, "sent" if ok else "FAILED")
