#!/usr/bin/env python3
"""
Miles — Sherenkov Family Travel Attaché
Dispatched by Alfred to search weekend flights and report deals.
"""

import logging
import sys

from flight_search import find_deals
from telegram_notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  Miles  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Miles reporting for duty. Beginning flight survey.")
    try:
        deals = find_deals()
        notify(deals)
        logger.info("Survey complete. Alfred has been informed.")
    except Exception as exc:
        logger.exception("Miles encountered an error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
