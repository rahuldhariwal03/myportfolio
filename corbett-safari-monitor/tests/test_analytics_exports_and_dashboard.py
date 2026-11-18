"""Tests for trend analytics, lead-time milestones, monitoring gaps, CSV exports,
API-ready read service, demo data safety guard, and all 5 Streamlit dashboard pages.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from streamlit.testing.v1 import AppTest

from scripts.seed_demo_data import seed_demo_database
from src.analytics import (
    CollectionMonitoringService,
    TrendAnalyticsService,
)
from src.api_ready import ReadOnlyQueryService
from src.database.repository import SafariMonitorRepository


def test_zone_table_lead_times_coverage_gaps_csv_and_read_service(
    repo: SafariMonitorRepository,
) -> None:
    bijrani_id = int(repo.get_zone_by_name("Bijrani")["id"])  # type: ignore[index]
    dhikala_id = int(repo.get_zone_by_name("Dhikala")["id"])  # type: ignore[index]

    run_id = repo.start_collection_run(
        "morning", "2026-11-18", "2026-11-20", "2026-11-18T07:30:00+05:30"
    )
    # Record lead-time milestones 30, 20, 15, 10, 5, 1 for Bijrani morning
    for lead, s_date, avail in (
        (30, "2026-12-18", 29),
        (20, "2026-12-08", 24),
        (15, "2026-12-03", 19),
        (10, "2026-11-28", 14),
        (5, "2026-11-23", 7),
        (1, "2026-11-19", 2),
    ):
        repo.record_snapshot(
            collection_run_id=run_id,
            safari_date=s_date,
            zone_id=bijrani_id,
            session="morning",
            available_slots=avail,
            total_capacity=30,
            raw_displayed_value=f"{avail} / 30",
            confidence="verified",
            captured_at="2026-11-18T07:30:00+05:30",
        )

    # Afternoon missing (NULL) on 2026-11-19 + Dhikala Canter separate unit
    repo.record_snapshot(
        collection_run_id=run_id,
        safari_date="2026-11-19",
        zone_id=bijrani_id,
        session="afternoon",
        available_slots=None,
        collection_status="missing",
        confidence="not_applicable",
        captured_at="2026-11-18T07:30:00+05:30",
    )
    repo.record_snapshot(
        collection_run_id=run_id,
        safari_date="2026-11-19",
        zone_id=dhikala_id,
        session="morning",
        available_slots=40,
        total_capacity=64,
        raw_displayed_value="40 / 64",
        confidence="verified",
        captured_at="2026-11-18T07:30:00+05:30",
    )
    repo.complete_collection_run(run_id, "partial", "2026-11-18T07:35:00+05:30")

    trends = TrendAnalyticsService(repo)
    monitor = CollectionMonitoringService(repo, stale_threshold_hours=14)
    api = ReadOnlyQueryService(repo)

    # Comparable slot totals keep Jeep permits and Canter seats strictly separated
    # Active-window-only restricts to 2026-11-18..2026-11-20 (excludes out-of-window future dates)
    win_totals = trends.get_comparable_slot_totals(active_window_only=True)
    assert win_totals["jeep_permit_slots"] == 2
    assert win_totals["canter_seat_slots"] == 40
    assert win_totals["monitored_dates_count"] == 1

    all_totals = trends.get_comparable_slot_totals(active_window_only=False)
    assert all_totals["jeep_permit_slots"] == 29 + 24 + 19 + 14 + 7 + 2
    assert all_totals["canter_seat_slots"] == 40

    # Zone availability table keeps missing Afternoon as <NA>, not 0
    tbl = trends.build_zone_availability_table(safari_date="2026-11-19", zones=["Bijrani"])
    assert len(tbl) == 1
    assert int(tbl.iloc[0]["Morning"]) == 2
    assert tbl["Afternoon"].isna().iloc[0]
    assert int(tbl.iloc[0]["Total available"]) == 2

    # CSV export writes empty cell for NULL Afternoon, never 0
    csv_text = monitor.dataframe_to_csv_bytes(tbl[["Zone", "Date", "Morning", "Afternoon"]]).decode()
    assert "Bijrani,2026-11-19,2,\n" in csv_text

    # All 6 requested lead-time milestones (30, 20, 15, 10, 5, 1) present
    lead_df = trends.compute_lead_time_summary(safari_mode="jeep_permit")
    assert list(lead_df["lead_time_days"]) == [30, 20, 15, 10, 5, 1]

    # Missing dates & missing zones detection
    gaps = monitor.detect_run_coverage_gaps(run_id)
    assert set(gaps["missing_dates"]) == {"2026-11-18", "2026-11-20"}
    assert "Jhirna" in gaps["missing_zones"]

    # Staleness detection flags old data instead of silently reporting it as current
    fresh = monitor.get_freshness_status(datetime(2026, 11, 18, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    stale = monitor.get_freshness_status(datetime(2026, 11, 19, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    assert fresh["is_stale"] is False
    assert stale["is_stale"] is True

    # Read-only future API data service
    assert len(api.get_zones()) == 8
    by_date = api.get_availability_by_date("2026-11-19")
    assert len(by_date) == 3
    hist = api.get_history(zone_name="Bijrani", session="morning")
    assert len(hist) == 6


def test_demo_seeder_refuses_to_contaminate_live_database(tmp_path: Path) -> None:
    live_url = f"sqlite:///{tmp_path / 'corbett_monitor.db'}"
    with pytest.raises(ValueError, match="Safety guard"):
        seed_demo_database(live_url, days_of_history=2, window_days=5)

    demo_url = f"sqlite:///{tmp_path / 'demo_corbett_monitor.db'}"
    summary = seed_demo_database(demo_url, days_of_history=3, window_days=5, reset=True)
    assert summary["collection_runs"] == summary["demo_runs"]
    assert summary["availability_snapshots"] > 0
    assert summary["change_events"] > 0


def test_streamlit_dashboard_renders_all_five_pages_in_demo_and_live_modes() -> None:
    """Smoke-test every single Streamlit page in both Demo and Live database modes."""
    app_path = str(Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run()
    assert not at.exception

    pages = [
        "1. Overview",
        "2. Zone-Wise Availability",
        "3. Daily Changes",
        "4. Historical Trends",
        "5. Collection Monitoring",
    ]
    # Verify all 5 pages in Demo mode
    for page_name in pages:
        at.sidebar.radio[0].set_value(page_name).run()
        assert not at.exception, f"Exception on {page_name} (Demo): {at.exception}"

    # Switch to clean Live Database (0 fake snapshots) and verify all 5 pages render cleanly
    at.sidebar.radio[1].set_value("Live Database (Real Only)").run()
    assert not at.exception
    for page_name in pages:
        at.sidebar.radio[0].set_value(page_name).run()
        assert not at.exception, f"Exception on {page_name} (Live): {at.exception}"
