"""
Alfred - Flight Search Logic

Search criteria:
  • Origin: ATL (Hartsfield-Jackson Atlanta)
  • Destination: any airport in the current batch (rotates through 300+ worldwide)
  • Trip: round-trip
  • Outbound: departs ATL on Friday after 17:00
  • Return: departs destination on Sunday (arrives ATL — time shown in message)
  • Passengers: 2 adults + 1 child (born 08/19/2022)
  • Budget: $200 – $500 total
  • Horizon: next 8 weekends
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta

from airports import load_destination_airports, select_batch
from google_flights import RoundTripResult, search

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ORIGIN = "ATL"
ADULTS = 2
CHILDREN = 1           # born 08/19/2022 → child fare (age 2-11)
BUDGET_MIN = 200
BUDGET_MAX = 500
DEPART_AFTER_HOUR = 17  # outbound must leave ATL at or after 17:00 (5 PM)
NUM_WEEKENDS = 8
BATCH_SIZE = 60         # airports searched per run
MAX_WORKERS = 5         # concurrent search threads (gentle on Google)


@dataclass
class FlightDeal:
    weekend_label: str      # "Apr 18 – Apr 20, 2025"
    friday: date
    sunday: date
    destination_iata: str
    destination_city: str
    destination_country: str
    price_usd: int
    airline: str
    outbound_departs: str   # "HH:MM"
    outbound_arrives: str
    outbound_duration: str
    outbound_stops: int
    # Return leg info (best-effort — Google Flights round-trip result shows outbound detail)
    return_departs: str
    return_arrives: str
    return_duration: str


def _upcoming_weekends(n: int = NUM_WEEKENDS) -> list[tuple[date, date]]:
    today = date.today()
    days_to_friday = (4 - today.weekday()) % 7 or 7
    first_friday = today + timedelta(days=days_to_friday)
    return [
        (first_friday + timedelta(weeks=i), first_friday + timedelta(weeks=i, days=2))
        for i in range(n)
    ]


def _time_to_minutes(hhmm: str) -> int:
    """'18:45' → 1125. Returns -1 on failure."""
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return -1


def _passes_filter(result: RoundTripResult) -> bool:
    # Price
    if not (BUDGET_MIN <= result.price_usd <= BUDGET_MAX):
        return False
    # Outbound departs ATL after 17:00 on Friday
    dep_mins = _time_to_minutes(result.outbound_departs)
    if dep_mins < 0:
        return False  # unparseable — skip
    if dep_mins < DEPART_AFTER_HOUR * 60:
        return False
    return True


def _search_one(
    airport: dict,
    friday: date,
    sunday: date,
) -> list[FlightDeal]:
    """Search one origin→destination pair for one weekend."""
    dest = airport["iata_code"]
    city = airport.get("municipality") or dest
    country = airport.get("iso_country", "")

    results: list[RoundTripResult] = search(
        origin=ORIGIN,
        destination=dest,
        outbound_date=friday.isoformat(),
        return_date=sunday.isoformat(),
        adults=ADULTS,
        children=CHILDREN,
    )

    deals = []
    weekend_label = f"{friday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"

    for r in results:
        if not _passes_filter(r):
            continue
        deals.append(FlightDeal(
            weekend_label=weekend_label,
            friday=friday,
            sunday=sunday,
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


def find_deals() -> list[FlightDeal]:
    """
    Main search entry point.
    Loads this run's airport batch and searches each airport × 8 weekends
    concurrently (up to MAX_WORKERS threads).
    """
    all_airports = load_destination_airports()
    batch = select_batch(all_airports, BATCH_SIZE)
    weekends = _upcoming_weekends()

    logger.info(
        "Searching %d airports × %d weekends = %d queries",
        len(batch), len(weekends), len(batch) * len(weekends),
    )

    # Build all (airport, friday, sunday) tasks
    tasks = [(airport, friday, sunday) for friday, sunday in weekends for airport in batch]

    all_deals: list[FlightDeal] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_search_one, airport, friday, sunday): (airport, friday)
            for airport, friday, sunday in tasks
        }
        for future in as_completed(futures):
            airport, friday = futures[future]
            try:
                deals = future.result()
                if deals:
                    logger.info(
                        "  ✓ %s (%s) %s → %d deal(s)",
                        airport["iata_code"],
                        airport.get("municipality", ""),
                        friday.strftime("%b %d"),
                        len(deals),
                    )
                all_deals.extend(deals)
            except Exception as exc:
                logger.debug("Task failed %s: %s", airport["iata_code"], exc)

    # Sort: by date first, then price
    all_deals.sort(key=lambda d: (d.friday, d.price_usd))
    logger.info("Total qualifying deals found: %d", len(all_deals))
    return all_deals
