"""Retail event calendar shared by the data generator and the forecaster."""

import datetime as dt

DIWALI = [
    dt.date(2024, 11, 1),
    dt.date(2025, 10, 20),
    dt.date(2026, 11, 8),
    dt.date(2027, 10, 29),
]

# Weeks relative to the Diwali week that get their own seasonal factor.
EVENT_WINDOW = range(-3, 2)
NO_EVENT = -99


def week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def diwali_offsets(weeks: list[dt.date]) -> list[int]:
    """For each Monday, its offset in weeks from the Diwali week, or NO_EVENT."""
    diwali_weeks = [week_start(d) for d in DIWALI]
    offsets = []
    for w in weeks:
        nearest = min(diwali_weeks, key=lambda d: abs((w - d).days))
        offset = (w - nearest).days // 7
        offsets.append(offset if offset in EVENT_WINDOW else NO_EVENT)
    return offsets
