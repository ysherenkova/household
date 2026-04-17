"""
Alfred - Google Flights client
Bypasses fast-flights' broken HTML parser and reads flight data directly
from aria-label attributes, which Google has kept stable.
"""

import logging
import random
import re
import time
from dataclasses import dataclass, field

from fast_flights import FlightData, Passengers
from fast_flights.core import fetch
from fast_flights.filter import TFSData
from selectolax.lexbor import LexborHTMLParser

logger = logging.getLogger(__name__)


@dataclass
class RoundTripResult:
    origin: str
    destination: str
    outbound_date: str   # YYYY-MM-DD
    return_date: str     # YYYY-MM-DD
    price_usd: int
    airline: str
    outbound_departs: str   # "HH:MM" 24-h
    outbound_arrives: str   # "HH:MM" 24-h
    outbound_stops: int
    return_departs: str = "??"
    return_arrives: str = "??"
    raw_flights: list = field(default_factory=list, repr=False)


# "at 6:00 AM on Friday" or "at 6:00 AM on Friday, April 24"
_TIME_RE = re.compile(r"at (\d{1,2}:\d{2}\s*(?:AM|PM))", re.IGNORECASE)
# "flight with Frontier"
_AIRLINE_RE = re.compile(r"flight with ([^.]+)\.", re.IGNORECASE)
# "From 414 US dollars"
_PRICE_RE = re.compile(r"From (\d[\d,]*)\s+\w+ dollars", re.IGNORECASE)


def _to_24h(time_str: str) -> str:
    """'6:00 AM' → '06:00'. Returns '??' on failure."""
    import datetime
    try:
        return datetime.datetime.strptime(time_str.strip().upper(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return "??"


def _parse_aria(label: str) -> dict | None:
    """Extract price, airline, departure and arrival from an item's aria-label."""
    price_m   = _PRICE_RE.search(label)
    airline_m = _AIRLINE_RE.search(label)
    times     = _TIME_RE.findall(label)
    if not price_m or len(times) < 2:
        return None
    return {
        "price":    int(price_m.group(1).replace(",", "")),
        "airline":  airline_m.group(1).strip() if airline_m else "?",
        "departs":  _to_24h(times[0]),
        "arrives":  _to_24h(times[1]),
    }


def search(
    origin: str,
    destination: str,
    outbound_date: str,   # YYYY-MM-DD
    return_date: str,     # YYYY-MM-DD
    adults: int = 2,
    children: int = 1,
) -> list[RoundTripResult]:
    """
    Search Google Flights for nonstop round-trip options.
    Returns an empty list on any error (rate-limit, no results, etc.).
    """
    time.sleep(random.uniform(0.15, 0.45))
    try:
        tfs = TFSData.from_interface(
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
            max_stops=0,
        )
        params = {"tfs": tfs.as_b64().decode(), "hl": "en", "tfu": "EgQIABABIgA", "curr": ""}
        res = fetch(params)
    except Exception as exc:
        logger.debug("fetch %s→%s: %s", origin, destination, exc)
        return []

    try:
        parser = LexborHTMLParser(res.text)
        seen: dict[tuple, RoundTripResult] = {}
        for item in parser.css("ul.Rk10dc li"):
            link = item.css_first(".JMc5Xc")
            if not link:
                continue
            label = link.attributes.get("aria-label", "")
            parsed = _parse_aria(label)
            if not parsed or parsed["price"] <= 0:
                continue
            r = RoundTripResult(
                origin=origin,
                destination=destination,
                outbound_date=outbound_date,
                return_date=return_date,
                price_usd=parsed["price"],
                airline=parsed["airline"],
                outbound_departs=parsed["departs"],
                outbound_arrives=parsed["arrives"],
                outbound_stops=0,
            )
            # Same flight can appear in both "best" and "other" sections at different prices
            key = (parsed["airline"], parsed["departs"], parsed["arrives"])
            if key not in seen or r.price_usd < seen[key].price_usd:
                seen[key] = r
        return list(seen.values())
    except Exception as exc:
        logger.debug("parse %s→%s: %s", origin, destination, exc)
        return []
