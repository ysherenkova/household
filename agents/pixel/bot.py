"""
Household Bot — unified command router for @sherenkov_housebot

Pixel commands (movie recommendations):
  /pixel          — 3 movie/cartoon suggestions
  /pixel-more     — 3 more options
  /pixel-history  — watch log
  /help           — instructions

Miles commands (flight search):
  /miles              — standard search (nearest 2 weekends)
  /miles extended     — next 8 weekends
  /miles 2026-05-02   — specific Friday's weekend

Free text → Pixel feedback: "we watched Moana and loved it"
"""

import io
import logging
import os
import re
import time

import requests

import feedback_parser
import history as hist
import persona
import recommender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  Bot  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TELEGRAM_API  = "https://api.telegram.org/bot{token}/{method}"
GITHUB_OWNER  = "ysherenkova"
GITHUB_REPO   = "household"
GITHUB_WORKFLOW = "household-flights.yml"


# ── Telegram helpers ───────────────────────────────────────────────────────────

def _tg(method: str, **kwargs) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(
        TELEGRAM_API.format(token=token, method=method),
        json=kwargs,
        timeout=15,
    )
    return resp.json()


def _send(chat_id: int, text: str) -> None:
    _tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")


def _get_updates(offset: int) -> list[dict]:
    data = _tg("getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
    return data.get("result", [])


# ── Voice transcription ────────────────────────────────────────────────────────

def _transcribe_voice(file_id: str) -> str | None:
    """Download a Telegram voice file and transcribe it with OpenAI Whisper."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        logger.warning("OPENAI_API_KEY not set — cannot transcribe voice")
        return None

    # Step 1: get the download path from Telegram
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    info = _tg("getFile", file_id=file_id)
    file_path = info.get("result", {}).get("file_path")
    if not file_path:
        logger.error("getFile returned no file_path for %s", file_id)
        return None

    # Step 2: download the OGG audio
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = requests.get(download_url, timeout=30)
    if resp.status_code != 200:
        logger.error("Voice download failed: HTTP %d", resp.status_code)
        return None

    # Step 3: transcribe with Whisper
    import openai
    client = openai.OpenAI(api_key=openai_key)
    audio = io.BytesIO(resp.content)
    audio.name = "voice.ogg"
    try:
        result = client.audio.transcriptions.create(model="whisper-1", file=audio)
        text = result.text.strip()
        logger.info("Voice transcribed: %r", text)
        return text
    except Exception as exc:
        logger.error("Whisper transcription failed: %s", exc)
        return None


def _normalize_voice(text: str) -> str:
    """Coerce spoken commands to slash-command form for the router."""
    lower = text.lower().strip(" .,!?")
    for cmd in ("miles", "pixel", "help"):
        if lower.startswith(cmd):
            return "/" + lower
    return text


# ── TMDb search ────────────────────────────────────────────────────────────────

def _search_movie(title: str) -> dict | None:
    token = os.environ["TMDB_API_TOKEN"]
    resp = requests.get(
        "https://api.themoviedb.org/3/search/movie",
        headers={"Authorization": f"Bearer {token}", "accept": "application/json"},
        params={"query": title, "include_adult": False},
        timeout=10,
    )
    results = resp.json().get("results", [])
    return results[0] if results else None


# ── GitHub Actions trigger ─────────────────────────────────────────────────────

def _trigger_miles(args: str = "") -> bool:
    """Trigger the Miles workflow via GitHub API. Returns True on success."""
    token = os.environ.get("GHUB_PAT", "")
    if not token:
        logger.error("GHUB_PAT not set — cannot trigger Miles workflow")
        return False
    try:
        resp = requests.post(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": "main", "inputs": {"args": args.strip()}},
            timeout=10,
        )
        logger.info("GitHub dispatch: status=%d body=%s", resp.status_code, resp.text[:200])
        return resp.status_code == 204
    except Exception as exc:
        logger.error("GitHub dispatch failed: %s", exc)
        return False


# ── Command handlers ───────────────────────────────────────────────────────────

def handle_pixel(chat_id: int, session_shown: set[int], is_more: bool = False) -> None:
    history  = hist.load()
    liked    = hist.liked_ids(history)
    disliked = hist.disliked_ids(history)
    watched  = hist.watched_ids(history)

    if not liked:
        _send(chat_id, "📽 No liked movies yet — send me some feedback first!\n\n" + persona.SIGN_OFF)
        return

    _send(chat_id, "🎬 Searching for the perfect picks…")

    movies = recommender.get_recommendations(
        liked_ids=liked,
        disliked_ids=disliked,
        watched_ids=watched,
        skip_ids=session_shown,
        n=3,
    )

    if not movies:
        _send(chat_id, "😔 Couldn't find new options right now — try again later!\n\n" + persona.SIGN_OFF)
        return

    for m in movies:
        session_shown.add(m["tmdb_id"])

    _send(chat_id, persona.suggestions_message(movies, is_more=is_more))


def handle_miles(chat_id: int, text: str) -> None:
    """Parse /miles [extended | YYYY-MM-DD] and trigger GitHub Actions."""
    # Extract argument after /miles
    arg = text[len("/miles"):].strip()

    if arg.lower() == "extended":
        workflow_args = "--extended"
        scope = "extended (8 weekends)"
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", arg):
        workflow_args = f"--date {arg}"
        scope = f"weekend of {arg}"
    elif arg == "":
        workflow_args = ""
        scope = "next weekend (7+ days out)"
    else:
        _send(chat_id, (
            "✈️ <b>Miles — usage:</b>\n"
            "  /miles — nearest 2 weekends\n"
            "  /miles extended — next 8 weekends\n"
            "  /miles 2026-05-02 — specific weekend\n\n"
            "🎩 <i>Alfred</i>"
        ))
        return

    # Acknowledge immediately so the user knows we received the command
    _send(chat_id, (
        f"✈️ Got it! Miles is searching <b>{scope}</b>.\n\n"
        f"Results will arrive in a few minutes. 🎩 <i>Alfred</i>"
    ))
    logger.info("Miles: triggering workflow args=%r", workflow_args)

    ok = _trigger_miles(workflow_args)
    if ok:
        logger.info("Miles workflow triggered successfully: args=%r", workflow_args)
    else:
        _send(chat_id, (
            "⚠️ Heads up — Miles couldn't reach GitHub Actions. "
            "The search may not have started. Check logs or try again.\n\n🎩 <i>Alfred</i>"
        ))
        logger.error("Miles workflow trigger FAILED: args=%r", workflow_args)


def handle_feedback(chat_id: int, text: str) -> bool:
    parsed = feedback_parser.parse(text)
    if not parsed:
        return False

    title_guess, rating = parsed
    movie = _search_movie(title_guess)

    if not movie:
        _send(chat_id, persona.not_found_message(title_guess))
        return True

    history = hist.load()
    hist.add(history, movie["id"], movie["title"], rating)
    _send(chat_id, persona.feedback_ack(movie["title"], rating))
    logger.info("Feedback: %s → %s", movie["title"], rating)
    return True


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("Household bot online. Listening for /miles, /pixel…")
    offset = 0
    session_shown: set[int] = set()

    allowed_chats = {
        int(os.environ.get("TELEGRAM_CHAT_ID_YULIIA", 0)),
        int(os.environ.get("TELEGRAM_CHAT_ID_IVAN", 0)),
    } - {0}

    while True:
        try:
            updates = _get_updates(offset)
        except Exception as exc:
            logger.warning("getUpdates failed: %s", exc)
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            msg     = update.get("message", {})
            chat_id = msg.get("chat", {}).get("id")

            if not chat_id:
                continue
            if allowed_chats and chat_id not in allowed_chats:
                continue

            # Voice message → transcribe and route as text
            voice = msg.get("voice")
            if voice:
                logger.info("← [%s] voice message (duration=%ss)", chat_id, voice.get("duration"))
                text = _transcribe_voice(voice["file_id"])
                if text is None:
                    _send(chat_id, "🎙 Sorry, I couldn't transcribe that. Please type your request.\n\n🎩 <i>Alfred</i>")
                    continue
                _send(chat_id, f"🎙 I heard: <i>\"{text}\"</i>")
                text = _normalize_voice(text)
            else:
                text = (msg.get("text") or "").strip()

            if not text:
                continue

            logger.info("← [%s] %s", chat_id, text[:80])

            if text.startswith("/pixel-more"):
                handle_pixel(chat_id, session_shown, is_more=True)
            elif text.startswith("/pixel-history"):
                _send(chat_id, persona.history_message(hist.load()))
            elif text.startswith("/pixel"):
                handle_pixel(chat_id, session_shown)
            elif text.startswith("/miles"):
                handle_miles(chat_id, text)
            elif text.startswith("/help") or text.startswith("/start"):
                _send(chat_id, persona.help_message())
            else:
                handled = handle_feedback(chat_id, text)
                if not handled:
                    _send(chat_id, persona.help_message())


if __name__ == "__main__":
    main()
