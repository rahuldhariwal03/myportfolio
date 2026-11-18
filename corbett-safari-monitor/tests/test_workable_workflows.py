"""Tests for beginner-friendly live workflows: manual form ingestion, CSV template/import,
rendered-DOM candidate selector discovery, and system readiness checks.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.collector import (
    ManualObservationRow,
    check_system_readiness,
    discover_candidate_selectors,
    generate_observation_csv_template,
    ingest_manual_observations,
    parse_observation_csv,
)
from src.config import AppConfig
from src.database.repository import SafariMonitorRepository


def test_manual_observation_ingest_saves_live_snapshots_and_computes_changes(
    repo: SafariMonitorRepository,
) -> None:
    ist = ZoneInfo("Asia/Kolkata")

    # Morning observation: Bijrani morning=22/30, afternoon left blank (not 0!)
    res1 = ingest_manual_observations(
        repo,
        [
            ManualObservationRow(
                safari_date="2026-12-05",
                zone_name="Bijrani",
                morning_raw="22 / 30",
                afternoon_raw="",
            )
        ],
        collection_type="morning",
        captured_at=datetime(2026, 12, 1, 7, 30, tzinfo=ist),
    )
    assert res1.status == "completed"
    assert res1.snapshots_recorded == 1
    assert res1.valid_snapshots == 1
    assert res1.skipped_blank_cells == 1
    assert res1.change_events_recorded == 0

    run_row = repo.get_collection_run(res1.run_id)
    assert run_row is not None and run_row["is_demo"] == 0

    # Evening observation: Bijrani morning drops to 16/30 -> reduction = 6
    res2 = ingest_manual_observations(
        repo,
        [
            ManualObservationRow(
                safari_date="2026-12-05",
                zone_name="Bijrani",
                morning_raw="16 / 30",
                afternoon_raw="Closed",
            )
        ],
        collection_type="evening",
        captured_at=datetime(2026, 12, 1, 19, 30, tzinfo=ist),
    )
    assert res2.status == "completed"
    assert res2.snapshots_recorded == 2
    assert res2.valid_snapshots == 1
    assert res2.change_events_recorded == 1

    events = repo.list_change_events()
    assert len(events) == 1
    assert events[0]["availability_reduction"] == 6
    assert events[0]["change_amount"] == -6


def test_csv_template_roundtrip_and_invalid_cell_handling(
    repo: SafariMonitorRepository,
) -> None:
    zones = repo.list_zones(active_only=True)
    tpl = generate_observation_csv_template(
        zones, window_days=2, reference_date=date(2026, 12, 1)
    )
    # Blank template has 0 filled rows
    assert parse_observation_csv(tpl) == []

    filled_csv = (
        "safari_date,zone_name,morning_raw,afternoon_raw,morning_capacity_raw,afternoon_capacity_raw\n"
        "2026-12-01,Bijrani,18 / 30,Sold Out,,30\n"
        "2026-12-01,Jhirna,₹ 3380,14 / 30,,\n"
        "2026-12-02,Dhela,,,,\n"
    ).encode("utf-8")

    rows = parse_observation_csv(filled_csv)
    assert len(rows) == 2  # Empty Dhela row skipped cleanly

    res = ingest_manual_observations(
        repo,
        rows,
        source_section="operator_csv_import",
        captured_at=datetime(2026, 12, 1, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert res.status == "partial"  # Jhirna price flagged as parse_error, stored as NULL
    assert res.valid_snapshots == 3  # Bijrani 18, Bijrani 0 (Sold Out), Jhirna 14
    assert res.issue_cells == 1

    snaps = repo.list_snapshots_for_run(res.run_id)
    price_snap = [s for s in snaps if s["zone_name"] == "Jhirna" and s["session"] == "morning"][0]
    assert price_snap["available_slots"] is None
    assert price_snap["raw_displayed_value"] == "₹ 3380"
    assert price_snap["collection_status"] == "parse_error"


def test_dom_candidate_selector_discovery_remains_unverified_until_approved() -> None:
    sample_html = """
    <html><body>
      <div class="calendar">
        <button data-date="2026-12-01">1</button>
      </div>
      <section class="zones-list">
        <div class="zone-card" data-zone-code="BijraniZone">
          <h4 class="zone-heading">Bijrani</h4>
          <span class="morning-count">18 / 30</span>
          <span class="afternoon-count">11 / 30</span>
        </div>
        <div class="zone-card" data-zone-code="JhirnaZone">
          <h4 class="zone-heading">Jhirna</h4>
          <span class="morning-count">25 / 30</span>
          <span class="afternoon-count">Sold Out</span>
        </div>
      </section>
    </body></html>
    """
    disc = discover_candidate_selectors(sample_html)
    assert disc["found_zones_count"] == 2
    cfg = disc["suggested_config"]
    assert cfg["verified"] is False  # Never auto-marked verified without operator confirmation
    assert cfg["navigation"]["zone_card_selector"] == "div.zone-card"
    assert cfg["navigation"]["zone_name_selector"] == "h4.zone-heading"
    assert cfg["navigation"]["date_cell_template"] == "[data-date='{date}']"
    assert cfg["availability"]["morning_availability_selector"] == "span.morning-count"
    assert cfg["availability"]["afternoon_availability_selector"] == "span.afternoon-count"


def test_system_readiness_returns_all_six_checklist_items(test_config: AppConfig) -> None:
    items = check_system_readiness(test_config, live_zone_count=8)
    assert len(items) == 6
    assert items[0]["ready"] is True  # DB & 8 zones ready
    assert items[1]["ready"] is True  # Manual / CSV recording ready now
    assert items[4]["ready"] is False  # Selectors unverified until local inspect
