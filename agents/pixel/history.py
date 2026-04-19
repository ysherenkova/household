"""
Pixel — Watch History
Persists the family's watched films + ratings to history.json.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import date

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "history.json")


@dataclass
class WatchEntry:
    tmdb_id: int
    title: str
    rating: str          # "loved" | "liked" | "disliked"
    watched_on: str      # ISO date string


def load() -> list[WatchEntry]:
    if not os.path.exists(HISTORY_FILE):
        return _seed_history()
    with open(HISTORY_FILE) as f:
        data = json.load(f)
    return [WatchEntry(**e) for e in data]


def save(history: list[WatchEntry]) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump([asdict(e) for e in history], f, indent=2)


def add(history: list[WatchEntry], tmdb_id: int, title: str, rating: str) -> list[WatchEntry]:
    # Update rating if already exists, otherwise append
    for e in history:
        if e.tmdb_id == tmdb_id:
            e.rating = rating
            save(history)
            return history
    history.append(WatchEntry(
        tmdb_id=tmdb_id,
        title=title,
        rating=rating,
        watched_on=date.today().isoformat(),
    ))
    save(history)
    return history


def watched_ids(history: list[WatchEntry]) -> set[int]:
    return {e.tmdb_id for e in history}


def liked_ids(history: list[WatchEntry]) -> list[int]:
    return [e.tmdb_id for e in history if e.rating in ("loved", "liked")]


def disliked_ids(history: list[WatchEntry]) -> list[int]:
    return [e.tmdb_id for e in history if e.rating == "disliked"]


def _seed_history() -> list[WatchEntry]:
    """Pre-populate with known watch history from the family."""
    seed = [
        WatchEntry(tmdb_id=127585, title="Peter Rabbit",          rating="loved",    watched_on="2025-01-01"),
        WatchEntry(tmdb_id=920,    title="Cars",                  rating="loved",    watched_on="2025-01-01"),
        WatchEntry(tmdb_id=39560,  title="Pokémon: The First Movie", rating="liked", watched_on="2025-01-01"),
        WatchEntry(tmdb_id=508439, title="Onward",                rating="liked",    watched_on="2025-01-01"),
        WatchEntry(tmdb_id=408728, title="Christopher Robin",     rating="disliked", watched_on="2025-01-01"),
    ]
    save(seed)
    return seed
