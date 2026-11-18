"""Rolling monitoring window and Asia/Kolkata date utilities.

Examples for a 30-day rolling window:
- Collection on Dec 1  -> monitors Dec 1 through Dec 30  (30 dates inclusive)
- Collection on Dec 2  -> monitors Dec 2 through Dec 31  (30 dates inclusive)
- Collection on Dec 3  -> monitors Dec 3 through Jan 1   (30 dates inclusive)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class DateWindow:
    """Inclusive rolling monitoring window `[start_date, end_date]`."""

    start_date: date
    end_date: date
    window_days: int
    timezone_name: str

    @property
    def dates(self) -> list[date]:
        return [self.start_date + timedelta(days=offset) for offset in range(self.window_days)]

    @property
    def iso_dates(self) -> list[str]:
        return [d.isoformat() for d in self.dates]


def now_in_timezone(timezone_name: str = "Asia/Kolkata") -> datetime:
    """Return timezone-aware current timestamp in the configured timezone."""
    return datetime.now(ZoneInfo(timezone_name))


def to_timezone(dt: datetime, timezone_name: str = "Asia/Kolkata") -> datetime:
    """Convert a datetime (aware or naive UTC) into the configured timezone."""
    tz = ZoneInfo(timezone_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(tz)


def format_iso_timestamp(dt: datetime) -> str:
    """Serialize a timezone-aware datetime to ISO-8601 with second precision."""
    if dt.tzinfo is None:
        raise ValueError("Timestamps must be timezone-aware")
    return dt.isoformat(timespec="seconds")


def calculate_rolling_window(
    reference: date | datetime | None = None,
    window_days: int = 30,
    timezone_name: str = "Asia/Kolkata",
) -> DateWindow:
    """Calculate the inclusive rolling N-day monitoring window.

    When `reference` is a `datetime`, it is first converted to `timezone_name`
    so midnight rollovers strictly follow `Asia/Kolkata` (or the configured TZ).
    """
    if window_days < 1:
        raise ValueError(f"window_days must be >= 1, got {window_days}")

    if reference is None:
        start = now_in_timezone(timezone_name).date()
    elif isinstance(reference, datetime):
        start = to_timezone(reference, timezone_name).date()
    elif isinstance(reference, date):
        start = reference
    else:
        raise TypeError(f"Unsupported reference type: {type(reference)!r}")

    end = start + timedelta(days=window_days - 1)
    return DateWindow(
        start_date=start,
        end_date=end,
        window_days=window_days,
        timezone_name=timezone_name,
    )


def describe_safari_date(target_date: date | str) -> tuple[str, str, bool]:
    """Return `(iso_date, weekday_name, is_weekend)` for a safari date.

    Saturday (5) and Sunday (6) are marked as weekends.
    """
    d = date.fromisoformat(target_date) if isinstance(target_date, str) else target_date
    weekday_name = d.strftime("%A")
    is_weekend = d.weekday() >= 5
    return d.isoformat(), weekday_name, is_weekend


def is_within_portal_operating_hours(
    moment: datetime,
    open_time: time = time(5, 30),
    close_time: time = time(23, 30),
    timezone_name: str = "Asia/Kolkata",
) -> bool:
    """Check whether `moment` falls within the portal's published daily hours.

    Per https://corbettgov.org/faq, the online facility operates from 05:30 AM
    to 11:30 PM Asia/Kolkata daily.
    """
    local_time = to_timezone(moment, timezone_name).time().replace(tzinfo=None)
    if open_time <= close_time:
        return open_time <= local_time <= close_time
    # Handles schedules that cross midnight if configured differently later
    return local_time >= open_time or local_time <= close_time


def calculate_lead_time_days(safari_date: date | str, captured_at: date | datetime | str, timezone_name: str = "Asia/Kolkata") -> int:
    """Calculate days between observation date (in local TZ) and safari date."""
    s_date = date.fromisoformat(safari_date) if isinstance(safari_date, str) else safari_date
    if isinstance(captured_at, str):
        parsed = datetime.fromisoformat(captured_at)
        obs_date = to_timezone(parsed, timezone_name).date()
    elif isinstance(captured_at, datetime):
        obs_date = to_timezone(captured_at, timezone_name).date()
    else:
        obs_date = captured_at
    return (s_date - obs_date).days
