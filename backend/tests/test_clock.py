"""The demo clock: one definition of "today", used everywhere.

``app.clock`` is the only place allowed to ask the wall clock. Everything else
reads the demo date, so the seeded ledger, the risk features and the UI all
agree on what day it is.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app import clock
from app.config import settings

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CLOCK_MODULE = APP_DIR / "clock.py"
FORBIDDEN = (
    "date.today(",
    "datetime.now(",
    "datetime.utcnow(",
    "datetime.today(",
    ".utcnow(",
)


def test_wall_clock_is_only_asked_in_app_clock() -> None:
    """No module outside app/clock.py may read the wall clock."""
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        if path == CLOCK_MODULE:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            for pattern in FORBIDDEN:
                if pattern in line:
                    rel = path.relative_to(APP_DIR.parent).as_posix()
                    offenders.append(f"{rel}:{line_no}: {line.strip()}")
    assert offenders == [], "these lines read the wall clock; use app.clock:\n" + "\n".join(offenders)


def test_demo_today_matches_the_configured_date() -> None:
    """The clock reports the configured demo date, not the real calendar."""
    assert clock.today() == settings.demo_today
    assert clock.today() == date(2026, 10, 19)


def test_now_stays_on_the_demo_date() -> None:
    """Row timestamps sit on the demo date at a fixed time of day."""
    assert clock.now().date() == clock.today()
    assert clock.now().hour == 9


def test_open_cycle_is_the_month_containing_today() -> None:
    """The open cycle is the first of the demo month."""
    assert clock.open_cycle() == clock.today().replace(day=1)


def test_recent_cycles_are_six_closed_months_then_the_open_cycle() -> None:
    """The ledger window is the open cycle plus six consecutive closed months."""
    cycles = clock.recent_cycles()
    assert len(cycles) == 7
    assert cycles[0] == clock.open_cycle()
    assert cycles[-1] == date(cycles[-1].year, cycles[-1].month, 1)
    for earlier, later in zip(cycles, cycles[1:]):
        earlier_index = earlier.year * 12 + earlier.month
        later_index = later.year * 12 + later.month
        assert earlier_index - later_index == 1, "ledger window has a gap"
