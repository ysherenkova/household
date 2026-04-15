"""
Alfred - Telegram Notifier
Formats deals into a tidy message and delivers it to both recipients.
"""

import logging
import os
from datetime import datetime, timezone

import requests

from flight_search import FlightDeal

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

FLAG = {
    "US": "🇺🇸", "PR": "🇵🇷", "VI": "🇻🇮", "MX": "🇲🇽", "CA": "🇨🇦",
    "BS": "🇧🇸", "JM": "🇯🇲", "DO": "🇩🇴", "BB": "🇧🇧", "TC": "🇹🇨",
    "KY": "🇰🇾", "LC": "🇱🇨", "SX": "🇸🇽", "AW": "🇦🇼", "BZ": "🇧🇿",
    "CR": "🇨🇷", "PA": "🇵🇦", "GT": "🇬🇹", "HN": "🇭🇳", "TT": "🇹🇹",
}

STOPS_LABEL = {0: "nonstop", 1: "1 stop", 2: "2 stops"}


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
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")

    if not deals:
        return (
            "✈️ <b>Alfred's Flight Report</b>\n"
            f"<i>{now}</i>\n\n"
            "No deals found in this run's batch.\n"
            "Alfred searches a rotating set of 60+ airports per run and covers "
            "300+ destinations every 2-3 days — check back soon!\n\n"
            "<i>Criteria: ATL → anywhere · Fri after 17:00 · "
            "Sun return · 2 adults + 1 child · $200–$500 total</i>\n\n"
            "— Alfred 🎩"
        )

    # Group by weekend
    by_weekend: dict[str, list[FlightDeal]] = {}
    for d in deals:
        by_weekend.setdefault(d.weekend_label, []).append(d)

    lines = [
        "✈️ <b>Alfred's Flight Report</b>",
        f"<i>{now} · {len(deals)} deal(s) across {len(by_weekend)} weekend(s)</i>",
        "",
    ]

    for label, wdeals in by_weekend.items():
        lines.append(f"📅 <b>{label}</b>")
        for d in sorted(wdeals, key=lambda x: x.price_usd)[:4]:
            flag = FLAG.get(d.destination_country, "🌍")
            stops = STOPS_LABEL.get(d.outbound_stops, f"{d.outbound_stops} stops")
            ret_time = (
                f"Dep {d.return_departs}" if d.return_departs not in ("??", "")
                else "check return time"
            )
            lines += [
                f"  {flag} <b>{d.destination_city}</b> ({d.destination_iata})  •  "
                f"<b>${d.price_usd}</b>  •  {d.airline}",
                f"  ┣ Out: ATL {d.outbound_departs} → {d.destination_iata} {d.outbound_arrives}"
                f"  ({d.outbound_duration}, {stops})",
                f"  ┗ Return Sun: {ret_time} ⚠️ verify arrives ATL before 23:00",
                "",
            ]

    lines += [
        "<i>Total price for 2 adults + 1 child (economy).</i>",
        "<i>Return arrival time: Alfred shows the best available — "
        "please confirm it reaches ATL by 23:00 before booking.</i>",
        "",
        "— Alfred 🎩",
    ]
    return "\n".join(lines)


def notify(deals: list[FlightDeal]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    recipients = [
        os.environ.get("TELEGRAM_CHAT_ID_YULIIA", ""),
        os.environ.get("TELEGRAM_CHAT_ID_IVAN", ""),
    ]
    message = _format(deals)
    for chat_id in recipients:
        if chat_id:
            ok = _send(token, chat_id, message)
            logger.info("Telegram → %s: %s", chat_id, "sent ✓" if ok else "FAILED ✗")
