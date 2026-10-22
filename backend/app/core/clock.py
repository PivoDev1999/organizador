from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    """Current instant, timezone-aware in UTC. The single source of "now": tests monkeypatch it."""
    return datetime.now(UTC)


def today(tz: ZoneInfo, now: datetime | None = None) -> date:
    """Current date in `tz` (services pass `settings.timezone`). `now`, handy in tests, must be aware."""
    if now is None:
        now = now_utc()
    elif now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(tz).date()
