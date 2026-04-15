"""
Alfred - Airport data loader
Pulls the live OurAirports CSV (public domain, updated nightly) and returns
every medium/large airport with scheduled service in the US + popular
international leisure destinations reachable from Atlanta.
"""

import csv
import io
import logging

import requests

logger = logging.getLogger(__name__)

# Public-domain airport dataset, updated every night by OurAirports
OURAIRPORTS_CSV = (
    "https://davidmegginson.github.io/ourairports-data/airports.csv"
)

# Countries whose airports we want as *destinations*
# (family leisure travel from Atlanta — US, Caribbean, Mexico, Canada, Central America)
DESTINATION_COUNTRIES = {
    "US",  # all 50 states + territories
    "PR",  # Puerto Rico
    "VI",  # US Virgin Islands
    "MX",  # Mexico (Cancun, Los Cabos, Puerto Vallarta, etc.)
    "CA",  # Canada
    "BS",  # Bahamas
    "JM",  # Jamaica
    "DO",  # Dominican Republic
    "BB",  # Barbados
    "TC",  # Turks & Caicos
    "KY",  # Cayman Islands
    "LC",  # St. Lucia
    "SX",  # Sint Maarten
    "AW",  # Aruba
    "BZ",  # Belize
    "CR",  # Costa Rica
    "PA",  # Panama
    "GT",  # Guatemala (Tikal etc.)
    "HN",  # Honduras (Roatan)
    "CU",  # Cuba (limited US flights)
    "HT",  # Haiti
    "TT",  # Trinidad & Tobago
}

# Airports to skip as destinations (departure-only hubs or non-leisure)
EXCLUDE_IATA = {
    "ATL",  # that's where we're leaving from
}


def load_destination_airports() -> list[dict]:
    """
    Returns a list of dicts with keys: iata_code, name, municipality, iso_country
    Sorted by country then municipality for consistent batching.
    """
    logger.info("Fetching airport list from OurAirports...")
    try:
        resp = requests.get(OURAIRPORTS_CSV, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to fetch airport data: %s", exc)
        return _fallback_airports()

    reader = csv.DictReader(io.StringIO(resp.text))
    airports = []
    seen_iata = set()

    for row in reader:
        if row.get("type") not in ("large_airport", "medium_airport"):
            continue
        if row.get("scheduled_service") != "yes":
            continue
        iata = (row.get("iata_code") or "").strip()
        if not iata or iata in seen_iata or iata in EXCLUDE_IATA:
            continue
        if row.get("iso_country") not in DESTINATION_COUNTRIES:
            continue

        seen_iata.add(iata)
        airports.append({
            "iata_code": iata,
            "name": row.get("name", ""),
            "municipality": row.get("municipality", ""),
            "iso_country": row.get("iso_country", ""),
        })

    airports.sort(key=lambda a: (a["iso_country"], a["municipality"], a["iata_code"]))
    logger.info("Loaded %d destination airports", len(airports))
    return airports


def select_batch(airports: list[dict], batch_size: int = 60) -> list[dict]:
    """
    Pick a rotating batch of airports so we don't search all 300+ at once.
    The batch rotates every run (twice per day) covering the full list in
    ~len(airports) / batch_size runs  ≈  2-3 days.
    No state file needed — offset is derived from the current UTC date + half-day.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Two runs per day → increment every 12 hours
    run_index = now.timetuple().tm_yday * 2 + (1 if now.hour >= 12 else 0)
    total = len(airports)
    if total == 0:
        return []
    start = (run_index * batch_size) % total
    end = start + batch_size
    if end <= total:
        batch = airports[start:end]
    else:
        batch = airports[start:] + airports[: end - total]
    logger.info(
        "Batch %d: airports %d–%d of %d (wraps=%s)",
        run_index, start, min(end, total), total, end > total,
    )
    return batch


def _fallback_airports() -> list[dict]:
    """
    A minimal hard-coded fallback used only if the OurAirports fetch fails.
    Covers the most popular leisure destinations from Atlanta.
    """
    fallback = [
        # Florida
        ("MIA", "Miami", "US"), ("MCO", "Orlando", "US"), ("TPA", "Tampa", "US"),
        ("FLL", "Fort Lauderdale", "US"), ("RSW", "Fort Myers", "US"),
        ("PBI", "West Palm Beach", "US"), ("JAX", "Jacksonville", "US"),
        ("EYW", "Key West", "US"), ("PNS", "Pensacola", "US"), ("VPS", "Destin", "US"),
        # Southeast
        ("BNA", "Nashville", "US"), ("MSY", "New Orleans", "US"),
        ("CHS", "Charleston", "US"), ("SAV", "Savannah", "US"),
        ("RDU", "Raleigh-Durham", "US"), ("CLT", "Charlotte", "US"),
        ("BHM", "Birmingham", "US"), ("MEM", "Memphis", "US"),
        # Northeast
        ("JFK", "New York", "US"), ("EWR", "Newark", "US"), ("LGA", "LaGuardia", "US"),
        ("BOS", "Boston", "US"), ("PHL", "Philadelphia", "US"),
        ("DCA", "Washington DC", "US"), ("IAD", "Washington Dulles", "US"),
        ("BWI", "Baltimore", "US"),
        # Midwest
        ("ORD", "Chicago O'Hare", "US"), ("MDW", "Chicago Midway", "US"),
        ("STL", "St. Louis", "US"), ("IND", "Indianapolis", "US"),
        ("CMH", "Columbus", "US"), ("CLE", "Cleveland", "US"),
        ("DTW", "Detroit", "US"), ("MSP", "Minneapolis", "US"),
        ("MKE", "Milwaukee", "US"), ("CVG", "Cincinnati", "US"),
        # West
        ("DEN", "Denver", "US"), ("LAS", "Las Vegas", "US"),
        ("LAX", "Los Angeles", "US"), ("SFO", "San Francisco", "US"),
        ("SAN", "San Diego", "US"), ("SEA", "Seattle", "US"),
        ("PHX", "Phoenix", "US"), ("PDX", "Portland", "US"),
        ("SLC", "Salt Lake City", "US"), ("AUS", "Austin", "US"),
        ("DFW", "Dallas", "US"), ("HOU", "Houston", "US"), ("SAT", "San Antonio", "US"),
        # Caribbean / Mexico
        ("CUN", "Cancun", "MX"), ("SJD", "Los Cabos", "MX"),
        ("PVR", "Puerto Vallarta", "MX"),
        ("SJU", "San Juan", "PR"), ("STT", "St. Thomas", "VI"),
        ("NAS", "Nassau", "BS"), ("MBJ", "Montego Bay", "JM"),
        ("PUJ", "Punta Cana", "DO"),
        ("GCM", "Grand Cayman", "KY"), ("BGI", "Barbados", "BB"),
    ]
    return [{"iata_code": c, "municipality": m, "iso_country": co, "name": m}
            for c, m, co in fallback]
