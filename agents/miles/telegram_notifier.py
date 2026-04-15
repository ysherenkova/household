"""
Miles — Telegram Notifier
Alfred frames Miles' report before delivering it to the household.
"""

import logging
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
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
STOPS_LABEL = {0: "nonstop", 1: "1 stop", 2: "2 stops"}
WINDOW_ICON = {"standard": "📅", "long_thu": "📅✨", "long_mon": "📅✨"}


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

    # ── Header — Alfred's voice ───────────────────────────────────────────────
    header_lines = [
        f"🎩 <b>{greeting()}, Sherenkov household.</b>",
        SEPARATOR,
    ]

    if not deals:
        header_lines += [
            staff_intro("miles"),
            "",
            no_results_note("miles"),
            "",
            f"<i>Criteria: ATL → anywhere · Thu/Fri depart · Sun/Mon return "
            f"· 2 adults + 1 child · $200–$500</i>",
            f"<i>{now}</i>",
            "",
            SIGN_OFF,
        ]
        return "\n".join(header_lines)

    header_lines += [
        staff_intro("miles"),
        f"<i>{len(deals)} deal(s) found · {now}</i>",
        "",
    ]

    # ── Group by window label ─────────────────────────────────────────────────
    by_window: dict[str, list[FlightDeal]] = {}
    for d in deals:
        by_window.setdefault(d.window_label, []).append(d)

    body_lines = []
    for label, wdeals in by_window.items():
        # Pick representative deal to get window metadata
        rep = wdeals[0]
        icon = WINDOW_ICON.get(rep.window_type, "📅")
        holiday_tag = f"  🎉 <b>{rep.holiday_label}</b>" if rep.holiday_label else ""
        body_lines.append(f"{icon} <b>{label}</b>{holiday_tag}")

        return_day = rep.return_date.strftime("%a")   # "Sun" or "Mon"

        for d in sorted(wdeals, key=lambda x: x.price_usd)[:4]:
            flag  = FLAG.get(d.destination_country, "🌍")
            stops = STOPS_LABEL.get(d.outbound_stops, f"{d.outbound_stops} stops")
            ret_note = (
                f"dep {d.return_departs}" if d.return_departs not in ("??", "")
                else "verify time"
            )
            body_lines += [
                f"  {flag} <b>{d.destination_city}</b> ({d.destination_iata})"
                f"  ·  <b>${d.price_usd}</b>  ·  {d.airline}",
                f"  ┣ Out: ATL {d.outbound_departs} → {d.destination_iata} {d.outbound_arrives}"
                f"  ({d.outbound_duration}, {stops})",
                f"  ┗ Back {return_day}: {ret_note}"
                f"  <i>⚠ confirm arrives ATL before 23:00</i>",
                "",
            ]

    footer_lines = [
        SEPARATOR,
        "<i>Prices: economy, 2 adults + 1 child (total).</i>",
        "<i>Miles rotates through 300+ destinations — new batches arrive twice daily.</i>",
        "",
        SIGN_OFF,
    ]

    return "\n".join(header_lines + body_lines + footer_lines)


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
