"""
Alfred's voice and identity.

All agent messages are framed by Alfred before delivery.
Future agents import from here to keep a consistent household tone.
"""

from datetime import datetime, timezone


NAME = "Alfred"
HOUSEHOLD = "Sherenkov"

# ── Alfred's vocabulary ───────────────────────────────────────────────────────

GREETINGS = {
    "morning": "Good morning",
    "afternoon": "Good afternoon",
    "evening": "Good evening",
}

STAFF = {
    "miles": {
        "name": "Miles",
        "title": "travel attaché",
        "task": "flight survey",
    },
    # Future staff members registered here:
    # "iris":  {"name": "Iris",  "title": "schedule keeper",   "task": "calendar management"},
    # "clara": {"name": "Clara", "title": "provisions manager", "task": "grocery & meal planning"},
}


def greeting() -> str:
    hour = datetime.now(timezone.utc).hour
    if hour < 12:
        period = "morning"
    elif hour < 18:
        period = "afternoon"
    else:
        period = "evening"
    return GREETINGS[period]


def staff_intro(agent_key: str) -> str:
    s = STAFF.get(agent_key, {"name": agent_key.title(), "title": "agent", "task": "assignment"})
    return (
        f"{s['name']} — your {s['title']} — has completed the {s['task']}.\n"
        f"Below are the opportunities identified for the {HOUSEHOLD} household."
    )


def no_results_note(agent_key: str) -> str:
    s = STAFF.get(agent_key, {"name": agent_key.title(), "task": "assignment"})
    return (
        f"{s['name']} found nothing worthy of your attention in this batch.\n"
        "The full destination list rotates every 2–3 days; "
        "promising results may appear in the next dispatch."
    )


SIGN_OFF = f"— {NAME} 🎩"
SEPARATOR = "─" * 28
