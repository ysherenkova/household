#!/usr/bin/env python3
"""
Miles — Sherenkov Family Travel Attaché
Dispatched by Alfred to search weekend flights and report deals.

Usage:
    python main.py                  # standard run — nearest 2 weekends
    python main.py --extended       # extended run — next 8 weekends
    python main.py --weeks 4        # custom horizon
    python main.py --test           # quick smoke-test: 5 airports × 1 weekend
"""

import argparse
import logging
import sys
from datetime import date

from flight_search import DEFAULT_WEEKS, EXTENDED_WEEKS, find_deals
from telegram_notifier import notify

TEST_AIRPORTS = ["MCO", "MIA", "CUN", "NAS", "SJU"]  # ~15 searches, done in seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  Miles  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Miles — flight search agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--extended",
        action="store_true",
        help=f"Extended search: next {EXTENDED_WEEKS} weekends instead of {DEFAULT_WEEKS}",
    )
    group.add_argument(
        "--weeks",
        type=int,
        metavar="N",
        help="Custom number of weekends to search ahead",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help=f"Smoke-test: {len(TEST_AIRPORTS)} airports × 1 weekend, delivers to Telegram",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Search a specific Friday's weekend only (e.g. --date 2026-04-24)",
    )
    args = parser.parse_args()

    if args.test:
        scope = f"TEST ({len(TEST_AIRPORTS)} airports × 1 weekend)"
        logger.info("Miles reporting for duty. Search scope: %s.", scope)
        from flight_search import _search_one
        from windows import get_trip_windows
        windows = get_trip_windows(num_weeks=1)
        from airports import _fallback_airports
        all_ap = {a["iata_code"]: a for a in _fallback_airports()}
        deals = []
        for iata in TEST_AIRPORTS:
            if iata in all_ap:
                for w in windows:
                    deals.extend(_search_one(all_ap[iata], w))
        deals.sort(key=lambda d: (d.depart_date, d.price_usd))
        notify(deals)
        logger.info("Test complete. %d deal(s) sent to Telegram.", len(deals))
        return

    if args.date:
        try:
            start_friday = date.fromisoformat(args.date)
        except ValueError:
            logger.error("--date must be YYYY-MM-DD, got: %s", args.date)
            sys.exit(1)
        scope = f"single weekend ({args.date})"
        logger.info("Miles reporting for duty. Search scope: %s.", scope)
        try:
            deals = find_deals(num_weeks=1, start_friday=start_friday)
            notify(deals)
            logger.info("Survey complete. Alfred has been informed.")
        except Exception as exc:
            logger.exception("Miles encountered an error: %s", exc)
            sys.exit(1)
        return

    if args.extended:
        num_weeks = EXTENDED_WEEKS
        scope = f"extended ({num_weeks} weekends)"
    elif args.weeks:
        num_weeks = args.weeks
        scope = f"custom ({num_weeks} weekends)"
    else:
        num_weeks = DEFAULT_WEEKS
        scope = f"standard ({num_weeks} weekends)"

    logger.info("Miles reporting for duty. Search scope: %s.", scope)
    try:
        deals = find_deals(num_weeks=num_weeks)
        notify(deals)
        logger.info("Survey complete. Alfred has been informed.")
    except Exception as exc:
        logger.exception("Miles encountered an error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
