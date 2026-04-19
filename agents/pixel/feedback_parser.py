"""
Pixel — Feedback Parser
Extracts movie title + rating from free-text messages like:
  "we watched Moana and loved it"
  "we saw Inside Out, didn't like it"
  "watched Cars 2 - liked it"
"""

import re

# Trigger phrases that indicate a feedback message
WATCH_TRIGGERS = re.compile(
    r"\b(we\s+)?(watched|saw|seen|finished)\b",
    re.IGNORECASE,
)

# Rating keywords mapped to canonical ratings
RATING_MAP = [
    (re.compile(r"\b(loved?|amazing|fantastic|great|excellent|adored?)\b", re.IGNORECASE), "loved"),
    (re.compile(r"\b(liked?|good|enjoyed?|fine|ok|okay)\b",                 re.IGNORECASE), "liked"),
    (re.compile(r"\b(didn.?t like|disliked?|hated?|bad|boring|not good|didn.?t enjoy)\b", re.IGNORECASE), "disliked"),
]


def parse(text: str) -> tuple[str, str] | None:
    """
    Returns (title_guess, rating) or None if not a feedback message.
    title_guess is a best-effort extraction — caller should search TMDb for it.
    """
    if not WATCH_TRIGGERS.search(text):
        return None

    rating = None
    for pattern, canonical in RATING_MAP:
        if pattern.search(text):
            rating = canonical
            break
    if not rating:
        return None

    # Extract title: text between watch trigger and rating/filler words
    # Strip common filler
    cleaned = re.sub(
        r"\b(we\s+)?(watched|saw|seen|finished|and|it|the movie|the film|the cartoon)\b",
        " ", text, flags=re.IGNORECASE,
    )
    for pattern, _ in RATING_MAP:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return None

    return cleaned, rating
