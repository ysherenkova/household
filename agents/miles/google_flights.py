"""
Alfred - Google Flights client
Thin wrapper around the fast-flights library (no API key required).
"""

import logging
import random
import time
from dataclasses import dataclass, field

from fast_flights import FlightData, Passengers, get_flights

logger = logging.getLogger(__name__)


@dataclass
class RoundTripResult:
    origin: str
    destination: str
    outbound_date: str   # YYYY-MM-DD
    return_date: str     # YYYY-MM-DD
    price_usd: int
    airline: str
    # Outbound leg (the leg we can reliably time-filter)
    outbound_departs: str   # "HH:MM" 24-h
    outbound_arrives: str   # "HH:MM" 24-h
    outbound_duration: str
    outbound_stops: int
    # Return leg (if extractable)
    return_departs: str = "??"
    return_arrives: str = "??"
    return_duration: str = ""
    return_stops: int = -1
    raw_flights: list = field(default_factory=list, repr=False)


def _to_24h(time_str: str) -> str:
    """Convert '6:30 PM', '6:30 PM on Fri, May 8', or '18:30' → '18:30'. Returns '??' on failure."""
    if not time_str:
        return "??"
    import re, datetime
    s = str(time_str).strip()
    # Extract bare time from strings like "5:05 AM on Fri, May 8"
    m = re.match(r"(\d{1,2}:\d{2}\s*(?:AM|PM))", s, re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    if "AM" in s.upper() or "PM" in s.upper():
        for fmt in ("%I:%M %p", "%I:%M%p"):
            try:
                return datetime.datetime.strptime(s.upper(), fmt.upper()).strftime("%H:%M")
            except ValueError:
                continue
    # Already 24-h or partial
    parts = s.replace(".", ":").split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            pass
    return "??"


def _parse_price(price_str: str) -> int:
    if not price_str:
        return 0
    digits = "".join(c for c in str(price_str) if c.isdigit())
    return int(digits) if digits else 0


def search(
    origin: str,
    destination: str,
    outbound_date: str,   # YYYY-MM-DD
    return_date: str,     # YYYY-MM-DD
    adults: int = 2,
    children: int = 1,
) -> list[RoundTripResult]:
    """
    Search Google Flights for round-trip options.
    Returns an empty list on any error (rate-limit, no results, etc.).
    """
    time.sleep(random.uniform(0.15, 0.45))
    try:
        result = get_flights(
            flight_data=[
                FlightData(date=outbound_date, from_airport=origin, to_airport=destination),
                FlightData(date=return_date,   from_airport=destination, to_airport=origin),
            ],
            trip="round-trip",
            seat="economy",
            passengers=Passengers(
                adults=adults,
                children=children,
                infants_in_seat=0,
                infants_on_lap=0,
            ),
            fetch_mode="common",
            max_stops=0,
        )
    except Exception as exc:
        logger.debug("fast-flights %s→%s: %s", origin, destination, exc)
        return []

    out = []
    for f in result.flights or []:
        price = _parse_price(f.price)
        if price <= 0:
            continue
        out.append(RoundTripResult(
            origin=origin,
            destination=destination,
            outbound_date=outbound_date,
            return_date=return_date,
            price_usd=price,
            airline=f.name or "?",
            outbound_departs=_to_24h(f.departure),
            outbound_arrives=_to_24h(f.arrival),
            outbound_duration=f.duration or "",
            outbound_stops=0,  # max_stops=0 is passed to Google, so all results are nonstop
        ))
    return out
