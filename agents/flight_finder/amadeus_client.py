"""
Alfred - Amadeus API Client
Handles authentication and communication with the Amadeus flight search API.
"""

import os
import time
import logging
from amadeus import Client, ResponseError

logger = logging.getLogger(__name__)


def get_client() -> Client:
    return Client(
        client_id=os.environ["AMADEUS_CLIENT_ID"],
        client_secret=os.environ["AMADEUS_CLIENT_SECRET"],
        hostname=os.environ.get("AMADEUS_HOSTNAME", "production"),
    )


def get_cheap_destinations(
    origin: str,
    departure_date: str,
    duration: int,
    max_price: int,
    currency: str = "USD",
) -> list[dict]:
    """
    Use Flight Inspiration Search to find all cheap destinations from an origin.
    Returns a list of destination dicts sorted by price (cheapest first).
    One API call per weekend — very efficient.
    """
    client = get_client()
    try:
        response = client.shopping.flight_destinations.get(
            origin=origin,
            departureDate=departure_date,
            duration=duration,
            maxPrice=max_price,
            currency=currency,
        )
        return response.data or []
    except ResponseError as e:
        logger.warning("Flight Inspiration Search failed for %s on %s: %s", origin, departure_date, e)
        return []


def get_flight_offers(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    adults: int = 2,
    children: int = 1,
    currency: str = "USD",
    max_results: int = 10,
) -> list[dict]:
    """
    Search for specific round-trip flight offers between two cities.
    Returns raw Amadeus flight offer objects.
    """
    client = get_client()
    try:
        time.sleep(0.2)  # gentle rate limiting
        response = client.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=departure_date,
            returnDate=return_date,
            adults=adults,
            children=children,
            currencyCode=currency,
            max=max_results,
        )
        return response.data or []
    except ResponseError as e:
        logger.warning(
            "Flight Offers Search failed %s->%s on %s: %s",
            origin, destination, departure_date, e,
        )
        return []
