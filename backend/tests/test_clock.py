from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core import clock
from app.core.clock import today
from tests.helpers import make_settings

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
UTC_ZONE = ZoneInfo("UTC")


def test_today_uses_given_timezone():
    late_night_in_brazil = datetime(2026, 1, 1, 2, 30, tzinfo=UTC)

    assert today(SAO_PAULO, late_night_in_brazil) == date(2025, 12, 31)
    assert today(UTC_ZONE, late_night_in_brazil) == date(2026, 1, 1)


def test_today_follows_settings_timezone():
    moment = datetime(2026, 1, 1, 2, 30, tzinfo=UTC)

    assert today(make_settings(app_timezone="America/Sao_Paulo").timezone, moment) == date(2025, 12, 31)
    assert today(make_settings(app_timezone="Asia/Tokyo").timezone, moment) == date(2026, 1, 1)


def test_today_without_now_matches_current_date_in_timezone():
    assert today(SAO_PAULO) == datetime.now(SAO_PAULO).date()


def test_today_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        today(SAO_PAULO, datetime(2026, 1, 1, 12, 0))


@pytest.mark.parametrize(
    ("local", "utc"),
    [
        (datetime(2026, 5, 10, 23, 30, tzinfo=SAO_PAULO), datetime(2026, 5, 11, 2, 30, tzinfo=UTC)),
        (datetime(2026, 12, 31, 23, 30, tzinfo=SAO_PAULO), datetime(2027, 1, 1, 2, 30, tzinfo=UTC)),
        (datetime(2028, 2, 29, 23, 30, tzinfo=SAO_PAULO), datetime(2028, 3, 1, 2, 30, tzinfo=UTC)),
    ],
    ids=["regular-day", "new-year", "leap-day"],
)
def test_late_evening_in_sao_paulo_is_still_the_local_day(local, utc):
    assert local == utc

    assert today(SAO_PAULO, local) == local.date()
    assert today(SAO_PAULO, utc) == local.date()
    assert today(UTC_ZONE, local) == utc.date()


@pytest.mark.parametrize(
    ("utc_time", "expected"),
    [
        (datetime(2026, 5, 11, 2, 59, 59, tzinfo=UTC), date(2026, 5, 10)),
        (datetime(2026, 5, 11, 3, 0, tzinfo=UTC), date(2026, 5, 11)),
    ],
    ids=["one-second-before-local-midnight", "local-midnight"],
)
def test_day_changes_at_local_midnight(utc_time, expected):
    assert today(SAO_PAULO, utc_time) == expected


def test_today_with_timezone_ahead_of_utc():
    assert today(ZoneInfo("Asia/Tokyo"), datetime(2026, 5, 10, 15, 0, tzinfo=UTC)) == date(2026, 5, 11)


def test_now_utc_is_aware_and_in_utc():
    assert clock.now_utc().utcoffset() == timedelta(0)


def test_today_without_now_reads_now_utc(monkeypatch):
    monkeypatch.setattr(clock, "now_utc", lambda: datetime(2026, 5, 11, 2, 30, tzinfo=UTC))

    assert today(SAO_PAULO) == date(2026, 5, 10)
