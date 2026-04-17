"""
Miles — Trip Window Generator

For each base weekend (Fri–Sun) in the next N weeks, generates up to 3 windows:

  1. Standard       Fri (after 17:00) → Sun (before 23:00)
  2. Long Thursday  Thu (any time)    → Sun (before 23:00)  — take 1 day off
  3. Long Monday    Fri (after 17:00) → Mon (before 23:00)  — take 1 day off

Windows that overlap with a US federal holiday are flagged so Alfred can
highlight them in the message (e.g. "Memorial Day weekend 🇺🇸").
"""

from dataclasses import dataclass
from datetime import date, timedelta


# ── 2026–2027 US Federal Holidays ────────────────────────────────────────────
# Includes "observed" shifts (holiday on Sat → observed Fri; on Sun → observed Mon).
US_HOLIDAYS: dict[date, str] = {
    # 2026
    date(2026,  1,  1): "New Year's Day",
    date(2026,  1, 19): "MLK Day",
    date(2026,  2, 16): "Presidents' Day",
    date(2026,  5, 25): "Memorial Day",
    date(2026,  7,  3): "Independence Day (observed)",   # Jul 4 is Saturday
    date(2026,  9,  7): "Labor Day",
    date(2026, 10, 12): "Columbus Day",
    date(2026, 11, 11): "Veterans Day",
    date(2026, 11, 26): "Thanksgiving",
    date(2026, 11, 27): "Day after Thanksgiving",        # widely observed
    date(2026, 12, 25): "Christmas",
    # 2027
    date(2027,  1,  1): "New Year's Day",
    date(2027,  1, 18): "MLK Day",
    date(2027,  2, 15): "Presidents' Day",
    date(2027,  5, 31): "Memorial Day",
    date(2027,  7,  5): "Independence Day (observed)",   # Jul 4 is Sunday
    date(2027,  9,  6): "Labor Day",
    date(2027, 10, 11): "Columbus Day",
    date(2027, 11, 11): "Veterans Day",
    date(2027, 11, 25): "Thanksgiving",
}


@dataclass
class TripWindow:
    # Human-readable label for the Telegram message
    label: str              # e.g. "May 22–24" or "May 21–24 (Thu off)"

    # Dates to search
    depart_date: date       # Thursday or Friday
    return_date: date       # Sunday or Monday

    # Departure constraint  (0 = any time;  17 = 17:00 or later)
    depart_after_h: int

    # Return constraint
    return_before_h: int    # 23 = before 23:00

    # Holiday info (empty string = none)
    holiday_label: str      # e.g. "Memorial Day 🇺🇸"
    window_type: str        # "standard" | "long_thu" | "long_mon"


def _holiday_on(d: date) -> str:
    """Return holiday name (with flag) if the date is a US holiday, else ''."""
    name = US_HOLIDAYS.get(d, "")
    return f"{name} 🇺🇸" if name else ""


def _fmt(d: date) -> str:
    return d.strftime("%b %d")


def get_trip_windows(num_weeks: int = 8) -> list[TripWindow]:
    """
    Return all trip windows for the next num_weeks weekends, sorted by
    departure date then window type.
    """
    today = date.today()
    days_to_friday = (4 - today.weekday()) % 7 or 7
    first_friday = today + timedelta(days=days_to_friday)

    windows: list[TripWindow] = []

    for i in range(num_weeks):
        fri = first_friday + timedelta(weeks=i)
        thu = fri - timedelta(days=1)
        sun = fri + timedelta(days=2)
        mon = fri + timedelta(days=3)

        fri_holiday = _holiday_on(fri)
        thu_holiday = _holiday_on(thu)
        mon_holiday = _holiday_on(mon)

        # 1. Standard: Fri → Sun
        h_label = fri_holiday  # Fri holiday means full day off anyway
        windows.append(TripWindow(
            label=f"{_fmt(fri)}–{_fmt(sun)}" + (f"  ·  {fri_holiday}" if fri_holiday else ""),
            depart_date=fri,
            return_date=sun,
            depart_after_h=0 if fri_holiday else 18,   # holiday Fri = fly any time; otherwise after 18:00
            return_before_h=23,
            holiday_label=h_label,
            window_type="standard",
        ))

        # 2. Long Thursday: Thu → Sun  (take Thu off, or Thu is a holiday)
        windows.append(TripWindow(
            label=(
                f"{_fmt(thu)}–{_fmt(sun)}"
                + (f"  ·  {thu_holiday}" if thu_holiday else "  ·  take Thu off")
            ),
            depart_date=thu,
            return_date=sun,
            depart_after_h=18,    # after 18:00 — fly after work even on day off
            return_before_h=23,
            holiday_label=thu_holiday,
            window_type="long_thu",
        ))

        # 3. Long Monday: Fri → Mon  (take Mon off, or Mon is a holiday)
        windows.append(TripWindow(
            label=(
                f"{_fmt(fri)}–{_fmt(mon)}"
                + (f"  ·  {mon_holiday}" if mon_holiday else "  ·  take Mon off")
            ),
            depart_date=fri,
            return_date=mon,
            depart_after_h=0 if fri_holiday else 18,   # after 18:00 on Fri
            return_before_h=23,
            holiday_label=mon_holiday,
            window_type="long_mon",
        ))

    return windows
