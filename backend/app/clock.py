"""The demo's single notion of "now".

Every part of the app that needs a date reads ``DEMO_TODAY`` from
:mod:`app.config` through this module: the seed's calendar, the open cycle,
the as-of instant for scoring, row timestamps such as "drafted at" and
"approved at", due-date logic and the outlook. Nothing else may call
``date.today()`` or ``datetime.now()``; ``tests/test_clock.py`` enforces it.

Using one fixed date keeps the demo reproducible: the same seed always
produces the same data, the same scores and the same screenshots.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from app.config import settings

# Every row timestamp lands at 09:00 UTC on the demo date, so ordering by
# created_at is stable within a run.
_DEMO_TIME = time(9, 0, tzinfo=timezone.utc)


def today() -> date:
    """The demo's current date, ``DEMO_TODAY`` from config."""
    return settings.demo_today


def now() -> datetime:
    """The demo's current instant, used for timestamps such as drafted_at."""
    return datetime.combine(settings.demo_today, _DEMO_TIME)


def open_cycle() -> date:
    """The open cycle is the month containing the demo date."""
    return settings.demo_today.replace(day=1)


def recent_cycles(count_closed: int = 6) -> list[date]:
    """The open cycle plus ``count_closed`` closed months before it, newest first.

    These are the months the ledger shows, so this is also the window the seed
    must cover.
    """
    months = [open_cycle()]
    start_index = months[0].year * 12 + months[0].month - 1
    for step in range(1, count_closed + 1):
        idx = start_index - step
        months.append(date(idx // 12, idx % 12 + 1, 1))
    return months
