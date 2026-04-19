"""
Pixel — TMDb Recommendation Engine

Strategy:
  1. For each liked movie, fetch TMDb's similar + recommendations lists
  2. Filter: age-appropriate (G/PG/TV-Y/TV-Y7), not already watched/disliked
  3. Score by: how many liked movies it's similar to + TMDb vote average
  4. Return top N, cycling through results for /more
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

TMDB_BASE    = "https://api.themoviedb.org/3"
TMDB_IMAGE   = "https://image.tmdb.org/t/p/w185"
CALM_GENRES  = {16, 10751}       # animation=16, family=10751
OK_RATINGS   = {"G", "PG", "TV-G", "TV-Y", "TV-Y7", "TV-Y7-FV", ""}
MAX_RUNTIME  = 120               # minutes — skip very long films


def _headers() -> dict:
    token = os.environ["TMDB_API_TOKEN"]
    return {"Authorization": f"Bearer {token}", "accept": "application/json"}


def _get(path: str, params: dict = {}) -> dict:
    resp = requests.get(f"{TMDB_BASE}{path}", headers=_headers(), params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _is_appropriate(tmdb_id: int) -> bool:
    """Check content rating and runtime."""
    try:
        detail = _get(f"/movie/{tmdb_id}", {"append_to_response": "release_dates"})
        # Runtime check
        if detail.get("runtime") and detail["runtime"] > MAX_RUNTIME:
            return False
        # Genre check — must have at least one calm genre
        genre_ids = {g["id"] for g in detail.get("genres", [])}
        if not genre_ids & CALM_GENRES:
            return False
        # Rating check — scan US release dates for certification
        for rd in detail.get("release_dates", {}).get("results", []):
            if rd.get("iso_3166_1") == "US":
                for r in rd.get("release_dates", []):
                    cert = r.get("certification", "")
                    if cert and cert not in OK_RATINGS:
                        return False
                break
        return True
    except Exception:
        return False


def _candidates_for(tmdb_id: int) -> list[dict]:
    """Return similar + recommended movies for one seed film."""
    out = []
    for endpoint in (f"/movie/{tmdb_id}/similar", f"/movie/{tmdb_id}/recommendations"):
        try:
            data = _get(endpoint)
            out.extend(data.get("results", []))
            time.sleep(0.1)
        except Exception:
            pass
    return out


def get_recommendations(
    liked_ids: list[int],
    disliked_ids: list[int],
    watched_ids: set[int],
    skip_ids: set[int] = set(),
    n: int = 3,
) -> list[dict]:
    """
    Return n movie recommendations as dicts with keys:
      tmdb_id, title, year, overview, poster_url, vote_average
    """
    exclude = watched_ids | set(disliked_ids) | skip_ids
    scores: dict[int, float] = {}
    meta:   dict[int, dict]  = {}

    # Gather candidates from all liked movies
    for seed_id in liked_ids[-10:]:   # limit to 10 most recent likes
        for item in _candidates_for(seed_id):
            tid = item["id"]
            if tid in exclude:
                continue
            if tid not in scores:
                scores[tid] = 0.0
                meta[tid]   = item
            scores[tid] += 1.0 + item.get("vote_average", 0) / 20

    if not scores:
        # Fallback: discover calm/family animated films
        data = _get("/discover/movie", {
            "with_genres": "16,10751",
            "sort_by": "vote_average.desc",
            "vote_count.gte": 100,
            "certification_country": "US",
            "certification.lte": "PG",
        })
        for item in data.get("results", []):
            tid = item["id"]
            if tid not in exclude:
                scores[tid] = item.get("vote_average", 0)
                meta[tid]   = item

    # Sort by score, then filter for age-appropriateness
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results = []
    checked = 0
    for tid, _ in ranked:
        if len(results) >= n:
            break
        if checked >= 40:   # don't check too many to stay fast
            break
        checked += 1
        if _is_appropriate(tid):
            m = meta[tid]
            year = (m.get("release_date") or "")[:4]
            results.append({
                "tmdb_id":      tid,
                "title":        m.get("title", "Unknown"),
                "year":         year,
                "overview":     m.get("overview", "")[:200],
                "poster_url":   TMDB_IMAGE + m["poster_path"] if m.get("poster_path") else "",
                "vote_average": round(m.get("vote_average", 0), 1),
            })
        time.sleep(0.1)

    return results
