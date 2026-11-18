"""Tests for rolling 30-day date windows, Asia/Kolkata timezone handling, and scheduler."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.config import AppConfig, load_config
from src.date_window import (
    calculate_lead_time_days,
    calculate_rolling_window,
    describe_safari_date,
    is_within_portal_operating_hours,
)
from src.scheduler import (
    create_scheduler,
    preview_upcoming_runs,
    validate_schedule_times,
)


def test_rolling_30_day_window_matches_spec_examples() -> None:
    """Verify exact December rolling window examples from Section 3 of the specification."""
    w1 = calculate_rolling_window(date(2026, 12, 1), window_days=30, timezone_name="Asia/Kolkata")
    assert w1.start_date == date(2026, 12, 1)
    assert w1.end_date == date(2026, 12, 30)
    assert len(w1.dates) == 30

    w2 = calculate_rolling_window(date(2026, 12, 2), window_days=30, timezone_name="Asia/Kolkata")
    assert w2.start_date == date(2026, 12, 2)
    assert w2.end_date == date(2026, 12, 31)
    assert len(w2.dates) == 30

    w3 = calculate_rolling_window(date(2026, 12, 3), window_days=30, timezone_name="Asia/Kolkata")
    assert w3.start_date == date(2026, 12, 3)
    assert w3.end_date == date(2027, 1, 1)
    assert len(w3.dates) == 30


def test_rolling_window_respects_asia_kolkata_midnight() -> None:
    """20:00 UTC on Nov 30 is 01:30 IST on Dec 1 -> window must start Dec 1."""
    utc_moment = datetime(2026, 11, 30, 20, 0, 0, tzinfo=ZoneInfo("UTC"))
    win = calculate_rolling_window(utc_moment, window_days=30, timezone_name="Asia/Kolkata")
    assert win.start_date == date(2026, 12, 1)
    assert win.end_date == date(2026, 12, 30)


def test_weekday_weekend_and_lead_time_helpers() -> None:
    iso_sat, wd_sat, wk_sat = describe_safari_date("2026-11-21")
    assert (iso_sat, wd_sat, wk_sat) == ("2026-11-21", "Saturday", True)

    iso_mon, wd_mon, wk_mon = describe_safari_date("2026-11-23")
    assert (iso_mon, wd_mon, wk_mon) == ("2026-11-23", "Monday", False)

    assert calculate_lead_time_days("2026-12-18", "2026-11-18T07:30:00+05:30") == 30
    assert calculate_lead_time_days("2026-11-19", "2026-11-18T19:30:00+05:30") == 1


def test_portal_operating_hours_guard() -> None:
    ist = ZoneInfo("Asia/Kolkata")
    assert is_within_portal_operating_hours(datetime(2026, 11, 18, 7, 30, tzinfo=ist)) is True
    assert is_within_portal_operating_hours(datetime(2026, 11, 18, 23, 30, tzinfo=ist)) is True
    assert is_within_portal_operating_hours(datetime(2026, 11, 18, 3, 15, tzinfo=ist)) is False


def test_scheduler_uses_configurable_times_and_warns_outside_hours(
    test_config: AppConfig, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("MORNING_COLLECTION_TIME", "08:15")
    monkeypatch.setenv("EVENING_COLLECTION_TIME", "20:45")
    monkeypatch.setenv("MONITORING_WINDOW_DAYS", "30")
    cfg = load_config(env_file=tmp_path / "nonexistent.env", base_dir=tmp_path)
    assert cfg.morning_collection_time == time(8, 15)
    assert cfg.evening_collection_time == time(20, 45)
    assert validate_schedule_times(cfg) == []

    ref = datetime(2026, 12, 1, 6, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    upcoming = preview_upcoming_runs(cfg, reference_time=ref)
    assert len(upcoming) == 2
    assert upcoming[0]["collection_type"] == "morning"
    assert "08:15:00" in upcoming[0]["next_run_at"]
    assert upcoming[0]["window_start"] == "2026-12-01"
    assert upcoming[0]["window_end"] == "2026-12-30"
    assert upcoming[1]["collection_type"] == "evening"
    assert "20:45:00" in upcoming[1]["next_run_at"]

    sched = create_scheduler(cfg, blocking=False)
    job_ids = {job.id for job in sched.get_jobs()}
    assert job_ids == {"morning_collection", "evening_collection"}

    bad_cfg = replace(test_config, morning_collection_time=time(4, 0))
    warnings = validate_schedule_times(bad_cfg)
    assert len(warnings) == 1
    assert "04:00" in warnings[0]
