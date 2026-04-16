"""
Miles — Flight Search Logic

Searches Google Flights for every combination of:
  - airport batch (rotating 60 of 300+ destinations per run)
  - trip window   (standard Fri→Sun, long Thu→Sun, long Fri→Mon)

Filters applied per result:
  - Outbound departs ATL on the correct day, at or after window.depart_after_h
  - Total price $200–$500
  - Return date matches the window's return_date
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date

from airports import load_destination_airports, select_batch
from google_flights import RoundTripResult, search
from windows import TripWindow, get_trip_windows

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ORIGIN          = "ATL"
ADULTS          = 2
CHILDREN        = 1        # born 08/19/2022 → child fare (age 2–11)
BUDGET_MIN      = 200
BUDGET_MAX      = 500
DEFAULT_WEEKS   = 2        # standard daily run — nearest 2 weekends
EXTENDED_WEEKS  = 8        # extended run — next 8 weekends (~2 months)
BATCH_SIZE      = 60
MAX_WORKERS     = 5


@dataclass
class FlightDeal:
    window_label: str          # from TripWindow.label
    window_type: str           # "standard" | "long_thu" | "long_mon"
    holiday_label: str         # "" or "Memorial Day 🇺🇸"
    depart_date: date
    return_date: date
    destination_iata: str
    destination_city: str
    destination_country: str
    price_usd: int
    airline: str
    outbound_departs: str      # "HH:MM"
    outbound_arrives: str
    outbound_duration: str
    outbound_stops: int
    return_departs: str
    return_arrives: str
    return_duration: str


def _time_to_minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


def _passes_filter(result: RoundTripResult, window: TripWindow) -> bool:
    if not (BUDGET_MIN <= result.price_usd <= BUDGET_MAX):
        return False
    dep_mins = _time_to_minutes(result.outbound_departs)
    if dep_mins < 0:
        return False
    if dep_mins < window.depart_after_h * 60:
        return False
    return True


def _search_one(airport: dict, window: TripWindow) -> list[FlightDeal]:
    dest    = airport["iata_code"]
    city    = airport.get("municipality") or dest
    country = airport.get("iso_country", "")

    results: list[RoundTripResult] = search(
        origin=ORIGIN,
        destination=dest,
        outbound_date=window.depart_date.isoformat(),
        return_date=window.return_date.isoformat(),
        adults=ADULTS,
        children=CHILDREN,
    )

    deals = []
    for r in results:
        if not _passes_filter(r, window):
            continue
        deals.append(FlightDeal(
            window_label=window.label,
            window_type=window.window_type,
            holiday_label=window.holiday_label,
            depart_date=window.depart_date,
            return_date=window.return_date,
            destination_iata=dest,
            destination_city=city,
            destination_country=country,
            price_usd=r.price_usd,
            airline=r.airline,
            outbound_departs=r.outbound_departs,
            outbound_arrives=r.outbound_arrives,
            outbound_duration=r.outbound_duration,
            outbound_stops=r.outbound_stops,
            return_departs=r.return_departs,
            return_arrives=r.return_arrives,
            return_duration=r.return_duration,
        ))
    return deals


def find_deals(num_weeks: int = DEFAULT_WEEKS) -> list[FlightDeal]:
    """
    Main entry point.
    Loads this run's rotating airport batch, generates all trip windows,
    then searches every (airport × window) pair concurrently.
    """
    all_airports = load_destination_airports()
    batch        = select_batch(all_airports, BATCH_SIZE)
    windows      = get_trip_windows(num_weeks)

    total_tasks = len(batch) * len(windows)
    logger.info(
        "Miles: %d airports × %d windows = %d searches this run",
        len(batch), len(windows), total_tasks,
    )

    tasks = [(airport, window) for window in windows for airport in batch]
    all_deals: list[FlightDeal] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_search_one, airport, window): (airport, window)
            for airport, window in tasks
        }
        for future in as_completed(futures):
            airport, window = futures[future]
            try:
                deals = future.result()
                if deals:
                    logger.info(
                        "  ✓ %s (%s) %s → %d deal(s)",
                        airport["iata_code"],
                        airport.get("municipality", ""),
                        window.depart_date.strftime("%b %d"),
                        len(deals),
                    )
                all_deals.extend(deals)
            except Exception as exc:
                logger.debug("Task failed %s / %s: %s",
                             airport["iata_code"], window.label, exc)

    # Sort: depart date → window type → price
    type_order = {"standard": 0, "long_thu": 1, "long_mon": 2}
    all_deals.sort(key=lambda d: (
        d.depart_date,
        type_order.get(d.window_type, 9),
        d.price_usd,
    ))
    logger.info("Miles: %d qualifying deal(s) found.", len(all_deals))
    return all_deals
