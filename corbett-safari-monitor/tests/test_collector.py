"""Tests for the compliant collector workflow: gates, unverified selectors, retries,
partial failures with diagnostic screenshots, and end-to-end snapshot + change recording.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.collector import (
    PageInspectionState,
    RawZoneCard,
    SafariAvailabilityCollector,
    SelectorConfig,
)
from src.config import AppConfig
from src.database.repository import SafariMonitorRepository


def _verified_selectors() -> SelectorConfig:
    return SelectorConfig(
        verified=True,
        verified_at="2026-11-18T10:00:00+05:30",
        verified_by="test_suite",
        unit_validated=True,
        capacity_displayed_on_portal=True,
        tourist_instructions_close="",
        important_info_acknowledge="",
        date_picker_trigger=".calendar-open",
        date_cell_template="[data-date='{date}']",
        date_url_template="",
        date_status_selector=".date-status",
        zone_card_selector=".zone-card",
        zone_name_selector=".zone-title",
        zone_id_attribute="data-zone-id",
        zone_expand_selector="",
        morning_availability_selector=".morning-slots",
        morning_capacity_selector=".morning-cap",
        afternoon_availability_selector=".afternoon-slots",
        afternoon_capacity_selector=".afternoon-cap",
        source_section_label="test_calendar_grid",
    )


class StubBrowserDriver:
    """Deterministic browser stub replicating portal gates, transient errors, and visible cards."""

    def __init__(
        self,
        *,
        entry_text: str = "Corbett Safari Availability Calendar",
        cards_by_date: dict[str, list[RawZoneCard]] | None = None,
        fail_once_on_open: bool = False,
        fail_always_dates: set[str] | None = None,
    ) -> None:
        self.entry_text = entry_text
        self.cards_by_date = cards_by_date or {}
        self.fail_once_on_open = fail_once_on_open
        self.fail_always_dates = fail_always_dates or set()
        self._current_date: str | None = None
        self.open_attempts = 0
        self.closed = False

    def open_portal(self, url: str) -> PageInspectionState:
        self.open_attempts += 1
        if self.fail_once_on_open and self.open_attempts == 1:
            raise TimeoutError("Temporary portal timeout")
        return PageInspectionState(
            url=url, http_status=200, visible_text=self.entry_text, html=f"<p>{self.entry_text}</p>"
        )

    def dismiss_consent_if_visible(self, selector: str) -> bool:
        return False

    def select_date(
        self, iso_date: str, selectors: SelectorConfig
    ) -> tuple[PageInspectionState, str | None]:
        if iso_date in self.fail_always_dates:
            raise RuntimeError(f"Calendar cell error for {iso_date}")
        self._current_date = iso_date
        return (
            PageInspectionState(
                url=f"https://safari.corbettgov.org/?date={iso_date}",
                http_status=200,
                visible_text=f"Availability for {iso_date}",
                html="<div>OK</div>",
            ),
            "open",
        )

    def read_zone_cards(self, selectors: SelectorConfig) -> list[RawZoneCard]:
        assert self._current_date is not None
        return self.cards_by_date.get(self._current_date, [])

    def capture_screenshot(self, target_path: Path) -> str | None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Minimal valid 1x1 PNG header bytes for screenshot diagnostic verification
        target_path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return str(target_path)

    def close(self) -> None:
        self.closed = True


def test_collector_stops_without_bypass_on_location_gate_and_saves_screenshot(
    test_config: AppConfig, repo: SafariMonitorRepository
) -> None:
    driver = StubBrowserDriver(
        entry_text=(
            "Location verification required. To protect your account and meet regulatory "
            "requirements, we must verify your location before you can continue."
        )
    )
    collector = SafariAvailabilityCollector(
        test_config,
        repo,
        driver_factory=lambda: driver,
        selector_config=_verified_selectors(),
        sleep_fn=lambda _: None,
    )
    res = collector.run(
        "morning",
        reference_time=datetime(2026, 12, 1, 7, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert res.status == "blocked"
    assert res.snapshots_recorded == 0
    assert driver.closed is True

    logs = repo.list_collection_logs(collection_run_id=res.run_id)
    assert any(l["status"] == "location_verification_required" for l in logs)
    shot_paths = [l["screenshot_path"] for l in logs if l["screenshot_path"]]
    assert len(shot_paths) == 1
    assert Path(shot_paths[0]).exists()


def test_collector_refuses_unverified_selectors_and_outside_operating_hours(
    test_config: AppConfig, repo: SafariMonitorRepository
) -> None:
    # Outside operating hours (02:00 IST)
    collector = SafariAvailabilityCollector(
        test_config,
        repo,
        driver_factory=lambda: StubBrowserDriver(),
        sleep_fn=lambda _: None,
    )
    night_res = collector.run(
        "manual",
        reference_time=datetime(2026, 12, 1, 2, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert night_res.status == "blocked"
    assert "operating hours" in (night_res.error_summary or "")

    # Inside operating hours, but selectors.json does not exist / unverified -> blocks cleanly
    day_res = collector.run(
        "manual",
        reference_time=datetime(2026, 12, 1, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert day_res.status == "blocked"
    assert "verified: false" in (day_res.error_summary or "")


def test_collector_recovers_from_retry_handles_partial_errors_and_preserves_history(
    test_config: AppConfig, repo: SafariMonitorRepository
) -> None:
    ist = ZoneInfo("Asia/Kolkata")
    # Run 1: transient failure on entry (recovered on retry), full 3-day window succeeds
    cards_run1 = {
        d: [
            RawZoneCard("Bijrani", "BijraniZone", "20 / 30", "30", "15 / 30", "30"),
        ]
        for d in ("2026-12-01", "2026-12-02", "2026-12-03")
    }
    driver1 = StubBrowserDriver(cards_by_date=cards_run1, fail_once_on_open=True)
    c1 = SafariAvailabilityCollector(
        test_config,
        repo,
        driver_factory=lambda: driver1,
        selector_config=_verified_selectors(),
        sleep_fn=lambda _: None,
    )
    r1 = c1.run("morning", reference_time=datetime(2026, 12, 1, 7, 30, tzinfo=ist))
    assert r1.status == "completed"
    assert driver1.open_attempts == 2  # Proves automatic retry worked
    assert r1.valid_snapshots == 6

    # Run 2 (evening): 1 date fails completely, 1 session is missing (NULL), 1 has price corruption,
    # and valid slots decrease -> marks run `partial`, preserves Run 1 + valid Run 2 + changes!
    cards_run2 = {
        "2026-12-01": [
            RawZoneCard("Bijrani", "BijraniZone", "14 / 30", "30", "--", "30"),
        ],
        "2026-12-03": [
            RawZoneCard("Bijrani", "BijraniZone", "18 / 30", "30", "₹ 3380", "30"),
        ],
    }
    driver2 = StubBrowserDriver(cards_by_date=cards_run2, fail_always_dates={"2026-12-02"})
    c2 = SafariAvailabilityCollector(
        test_config,
        repo,
        driver_factory=lambda: driver2,
        selector_config=_verified_selectors(),
        sleep_fn=lambda _: None,
    )
    r2 = c2.run("evening", reference_time=datetime(2026, 12, 1, 19, 30, tzinfo=ist))
    assert r2.status == "partial"
    assert r2.snapshots_recorded == 4
    assert r2.valid_snapshots == 2
    assert r2.change_events_recorded == 2  # Only the 2 valid series compared (missing & price skipped!)

    snaps_r2 = repo.list_snapshots_for_run(r2.run_id)
    by_key = {(s["safari_date"], s["session"]): s for s in snaps_r2}
    assert by_key[("2026-12-01", "afternoon")]["available_slots"] is None
    assert by_key[("2026-12-01", "afternoon")]["collection_status"] == "missing"
    assert by_key[("2026-12-03", "afternoon")]["available_slots"] is None
    assert by_key[("2026-12-03", "afternoon")]["collection_status"] == "parse_error"
    assert by_key[("2026-12-03", "afternoon")]["raw_displayed_value"] == "₹ 3380"

    # Run 1 snapshots remain untouched
    assert len(repo.list_snapshots_for_run(r1.run_id)) == 6
