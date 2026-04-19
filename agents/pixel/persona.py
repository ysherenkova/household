"""Pixel — voice and formatting for Telegram messages."""

SIGN_OFF  = "🎬 <i>Pixel, Sherenkov family screen curator</i>"
SEPARATOR = "─" * 24

RATING_EMOJI = {"loved": "❤️", "liked": "👍", "disliked": "👎"}


def format_suggestion(idx: int, movie: dict) -> str:
    stars = "⭐" * round(movie["vote_average"] / 2)
    year  = f" ({movie['year']})" if movie["year"] else ""
    overview = movie["overview"]
    if len(overview) > 150:
        overview = overview[:147] + "..."
    return "\n".join([
        f"<b>{idx}. {movie['title']}{year}</b>  {stars}",
        f"<i>{overview}</i>",
        "",
    ])


def suggestions_message(movies: list[dict], is_more: bool = False) -> str:
    intro = "Here are 3 more options:" if is_more else "Here's what I'd suggest for tonight:"
    lines = [f"🎬 {intro}", ""]
    for i, m in enumerate(movies, 1):
        lines.append(format_suggestion(i, m))
    lines += [
        SEPARATOR,
        "Watched one? Just tell me: <i>\"we watched [title] and loved/liked/didn't like it\"</i>",
        "Want more options? Send /pixel-more",
        "",
        SIGN_OFF,
    ]
    return "\n".join(lines)


def feedback_ack(title: str, rating: str) -> str:
    emoji = RATING_EMOJI.get(rating, "👍")
    notes = {
        "loved":    "Noted with ❤️ — I'll keep that in mind for next time.",
        "liked":    "Good to know! I'll look for more like it.",
        "disliked": "Got it — I'll steer clear of similar ones.",
    }
    return f"{emoji} <b>{title}</b> — {notes.get(rating, 'Noted!')}\n\n{SIGN_OFF}"


def not_found_message(text: str) -> str:
    return (
        f"🤔 I couldn't find <b>{text}</b> in the database.\n\n"
        f"Try the full title, e.g. <i>\"we watched Toy Story and loved it\"</i>\n\n"
        f"{SIGN_OFF}"
    )


def help_message() -> str:
    return "\n".join([
        "🎩 <b>Sherenkov Household Bot</b>",
        "",
        "🎬 <b>Pixel</b> — screen curator",
        "  /pixel — 3 movie recommendations",
        "  /pixel-more — 3 more options",
        "  /pixel-history — watch log",
        "  <i>we watched Moana and loved it</i> — save feedback",
        "",
        "✈️ <b>Miles</b> — flight search",
        "  /miles — nearest 2 weekends",
        "  /miles extended — next 8 weekends",
        "  /miles 2026-05-02 — specific weekend",
        "",
        SIGN_OFF,
    ])


def history_message(history: list) -> str:
    if not history:
        return f"📽 No watch history yet.\n\n{SIGN_OFF}"
    lines = ["📽 <b>Watch history:</b>", ""]
    for e in sorted(history, key=lambda x: x.watched_on, reverse=True):
        emoji = RATING_EMOJI.get(e.rating, "•")
        lines.append(f"{emoji} {e.title}")
    lines += ["", SIGN_OFF]
    return "\n".join(lines)
