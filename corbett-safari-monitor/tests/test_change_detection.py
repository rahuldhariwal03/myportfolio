"""Tests for availability change calculations, NULL safety, capacity updates, and 24h changes."""

from __future__ import annotations

from src.analytics import (
    ChangeDetectionService,
    calculate_slot_change,
    compute_capacity_occupied_pct,
)
from src.database.repository import SafariMonitorRepository


def test_exact_specification_example_40_to_32_to_25(repo: SafariMonitorRepository) -> None:
    """Verify exact Section 6 worked example:
    Yesterday evening = 40 -> Today morning = 32 -> Today evening = 25
    Expected: morning reduction = 8, evening reduction = 7, total daily reduction = 15.
    """
    dhikala_id = int(repo.get_zone_by_name("Dhikala")["id"])  # type: ignore[index]
    svc = ChangeDetectionService(repo, timezone_name="Asia/Kolkata")

    r1 = repo.start_collection_run("evening", "2026-12-01", "2026-12-30", "2026-12-01T19:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=r1,
        safari_date="2026-12-10",
        zone_id=dhikala_id,
        session="morning",
        available_slots=40,
        total_capacity=64,
        raw_displayed_value="40 / 64",
        confidence="verified",
        captured_at="2026-12-01T19:30:00+05:30",
    )
    repo.complete_collection_run(r1, "completed", "2026-12-01T19:33:00+05:30")
    assert svc.detect_and_record_for_run(r1) == []  # First observation has no predecessor

    r2 = repo.start_collection_run("morning", "2026-12-02", "2026-12-31", "2026-12-02T07:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=r2,
        safari_date="2026-12-10",
        zone_id=dhikala_id,
        session="morning",
        available_slots=32,
        total_capacity=64,
        raw_displayed_value="32 / 64",
        confidence="verified",
        captured_at="2026-12-02T07:30:00+05:30",
    )
    repo.complete_collection_run(r2, "completed", "2026-12-02T07:33:00+05:30")
    svc.detect_and_record_for_run(r2)

    r3 = repo.start_collection_run("evening", "2026-12-02", "2026-12-31", "2026-12-02T19:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=r3,
        safari_date="2026-12-10",
        zone_id=dhikala_id,
        session="morning",
        available_slots=25,
        total_capacity=64,
        raw_displayed_value="25 / 64",
        confidence="verified",
        captured_at="2026-12-02T19:30:00+05:30",
    )
    repo.complete_collection_run(r3, "completed", "2026-12-02T19:33:00+05:30")
    created = svc.detect_and_record_for_run(r3)
    assert len(created) == 1
    # Re-running change detection is idempotent (no duplicate event rows)
    assert svc.detect_and_record_for_run(r3) == created

    summary = svc.summarize_daily_changes(observed_date="2026-12-02")
    assert summary["morning_reduction"] == 8
    assert summary["evening_reduction"] == 7
    assert summary["daily_reduction"] == 15
    assert summary["daily_increase"] == 0
    assert summary["daily_net_change"] == -15

    # Verify rolling 24-hour comparison (40 at Dec 1 19:30 -> 25 at Dec 2 19:30)
    df_24h = svc.calculate_24h_changes()
    assert len(df_24h) == 1
    row = df_24h.iloc[0]
    assert int(row["baseline_available_24h"]) == 40
    assert int(row["current_available"]) == 25
    assert int(row["reduction_24h"]) == 15
    assert int(row["change_24h"]) == -15


def test_missing_snapshot_is_never_treated_as_zero(repo: SafariMonitorRepository) -> None:
    """Sequence 20 -> NULL (missing) -> 17 MUST report reduction = 3, never 20 or +17."""
    zone_id = int(repo.get_zone_by_name("Bijrani")["id"])  # type: ignore[index]
    svc = ChangeDetectionService(repo)

    r1 = repo.start_collection_run("morning", "2026-12-01", "2026-12-30", "2026-12-01T07:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=r1,
        safari_date="2026-12-15",
        zone_id=zone_id,
        session="morning",
        available_slots=20,
        total_capacity=30,
        captured_at="2026-12-01T07:30:00+05:30",
    )
    svc.detect_and_record_for_run(r1)

    r2 = repo.start_collection_run("evening", "2026-12-01", "2026-12-30", "2026-12-01T19:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=r2,
        safari_date="2026-12-15",
        zone_id=zone_id,
        session="morning",
        available_slots=None,
        collection_status="missing",
        confidence="not_applicable",
        error_details="DOM badge missing",
        captured_at="2026-12-01T19:30:00+05:30",
    )
    assert svc.detect_and_record_for_run(r2) == []

    r3 = repo.start_collection_run("morning", "2026-12-02", "2026-12-31", "2026-12-02T07:30:00+05:30")
    repo.record_snapshot(
        collection_run_id=r3,
        safari_date="2026-12-15",
        zone_id=zone_id,
        session="morning",
        available_slots=17,
        total_capacity=30,
        captured_at="2026-12-02T07:30:00+05:30",
    )
    svc.detect_and_record_for_run(r3)

    events = repo.list_change_events()
    assert len(events) == 1
    assert events[0]["previous_available"] == 20
    assert events[0]["current_available"] == 17
    assert events[0]["availability_reduction"] == 3
    assert events[0]["availability_increase"] == 0
    assert events[0]["change_amount"] == -3


def test_availability_increase_capacity_adjustment_and_occupancy_validation() -> None:
    # Pure missing check
    assert calculate_slot_change(None, 15) is None
    assert calculate_slot_change(15, None) is None

    # Availability increase (e.g. quota release / cancellation)
    inc = calculate_slot_change(10, 14, previous_capacity=30, current_capacity=30, current_confidence="verified")
    assert inc is not None
    assert inc.availability_increase == 4
    assert inc.availability_reduction == 0
    assert inc.net_change == 4
    assert inc.change_type == "increase"
    assert inc.capacity_occupied_pct == 53.33

    # Capacity adjustment between consecutive runs
    cap_adj = calculate_slot_change(25, 22, previous_capacity=30, current_capacity=26, current_confidence="verified")
    assert cap_adj is not None
    assert cap_adj.change_type == "capacity_changed_reduction"
    assert cap_adj.availability_reduction == 3
    assert cap_adj.capacity_occupied_pct == round((4 / 26) * 100, 2)

    # Occupancy percentage omitted when confidence is unverified or capacity missing/invalid
    assert compute_capacity_occupied_pct(15, 30, confidence="unverified") is None
    assert compute_capacity_occupied_pct(15, None, confidence="verified") is None
    assert compute_capacity_occupied_pct(35, 30, confidence="verified") is None
    assert compute_capacity_occupied_pct(0, 30, confidence="verified") == 100.0
