#!/usr/bin/env python3
"""Generate clearly labeled [DEMO] sample test records in an ISOLATED database.

IMPORTANT:
- This script NEVER writes into your live database (`data/corbett_monitor.db`).
- It writes ONLY into `DEMO_DATABASE_URL` (`data/demo_corbett_monitor.db`) and marks
  every run with `is_demo = 1` and `collection_type` in `{'demo_morning', 'demo_evening'}`.
- Purpose: Verify Phase 2 schema constraints, Phase 5 change detection (reductions,
  increases, NULL handling, capacity adjustments, 24h deltas), lead-time milestones
  (30, 20, 15, 10, 5, 1 days), and all 5 Streamlit dashboard pages before live data
  accumulates over weeks.

Usage:
    python scripts/seed_demo_data.py --reset
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import ChangeDetectionService
from src.config import load_config
from src.database import SafariMonitorRepository, create_backend, initialize_schema
from src.date_window import calculate_rolling_window, format_iso_timestamp, now_in_timezone

# Illustrative demo capacities for testing the analytics engine (explicitly marked as [DEMO]).
DEMO_ZONE_PROFILES: dict[str, dict[str, int | float]] = {
    "Bijrani": {"capacity": 30, "demand": 1.35},
    "Jhirna": {"capacity": 30, "demand": 1.05},
    "Dhela": {"capacity": 15, "demand": 0.90},
    "Garjia": {"capacity": 30, "demand": 1.15},
    "Durgadevi": {"capacity": 11, "demand": 0.80},
    "Sonanadi": {"capacity": 15, "demand": 0.65},
    "Pakhro": {"capacity": 12, "demand": 0.55},
    "Dhikala": {"capacity": 64, "demand": 1.45},  # 4 canters x 16 seats (distinct unit!)
}


def seed_demo_database(
    demo_database_url: str,
    *,
    timezone_name: str = "Asia/Kolkata",
    days_of_history: int = 8,
    window_days: int = 30,
    reset: bool = False,
    seed: int = 20261118,
) -> dict[str, int]:
    """Populate the isolated demo database with deterministic multi-day rolling observations."""
    if not demo_database_url.startswith("sqlite:///"):
        raise ValueError("seed_demo_data only supports a local SQLite DEMO_DATABASE_URL")

    db_file = Path(demo_database_url[len("sqlite:///") :])
    if "demo" not in db_file.name.lower():
        raise ValueError(
            f"Safety guard: refusing to write demo records to non-demo filename {db_file.name!r}"
        )

    if reset and db_file.exists():
        for candidate in (
            db_file,
            Path(f"{db_file}-wal"),
            Path(f"{db_file}-shm"),
            Path(f"{db_file}-journal"),
        ):
            if candidate.exists():
                candidate.unlink()

    backend = create_backend(demo_database_url)
    initialize_schema(backend, seed_official_zones=True)
    repo = SafariMonitorRepository(backend, timezone_name=timezone_name)
    existing = repo.get_database_summary()
    if existing["collection_runs"] > 0:
        return existing

    rng = random.Random(seed)
    tz = ZoneInfo(timezone_name)
    now_local = now_in_timezone(timezone_name)
    today = now_local.date()
    first_obs_day = today - timedelta(days=days_of_history - 1)

    zones = repo.list_zones(active_only=True)
    change_service = ChangeDetectionService(repo, timezone_name=timezone_name)

    # Maintain evolving synthetic slot levels per (safari_date, zone_name, session)
    slot_state: dict[tuple[str, str, str], int] = {}

    # Build chronological list of past-only demo collection runs (never future-dated)
    planned_slots: list[tuple[int, datetime, str, str]] = []
    for day_idx in range(days_of_history):
        obs_day = first_obs_day + timedelta(days=day_idx)
        for run_slot, run_clock, run_type in (
            ("morning", time(7, 30), "demo_morning"),
            ("evening", time(19, 30), "demo_evening"),
        ):
            candidate_dt = datetime.combine(obs_day, run_clock, tzinfo=tz)
            if candidate_dt <= now_local:
                planned_slots.append((day_idx, candidate_dt, run_slot, run_type))

    # Identify the latest day that has BOTH morning and evening runs for the 40->32->25 demo
    last_complete_day_idx = max(
        (
            d_idx
            for d_idx in range(1, days_of_history)
            if sum(1 for item in planned_slots if item[0] == d_idx) == 2
        ),
        default=days_of_history - 2,
    )
    last_planned_idx = len(planned_slots) - 1

    blocked_inserted = False
    for seq_idx, (day_idx, run_start, run_slot, run_type) in enumerate(planned_slots):
        obs_day = run_start.date()
        window = calculate_rolling_window(obs_day, window_days=window_days, timezone_name=timezone_name)

        # Inject one realistic paused/blocked run mid-week to demonstrate Page 5 monitoring
        if day_idx == 3 and run_slot == "morning" and not blocked_inserted:
            blocked_inserted = True
            blocked_start = datetime.combine(obs_day, time(7, 15), tzinfo=tz)
            blocked_end = blocked_start + timedelta(seconds=18)
            blocked_run_id = repo.start_collection_run(
                collection_type="demo_morning",
                date_window_start=window.start_date,
                date_window_end=window.end_date,
                started_at=blocked_start,
                is_demo=True,
                source_url="[DEMO] https://safari.corbettgov.org/",
            )
            repo.log_collection_event(
                collection_run_id=blocked_run_id,
                page_or_zone="portal_entry",
                status="portal_paused",
                error_message=(
                    "[DEMO] Portal displayed: 'All bookings have been paused by the department! "
                    "The system is undergoing scheduled updates.'"
                ),
                logged_at=blocked_end,
            )
            repo.complete_collection_run(
                blocked_run_id,
                status="blocked",
                completed_at=blocked_end,
                error_summary="[DEMO] Department scheduled maintenance overlay detected; aborted safely.",
            )
            continue

        is_final_run = seq_idx == last_planned_idx
        with backend.transaction():
            run_id = repo.start_collection_run(
                collection_type=run_type,
                date_window_start=window.start_date,
                date_window_end=window.end_date,
                started_at=run_start,
                is_demo=True,
                source_url="[DEMO] https://safari.corbettgov.org/",
            )

            had_issue = False
            issue_messages: list[str] = []

            for offset, s_date in enumerate(window.dates):
                iso_date = s_date.isoformat()
                is_weekend = s_date.weekday() >= 5
                lead_days = (s_date - obs_day).days
                capture_ts = run_start + timedelta(seconds=offset * 5)

                for zone in zones:
                    z_id = int(zone["id"])
                    z_name = str(zone["zone_name"])
                    profile = DEMO_ZONE_PROFILES[z_name]
                    base_cap = int(profile["capacity"])
                    demand_factor = float(profile["demand"])
                    unit_word = "seats" if zone["safari_mode"] == "canter_seat" else "permits"

                    # Demonstrate a validated capacity adjustment on Jhirna on the final run
                    effective_cap = base_cap
                    if z_name == "Jhirna" and s_date == today + timedelta(days=9) and is_final_run:
                        effective_cap = 28

                    for session in ("morning", "afternoon"):
                        key = (iso_date, z_name, session)

                        if key not in slot_state:
                            session_boost = 1.15 if session == "morning" else 0.88
                            weekend_boost = 1.32 if is_weekend else 0.85
                            lead_ratio = min(1.0, max(0.0, (31 - lead_days) / 31.0))
                            occupied_frac = min(
                                1.0,
                                lead_ratio * 0.62 * demand_factor * session_boost * weekend_boost
                                + rng.uniform(-0.04, 0.06),
                            )
                            occupied_frac = max(0.0, occupied_frac)
                            initial_avail = int(round(effective_cap * (1.0 - occupied_frac)))
                            slot_state[key] = max(0, min(effective_cap, initial_avail))
                        else:
                            prev_val = slot_state[key]
                            urgency = (
                                1.45 if lead_days <= 7 else (1.1 if lead_days <= 15 else 0.65)
                            )
                            weekend_mult = 1.35 if is_weekend else 0.9
                            session_mult = 1.15 if session == "morning" else 0.9
                            expected_drop = (
                                0.48 * demand_factor * urgency * weekend_mult * session_mult
                            )
                            if zone["safari_mode"] == "canter_seat":
                                expected_drop *= 2.1

                            roll = rng.random()
                            if roll < 0.04 and prev_val + 2 <= effective_cap:
                                delta = rng.choice([1, 2, 3])
                            elif roll < 0.44:
                                delta = -max(
                                    0, int(round(rng.uniform(0.3, 1.5) * expected_drop))
                                )
                            else:
                                delta = 0

                            slot_state[key] = max(0, min(effective_cap, prev_val + delta))

                        # Textbook 40 -> 32 -> 25 example on Dhikala (today + 5, morning)
                        target_example_date = (today + timedelta(days=5)).isoformat()
                        if (
                            z_name == "Dhikala"
                            and iso_date == target_example_date
                            and session == "morning"
                        ):
                            if day_idx == last_complete_day_idx - 1 and run_slot == "evening":
                                slot_state[key] = 40
                            elif day_idx == last_complete_day_idx and run_slot == "morning":
                                slot_state[key] = 32
                            elif day_idx == last_complete_day_idx and run_slot == "evening":
                                slot_state[key] = 25

                        # Deliberate missing/NULL records on final run (stored as NULL, never 0)
                        if (
                            is_final_run
                            and z_name == "Pakhro"
                            and s_date in {today + timedelta(days=12), today + timedelta(days=13)}
                            and session == "afternoon"
                        ):
                            had_issue = True
                            msg = (
                                f"[DEMO] Afternoon badge did not load within timeout "
                                f"for Pakhro ({iso_date})"
                            )
                            issue_messages.append(msg)
                            repo.record_snapshot(
                                collection_run_id=run_id,
                                safari_date=iso_date,
                                zone_id=z_id,
                                session=session,
                                available_slots=None,
                                total_capacity=None,
                                raw_displayed_value=None,
                                raw_capacity_value=None,
                                collection_status="missing",
                                confidence="not_applicable",
                                source_section="demo_calendar_zone_card",
                                error_details=msg,
                                date_operating_status="partial",
                                captured_at=capture_ts,
                            )
                            repo.log_collection_event(
                                collection_run_id=run_id,
                                page_or_zone=f"Pakhro / {iso_date} / afternoon",
                                status="missing",
                                error_message=msg,
                                logged_at=capture_ts,
                            )
                            continue

                        avail = min(slot_state[key], effective_cap)
                        slot_state[key] = avail
                        raw_text = (
                            f"[DEMO] Full (0 / {effective_cap} {unit_word})"
                            if avail == 0
                            else f"[DEMO] {avail} / {effective_cap} {unit_word} available"
                        )
                        repo.record_snapshot(
                            collection_run_id=run_id,
                            safari_date=iso_date,
                            zone_id=z_id,
                            session=session,
                            available_slots=avail,
                            total_capacity=effective_cap,
                            raw_displayed_value=raw_text,
                            raw_capacity_value=f"[DEMO] {effective_cap}",
                            collection_status="success",
                            confidence="verified",
                            source_section="demo_calendar_zone_card",
                            error_details=None,
                            date_operating_status="open",
                            captured_at=capture_ts,
                        )

            events_created = change_service.detect_and_record_for_run(run_id)
            run_end = run_start + timedelta(minutes=3, seconds=10)
            final_status = "partial" if had_issue else "completed"
            summary_msg = (
                f"[DEMO] Partial run: {len(issue_messages)} missing cell(s) stored as NULL."
                if had_issue
                else None
            )
            repo.log_collection_event(
                collection_run_id=run_id,
                page_or_zone="run_summary",
                status="ok" if not had_issue else "partial",
                error_message=(
                    f"[DEMO] Recorded window {window.start_date}..{window.end_date} "
                    f"({len(events_created)} change comparisons computed)."
                ),
                logged_at=format_iso_timestamp(run_end),
            )
            repo.complete_collection_run(
                run_id,
                status=final_status,
                completed_at=run_end,
                error_summary=summary_msg,
            )

    return repo.get_database_summary()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed isolated [DEMO] sample test records into demo_corbett_monitor.db."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Recreate demo_corbett_monitor.db from scratch before seeding.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=8,
        help="Number of historical collection days to simulate (default: 8).",
    )
    args = parser.parse_args()

    config = load_config()
    config.ensure_directories()
    summary = seed_demo_database(
        config.demo_database_url,
        timezone_name=config.timezone_name,
        days_of_history=args.days,
        window_days=config.monitoring_window_days,
        reset=args.reset,
    )
    print(f"[DEMO] Sample dataset ready in isolated file: {config.demo_database_url}")
    print("       (Live database was NOT touched.)")
    for table_name, count in summary.items():
        print(f"  - {table_name:24s}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
