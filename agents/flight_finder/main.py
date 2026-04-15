#!/usr/bin/env python3
"""
Alfred - Sherenkov Family Butler
Flight Finder Agent

Searches for round-trip weekend flights from Atlanta that match
the family's criteria and reports results via Telegram.
"""

import logging
import sys

from flight_search import find_deals
from telegram_notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  Alfred  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Good day. Alfred is starting the flight search.")
    try:
        deals = find_deals()
        logger.info("Search complete. %d qualifying deal(s) found.", len(deals))
        notify(deals)
        logger.info("Messages dispatched. Alfred signing off.")
    except Exception as exc:
        logger.exception("Alfred encountered an error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
