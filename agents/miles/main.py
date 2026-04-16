#!/usr/bin/env python3
"""
Miles — Sherenkov Family Travel Attaché
Dispatched by Alfred to search weekend flights and report deals.

Usage:
    python main.py                  # standard run — nearest 2 weekends
    python main.py --extended       # extended run — next 8 weekends
    python main.py --weeks 4        # custom horizon
"""

import argparse
import logging
import sys

from flight_search import DEFAULT_WEEKS, EXTENDED_WEEKS, find_deals
from telegram_notifier import notify

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
    args = parser.parse_args()

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
