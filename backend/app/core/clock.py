from datetime import date, datetime
from zoneinfo import ZoneInfo


def today(tz: ZoneInfo, now: datetime | None = None) -> date:
    """Current date in `tz` (services pass `settings.timezone`). `now`, handy in tests, must be aware."""
    if now is None:
        return datetime.now(tz).date()
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(tz).date()
