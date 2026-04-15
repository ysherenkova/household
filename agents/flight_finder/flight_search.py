"""
Alfred - Flight Search Logic
Finds round-trip weekend flights from Atlanta that match the family's criteria:
  - Outbound departs ATL on Friday after 17:00
  - Return arrives ATL on Sunday before 23:00
  - 2 adults + 1 child (born 08/19/2022)
  - Total price $200–$500
  - Next 8 weekends
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from amadeus_client import get_cheap_destinations, get_flight_offers

logger = logging.getLogger(__name__)

# ── Search configuration ──────────────────────────────────────────────────────
ORIGIN = "ATL"
ADULTS = 2
CHILDREN = 1          # born 08/19/2022 (child fare, needs own seat)
BUDGET_MIN = 200
BUDGET_MAX = 500
DEPART_AFTER_HOUR = 17   # outbound must leave ATL after 5 PM
ARRIVE_BEFORE_HOUR = 23  # return must arrive ATL before 11 PM
NUM_WEEKENDS = 8
TOP_DESTINATIONS_PER_WEEKEND = 10  # how many cheapest destinations to inspect in detail

# City name lookup for cleaner messages
CITY_NAMES: dict[str, str] = {
    "ATL": "Atlanta", "JFK": "New York (JFK)", "EWR": "New York (Newark)",
    "LGA": "New York (LaGuardia)", "LAX": "Los Angeles", "ORD": "Chicago",
    "MIA": "Miami", "MCO": "Orlando", "TPA": "Tampa", "BOS": "Boston",
    "DEN": "Denver", "LAS": "Las Vegas", "SFO": "San Francisco",
    "SAN": "San Diego", "SEA": "Seattle", "BNA": "Nashville",
    "MSY": "New Orleans", "AUS": "Austin", "HOU": "Houston",
    "DFW": "Dallas", "PHX": "Phoenix", "PDX": "Portland",
    "CUN": "Cancun", "SJU": "San Juan", "PHL": "Philadelphia",
    "CLT": "Charlotte", "IAD": "Washington DC", "DCA": "Washington DC",
    "BWI": "Baltimore/DC", "RSW": "Fort Myers", "FLL": "Fort Lauderdale",
    "PBI": "West Palm Beach", "SAV": "Savannah", "CHS": "Charleston",
    "MEM": "Memphis", "STL": "St. Louis", "MSP": "Minneapolis",
    "DTW": "Detroit", "CMH": "Columbus", "IND": "Indianapolis",
    "PIT": "Pittsburgh", "BUF": "Buffalo", "RIC": "Richmond",
    "RDU": "Raleigh-Durham", "GSP": "Greenville", "BHM": "Birmingham",
    "MOB": "Mobile", "NAS": "Nassau", "GCM": "Grand Cayman",
    "MBJ": "Montego Bay", "SXM": "St. Maarten", "BGI": "Barbados",
}


@dataclass
class FlightDeal:
    weekend_label: str        # e.g. "Apr 18 – Apr 20, 2025"
    friday: date
    sunday: date
    destination_code: str
    destination_name: str
    price: float
    currency: str
    airline: str
    outbound_summary: str     # e.g. "ATL 18:45 → NYC 21:10 (nonstop)"
    return_summary: str
    outbound_departs: str     # HH:MM for sorting / display
    return_arrives: str


def get_upcoming_weekends(num: int = NUM_WEEKENDS) -> list[tuple[date, date]]:
    """Return the next `num` Friday–Sunday pairs starting from next week."""
    today = date.today()
    days_to_friday = (4 - today.weekday()) % 7
    if days_to_friday == 0:
        days_to_friday = 7  # don't use today if today is Friday
    first_friday = today + timedelta(days=days_to_friday)
    return [(first_friday + timedelta(weeks=i), first_friday + timedelta(weeks=i, days=2))
            for i in range(num)]


def _parse_time(datetime_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM-DDTHH:MM:SS' → (hour, minute)."""
    time_part = datetime_str.split("T")[1]
    h, m = int(time_part[:2]), int(time_part[3:5])
    return h, m


def _format_itinerary(itinerary: dict) -> tuple[str, str, str]:
    """
    Returns (summary_string, departs_HH:MM, arrives_HH:MM) for an itinerary.
    summary_string example: 'ATL 18:45 → MIA 21:10 (nonstop)'
    """
    segments = itinerary["segments"]
    first, last = segments[0], segments[-1]

    dep_h, dep_m = _parse_time(first["departure"]["at"])
    arr_h, arr_m = _parse_time(last["arrival"]["at"])
    dep_airport = first["departure"]["iataCode"]
    arr_airport = last["arrival"]["iataCode"]
    stops = len(segments) - 1
    stop_label = "nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"

    summary = f"{dep_airport} {dep_h:02d}:{dep_m:02d} → {arr_airport} {arr_h:02d}:{arr_m:02d} ({stop_label})"
    return summary, f"{dep_h:02d}:{dep_m:02d}", f"{arr_h:02d}:{arr_m:02d}"


def _offer_matches_criteria(offer: dict, friday: date, sunday: date) -> bool:
    """
    Returns True if the offer satisfies all time + price constraints.
    Outbound must depart ATL on Friday after DEPART_AFTER_HOUR.
    Return must arrive ATL on Sunday before ARRIVE_BEFORE_HOUR.
    """
    try:
        price = float(offer["price"]["grandTotal"])
        if not (BUDGET_MIN <= price <= BUDGET_MAX):
            return False

        # Outbound: first segment departs on Friday after 17:00
        out_seg = offer["itineraries"][0]["segments"][0]
        out_dep_date = out_seg["departure"]["at"].split("T")[0]
        out_h, _ = _parse_time(out_seg["departure"]["at"])
        if out_dep_date != friday.isoformat() or out_h < DEPART_AFTER_HOUR:
            return False

        # Return: last segment arrives on Sunday before 23:00
        ret_segs = offer["itineraries"][1]["segments"]
        ret_arr = ret_segs[-1]["arrival"]["at"]
        ret_arr_date = ret_arr.split("T")[0]
        ret_h, ret_m = _parse_time(ret_arr)
        if ret_arr_date != sunday.isoformat():
            return False
        if ret_h > ARRIVE_BEFORE_HOUR or (ret_h == ARRIVE_BEFORE_HOUR and ret_m > 0):
            return False

        return True
    except (KeyError, IndexError, ValueError):
        return False


def find_deals() -> list[FlightDeal]:
    """
    Main search routine.
    Step 1: Flight Inspiration Search — 1 API call per weekend, returns all cheap destinations.
    Step 2: Flight Offers Search — detailed call for top N cheapest destinations to verify times.
    """
    weekends = get_upcoming_weekends()
    all_deals: list[FlightDeal] = []

    for friday, sunday in weekends:
        friday_str = friday.isoformat()
        sunday_str = sunday.isoformat()
        weekend_label = f"{friday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"
        logger.info("Searching weekend %s", weekend_label)

        # Step 1: inspiration search (1 call)
        inspirations = get_cheap_destinations(
            origin=ORIGIN,
            departure_date=friday_str,
            duration=2,
            max_price=BUDGET_MAX,
        )

        if not inspirations:
            logger.info("  No inspiration results for %s", weekend_label)
            continue

        # Step 2: detailed offers for top N destinations
        top_destinations = [d["destination"] for d in inspirations[:TOP_DESTINATIONS_PER_WEEKEND]]
        logger.info("  Checking %d destinations: %s", len(top_destinations), ", ".join(top_destinations))

        for dest_code in top_destinations:
            offers = get_flight_offers(
                origin=ORIGIN,
                destination=dest_code,
                departure_date=friday_str,
                return_date=sunday_str,
                adults=ADULTS,
                children=CHILDREN,
            )

            for offer in offers:
                if not _offer_matches_criteria(offer, friday, sunday):
                    continue

                out_summary, out_dep_time, _ = _format_itinerary(offer["itineraries"][0])
                ret_summary, _, ret_arr_time = _format_itinerary(offer["itineraries"][1])

                all_deals.append(FlightDeal(
                    weekend_label=weekend_label,
                    friday=friday,
                    sunday=sunday,
                    destination_code=dest_code,
                    destination_name=CITY_NAMES.get(dest_code, dest_code),
                    price=float(offer["price"]["grandTotal"]),
                    currency=offer["price"]["currency"],
                    airline=(offer.get("validatingAirlineCodes") or ["?"])[0],
                    outbound_summary=out_summary,
                    return_summary=ret_summary,
                    outbound_departs=out_dep_time,
                    return_arrives=ret_arr_time,
                ))

    # Sort: cheapest first, then by date
    all_deals.sort(key=lambda d: (d.friday, d.price))
    return all_deals
