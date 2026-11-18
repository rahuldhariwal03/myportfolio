"""Tests for database schema, constraints, duplicate prevention, immutability, and recovery."""

from __future__ import annotations

import sqlite3

import pytest

from src.database.repository import SafariMonitorRepository


def test_schema_contains_all_six_required_tables_and_columns(
    repo: SafariMonitorRepository,
) -> None:
    expected_columns = {
        "collection_runs": {
            "id",
            "started_at",
            "completed_at",
            "collection_type",
            "date_window_start",
            "date_window_end",
            "status",
            "error_summary",
        },
        "safari_dates": {"id", "safari_date", "weekday", "is_weekend", "operating_status"},
        "zones": {"id", "zone_name", "source_zone_identifier"},
        "availability_snapshots": {
            "id",
            "collection_run_id",
            "safari_date",
            "zone_id",
            "session",
            "available_slots",
            "total_capacity",
            "raw_displayed_value",
            "collection_status",
            "confidence",
            "captured_at",
        },
        "change_events": {
            "id",
            "safari_date",
            "zone_id",
            "session",
            "previous_available",
            "current_available",
            "change_amount",
            "change_type",
            "observed_at",
        },
        "collection_logs": {
            "id",
            "collection_run_id",
            "page_or_zone",
            "status",
            "error_message",
            "screenshot_path",
        },
    }

    for table_name, req_cols in expected_columns.items():
        info = repo.backend.fetch_all(f"PRAGMA table_info({table_name})")
        actual_cols = {row["name"] for row in info}
        assert req_cols.issubset(actual_cols), f"Missing columns in {table_name}: {req_cols - actual_cols}"


def test_official_zones_seeded_without_invented_identifiers(
    repo: SafariMonitorRepository,
) -> None:
    zones = repo.list_zones(active_only=True)
    assert len(zones) == 8
    by_name = {z["zone_name"]: z for z in zones}
    # Only DhikalaZone was observed in official portal redirect; others stay NULL until verified
    assert by_name["Dhikala"]["source_zone_identifier"] == "DhikalaZone"
    assert by_name["Dhikala"]["safari_mode"] == "canter_seat"
    assert by_name["Bijrani"]["source_zone_identifier"] is None
    assert by_name["Bijrani"]["safari_mode"] == "jeep_permit"


def test_duplicate_prevention_within_run_and_preservation_across_runs(
    repo: SafariMonitorRepository,
) -> None:
    bijrani = repo.get_zone_by_name("Bijrani")
    assert bijrani is not None
    zone_id = int(bijrani["id"])

    run1 = repo.start_collection_run("morning", "2026-12-01", "2026-12-30", "2026-12-01T07:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=run1,
        safari_date="2026-12-05",
        zone_id=zone_id,
        session="morning",
        available_slots=24,
        total_capacity=30,
        raw_displayed_value="24 / 30",
        captured_at="2026-12-01T07:31:00+05:30",
    )

    # Duplicate observation for the SAME (run, date, zone, session) is blocked
    with pytest.raises(sqlite3.IntegrityError):
        repo.record_snapshot(
            collection_run_id=run1,
            safari_date="2026-12-05",
            zone_id=zone_id,
            session="morning",
            available_slots=23,
            total_capacity=30,
            raw_displayed_value="23 / 30",
            captured_at="2026-12-01T07:32:00+05:30",
        )

    # New observation in a LATER run is preserved alongside the first
    run2 = repo.start_collection_run("evening", "2026-12-01", "2026-12-30", "2026-12-01T19:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=run2,
        safari_date="2026-12-05",
        zone_id=zone_id,
        session="morning",
        available_slots=19,
        total_capacity=30,
        raw_displayed_value="19 / 30",
        captured_at="2026-12-01T19:31:00+05:30",
    )
    rows = repo.backend.fetch_all(
        "SELECT available_slots FROM availability_snapshots ORDER BY id ASC"
    )
    assert [r["available_slots"] for r in rows] == [24, 19]


def test_historical_snapshots_are_strictly_immutable(repo: SafariMonitorRepository) -> None:
    zone_id = int(repo.get_zone_by_name("Jhirna")["id"])  # type: ignore[index]
    run_id = repo.start_collection_run("morning", "2026-12-01", "2026-12-30", "2026-12-01T07:30:00+05:30")
    snap_id = repo.record_snapshot(
        collection_run_id=run_id,
        safari_date="2026-12-10",
        zone_id=zone_id,
        session="afternoon",
        available_slots=18,
        total_capacity=30,
        raw_displayed_value="18 / 30",
        captured_at="2026-12-01T07:31:00+05:30",
    )

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repo.backend.execute(
            "UPDATE availability_snapshots SET available_slots = 5 WHERE id = ?",
            (snap_id,),
        )

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repo.backend.execute("DELETE FROM availability_snapshots WHERE id = ?", (snap_id,))


def test_missing_values_stored_as_null_and_invalid_values_rejected(
    repo: SafariMonitorRepository,
) -> None:
    zone_id = int(repo.get_zone_by_name("Dhela")["id"])  # type: ignore[index]
    run_id = repo.start_collection_run("morning", "2026-12-01", "2026-12-30", "2026-12-01T07:30:00+05:30")

    snap_id = repo.record_snapshot(
        collection_run_id=run_id,
        safari_date="2026-12-11",
        zone_id=zone_id,
        session="morning",
        available_slots=None,
        total_capacity=None,
        raw_displayed_value=None,
        collection_status="missing",
        confidence="not_applicable",
        error_details="Element timed out",
        captured_at="2026-12-01T07:31:00+05:30",
    )
    saved = repo.get_snapshot(snap_id)
    assert saved is not None
    assert saved["available_slots"] is None
    assert saved["collection_status"] == "missing"

    # Reject negative slots
    with pytest.raises(ValueError, match="negative"):
        repo.record_snapshot(
            collection_run_id=run_id,
            safari_date="2026-12-12",
            zone_id=zone_id,
            session="morning",
            available_slots=-1,
            captured_at="2026-12-01T07:31:00+05:30",
        )

    # Reject available_slots exceeding total_capacity
    with pytest.raises(ValueError, match="exceed"):
        repo.record_snapshot(
            collection_run_id=run_id,
            safari_date="2026-12-13",
            zone_id=zone_id,
            session="morning",
            available_slots=20,
            total_capacity=15,
            captured_at="2026-12-01T07:31:00+05:30",
        )


def test_recover_interrupted_collection_runs(repo: SafariMonitorRepository) -> None:
    stale_id = repo.start_collection_run(
        "morning", "2026-12-01", "2026-12-30", "2026-12-01T07:30:00+05:30"
    )
    count = repo.recover_interrupted_runs()
    assert count == 1
    recovered = repo.get_collection_run(stale_id)
    assert recovered is not None
    assert recovered["status"] == "interrupted"
    assert recovered["completed_at"] is not None
