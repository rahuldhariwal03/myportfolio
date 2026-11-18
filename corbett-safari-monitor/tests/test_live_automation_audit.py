"""Regression tests for every bug & real-world edge case caught during live-automation audit."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.collector import (
    CollectorBusyError,
    PageInspectionState,
    RawZoneCard,
    ReadOnlyGuard,
    SafariAvailabilityCollector,
    SelectorConfig,
    aggregate_date_operating_status,
    discover_candidate_selectors,
    format_date_template,
    normalize_zone_name,
    parse_availability_text,
)
from src.collector.playwright_collector import _single_run_lock
from src.config import AppConfig
from src.database.repository import SafariMonitorRepository

IST = ZoneInfo("Asia/Kolkata")


def test_selector_config_blocks_missing_date_navigation_so_single_date_is_never_duplicated() -> None:
    """Fix #3: Never loop 30 times over the same static date when date selectors are blank."""
    cfg = SelectorConfig(
        verified=True,
        verified_at="2026-11-18T08:00:00+05:30",
        verified_by="operator",
        unit_validated=True,
        capacity_displayed_on_portal=False,
        tourist_instructions_close="",
        important_info_acknowledge="",
        date_picker_trigger="",
        date_cell_template="",  # Missing!
        date_url_template="",   # Missing!
        zone_card_selector=".zone-card",
        zone_name_selector=".zone-name",
        morning_availability_selector=".morning",
        afternoon_availability_selector=".afternoon",
    )
    ok, reason = cfg.validate_for_collection()
    assert ok is False
    assert reason is not None
    assert "date navigation" in reason.lower()


def test_format_date_template_supports_iso_indian_and_aria_calendar_formats() -> None:
    """Fix #2: Calendar selectors handle ISO, DD-MM-YYYY, DD/MM/YYYY, and aria-label formats."""
    assert format_date_template("[data-date='{date}']", "2026-12-05") == "[data-date='2026-12-05']"
    assert format_date_template("[data-day='{dmy}']", "2026-12-05") == "[data-day='05-12-2026']"
    assert format_date_template("[title='{dmy_slash}']", "2026-12-05") == "[title='05/12/2026']"
    assert (
        format_date_template(".flatpickr-day[aria-label='{aria_date}']", "2026-12-05")
        == ".flatpickr-day[aria-label='December 5, 2026']"
    )
    assert (
        format_date_template("button[aria-label*='{short_aria_date}']", "2026-12-05")
        == "button[aria-label*='Dec 5, 2026']"
    )
    assert (
        format_date_template(
            "https://safari.corbettgov.org/?eventName={zone_id}&date={date}",
            "2026-12-05",
            zone_id="DhikalaZone",
        )
        == "https://safari.corbettgov.org/?eventName=DhikalaZone&date=2026-12-05"
    )


def test_read_only_guard_allows_booking_domain_availability_reads_but_blocks_mutations() -> None:
    """Fix #6: Hostname `booking.corbettgov.org` and read-only availability fetches must work."""
    # Legitimate read-only availability calls MUST be allowed
    assert ReadOnlyGuard.should_block_network_request(
        "https://booking.corbettgov.org/api/v1/availability?date=2026-11-20", "GET"
    ) is False
    assert ReadOnlyGuard.should_block_network_request(
        "https://safari.corbettgov.org/api/permits/availability", "POST"
    ) is False
    assert ReadOnlyGuard.should_block_network_request(
        "https://booking.corbettgov.org/api/calendar/slots", "POST"
    ) is False

    # Booking, cart, hold, OTP, passenger, and payment calls MUST ALWAYS be blocked
    assert ReadOnlyGuard.should_block_network_request(
        "https://safari.corbettgov.org/api/book-ticket", "POST"
    ) is True
    assert ReadOnlyGuard.should_block_network_request(
        "https://booking.corbettgov.org/api/orders/create", "POST"
    ) is True
    assert ReadOnlyGuard.should_block_network_request(
        "https://safari.corbettgov.org/api/send-otp", "POST"
    ) is True
    assert ReadOnlyGuard.should_block_network_request(
        "https://api.razorpay.com/v1/checkout", "GET"
    ) is True
    assert ReadOnlyGuard.should_block_network_request(
        "https://safari.corbettgov.org/api/cart/add", "POST"
    ) is True
    assert ReadOnlyGuard.should_block_network_request(
        "https://safari.corbettgov.org/api/passenger/save", "POST"
    ) is True


def test_parser_handles_real_portal_labels_and_rejects_indian_slash_dates() -> None:
    """Fix #7: Real portal slot formats parse cleanly; slash dates & 'Not Available' stay NULL."""
    # Real labeled strings
    assert parse_availability_text("Morning: 18 Available", unit_validated=True).available_slots == 18
    assert parse_availability_text("Afternoon - 12 Tickets Left", unit_validated=True).available_slots == 12
    assert parse_availability_text("Available (9)", unit_validated=True).available_slots == 9
    assert parse_availability_text("Only 4 left!", unit_validated=True).available_slots == 4
    assert parse_availability_text("Sold Out!", unit_validated=True).available_slots == 0
    assert parse_availability_text("No tickets available", unit_validated=True).available_slots == 0

    # Slash & hyphen dates MUST NOT be misread as fraction slot counts (e.g. 05/12)
    slash_date = parse_availability_text("05/12/2026", unit_validated=True)
    assert slash_date.available_slots is None
    assert slash_date.collection_status == "parse_error"

    dmy_date = parse_availability_text("18-11-2026", unit_validated=True)
    assert dmy_date.available_slots is None
    assert dmy_date.collection_status == "parse_error"

    # Ambiguous "Not Available" MUST stay NULL (never coerced to 0)
    na = parse_availability_text("Not Available", unit_validated=True)
    assert na.available_slots is None
    assert na.collection_status == "missing"


def test_zone_alias_normalization_duplicate_card_guard_and_date_status_aggregation(
    repo: SafariMonitorRepository, test_config: AppConfig
) -> None:
    """Fixes #5 & #8: Aliases map to canonical zones, duplicate cards skip, date stays partial."""
    assert normalize_zone_name("Bijrani Zone") == "Bijrani"
    assert normalize_zone_name("Garjiya") == "Garjia"
    assert normalize_zone_name("Durga Devi Zone") == "Durgadevi"
    assert normalize_zone_name("DhikalaZone") == "Dhikala"
    assert normalize_zone_name("Dhikala Canter Safari") == "Dhikala"

    assert aggregate_date_operating_status(["success", "success"]) == "open"
    assert aggregate_date_operating_status(["success", "zone_closed"]) == "partial"
    assert aggregate_date_operating_status(["zone_closed", "zone_closed"]) == "closed"

    class _AliasAndDupDriver:
        def open_portal(self, url: str) -> PageInspectionState:
            return PageInspectionState(url, 200, "Safari Calendar", "<div>Safari</div>")

        def dismiss_consent_if_visible(self, selector: str) -> bool:
            return False

        def select_date(self, iso_date: str, selectors: SelectorConfig):
            return PageInspectionState("https://safari.corbettgov.org/", 200, iso_date, ""), "open"

        def read_zone_cards(self, selectors: SelectorConfig) -> list[RawZoneCard]:
            return [
                RawZoneCard("Garjiya Zone", None, "Morning: 15 Available", None, "10", None),
                # Responsive mobile duplicate of same zone — must NOT crash with IntegrityError!
                RawZoneCard("Garjia", None, "Morning: 15 Available", None, "10", None),
                RawZoneCard("Durga Devi", None, "8 Tickets Left", None, "Sold Out!", None),
                # Closed zone LAST — must NOT overwrite whole date status to 'closed'!
                RawZoneCard("Pakhro Zone", None, "Closed", None, "Closed", None),
            ]

        def capture_screenshot(self, target_path: Path) -> str | None:
            return None

        def close(self) -> None:
            pass

    selectors = SelectorConfig(
        verified=True,
        verified_at="2026-11-18T08:00:00+05:30",
        verified_by="operator",
        unit_validated=True,
        capacity_displayed_on_portal=False,
        tourist_instructions_close="",
        important_info_acknowledge="",
        date_picker_trigger="",
        date_cell_template="[data-date='{date}']",
        zone_card_selector=".card",
        zone_name_selector=".name",
        morning_availability_selector=".m",
        afternoon_availability_selector=".a",
    )
    collector = SafariAvailabilityCollector(
        test_config,
        repo,
        driver_factory=_AliasAndDupDriver,
        selector_config=selectors,
        sleep_fn=lambda _: None,
    )
    res = collector.run(
        "manual",
        reference_time=datetime(2026, 11, 18, 9, 0, tzinfo=IST),
        window_days_override=1,
    )
    assert res.status == "completed"
    assert res.snapshots_recorded == 6  # 3 unique zones x 2 sessions (duplicate safely skipped)
    assert res.valid_snapshots == 4     # Garjia (2) + Durgadevi (2); Pakhro (2 closed -> NULL)
    assert len(repo.list_zones(active_only=False)) == 8  # No spurious 9th zone inserted!

    d_row = repo.list_safari_dates("2026-11-18", "2026-11-18")[0]
    assert d_row["operating_status"] == "partial"


def test_headed_consent_wait_and_per_zone_url_automatic_multi_date_collection(
    repo: SafariMonitorRepository, test_config: AppConfig
) -> None:
    """Fixes #1 & #4: Waits for human to click Allow once, then auto-scans all dates via zone URL."""
    visited_urls: list[str] = []

    class _ConsentThenZoneUrlDriver:
        def __init__(self) -> None:
            self.polls = 0

        def open_portal(self, url: str) -> PageInspectionState:
            # Initially shows Location verification prompt
            return PageInspectionState(
                url, 200, "Location verification required. Please verify your location.", ""
            )

        def current_state(self, http_status: int | None = None) -> PageInspectionState:
            self.polls += 1
            # Operator clicks Allow on first check -> gate clears genuinely!
            return PageInspectionState(
                "https://safari.corbettgov.org/", 200, "Select Safari Date", "<div>Open</div>"
            )

        def dismiss_consent_if_visible(self, selector: str) -> bool:
            return False

        def select_date(self, iso_date: str, selectors: SelectorConfig):
            raise AssertionError("Should use open_zone_date_url in pure zone_url_templates mode")

        def read_zone_cards(self, selectors: SelectorConfig) -> list[RawZoneCard]:
            return []

        def open_zone_date_url(
            self, zone_name: str, url_template: str, iso_date: str, selectors: SelectorConfig
        ) -> tuple[PageInspectionState, RawZoneCard]:
            full_url = format_date_template(url_template, iso_date)
            visited_urls.append(full_url)
            return (
                PageInspectionState(full_url, 200, f"Dhikala {iso_date}", ""),
                RawZoneCard(zone_name, "DhikalaZone", "28 / 64", None, "19 / 64", None),
            )

        def capture_screenshot(self, target_path: Path) -> str | None:
            return None

        def close(self) -> None:
            pass

    headed_cfg = replace(test_config, playwright_headless=False, consent_wait_seconds=10)
    zone_url_selectors = SelectorConfig(
        verified=True,
        verified_at="2026-11-18T08:00:00+05:30",
        verified_by="operator",
        unit_validated=True,
        capacity_displayed_on_portal=True,
        tourist_instructions_close="",
        important_info_acknowledge="",
        date_picker_trigger="",
        date_cell_template="",
        zone_url_templates={
            "Dhikala": "https://safari.corbettgov.org/?eventName=DhikalaZone&date={date}"
        },
        morning_availability_selector=".morning-seats",
        afternoon_availability_selector=".afternoon-seats",
    )
    ok, err = zone_url_selectors.validate_for_collection()
    assert ok is True, err

    collector = SafariAvailabilityCollector(
        headed_cfg,
        repo,
        driver_factory=_ConsentThenZoneUrlDriver,
        selector_config=zone_url_selectors,
        sleep_fn=lambda _: None,
    )
    res = collector.run(
        "morning",
        reference_time=datetime(2026, 11, 30, 7, 30, tzinfo=IST),
        window_days_override=3,  # Crosses Nov 30 -> Dec 1 -> Dec 2 automatically!
    )
    assert res.status == "completed"
    assert visited_urls == [
        "https://safari.corbettgov.org/?eventName=DhikalaZone&date=2026-11-30",
        "https://safari.corbettgov.org/?eventName=DhikalaZone&date=2026-12-01",
        "https://safari.corbettgov.org/?eventName=DhikalaZone&date=2026-12-02",
    ]
    assert res.valid_snapshots == 6


def test_dom_discovery_detects_aria_calendar_next_month_and_dhikala_url() -> None:
    """Fix #10: Auto-discovers aria-label calendar, next-month button, and Dhikala query URL."""
    cal_html = """
    <html><body>
      <button aria-label="Go to next month">&gt;</button>
      <span class="flatpickr-day" aria-label="November 30, 2026">30</span>
      <div class="flex p-4 safari-card">
        <h4 class="text-lg font-bold zone-heading">Bijrani Zone</h4>
        <div class="morning-count">18 Available</div>
        <div class="afternoon-count">9 Available</div>
      </div>
    </body></html>
    """
    disc = discover_candidate_selectors(cal_html)
    nav = disc["suggested_config"]["navigation"]
    assert disc["suggested_config"]["verified"] is False
    assert nav["date_cell_template"] == ".flatpickr-day[aria-label='{aria_date}']"
    assert nav["calendar_next_month_selector"] == "button[aria-label='Go to next month']"
    assert nav["zone_card_selector"] == "div.safari-card"
    assert nav["zone_name_selector"] == "h4.zone-heading"

    # Single-zone URL (`?eventName=DhikalaZone&date=2026-11-18`)
    dhikala_html = """
    <html><body>
      <div><span>Morning</span><span>32 Seats Left</span></div>
      <div><span>Afternoon</span><span>14 Seats Left</span></div>
    </body></html>
    """
    d_disc = discover_candidate_selectors(
        dhikala_html,
        final_url="https://safari.corbettgov.org/?eventName=DhikalaZone&date=2026-11-18",
    )
    assert d_disc["suggested_config"]["navigation"]["zone_url_templates"] == {
        "Dhikala": "https://safari.corbettgov.org/?eventName=DhikalaZone&date={date}"
    }


def test_single_run_lock_blocks_foreign_live_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix #9: Prevents two Playwright processes from corrupting `data/browser_profile`."""
    lock = tmp_path / ".collector.lock"
    lock.write_text("999999", encoding="utf-8")
    monkeypatch.setattr("src.collector.playwright_collector._is_pid_alive", lambda pid: True)
    with pytest.raises(CollectorBusyError):
        with _single_run_lock(lock):
            pass


def test_zone_url_single_date_network_error_recovers_without_crashing(
    repo: SafariMonitorRepository, test_config: AppConfig
) -> None:
    """Ensures a transient error on Day 1 in zone_url mode still collects Day 2 cleanly."""

    class _FlakyZoneUrlDriver:
        def open_portal(self, url: str) -> PageInspectionState:
            return PageInspectionState(url, 200, "Safari Open", "")

        def dismiss_consent_if_visible(self, selector: str) -> bool:
            return False

        def select_date(self, iso_date: str, selectors: SelectorConfig):
            return PageInspectionState(iso_date, 200, "", ""), "open"

        def read_zone_cards(self, selectors: SelectorConfig) -> list[RawZoneCard]:
            return []

        def open_zone_date_url(
            self, zone_name: str, url_template: str, iso_date: str, selectors: SelectorConfig
        ) -> tuple[PageInspectionState, RawZoneCard]:
            if iso_date == "2026-11-18":
                raise TimeoutError("Temporary network hiccup on first date")
            return (
                PageInspectionState(url_template, 200, "Open", ""),
                RawZoneCard(zone_name, "DhikalaZone", "30", None, "20", None),
            )

        def capture_screenshot(self, target_path: Path) -> str | None:
            return None

        def close(self) -> None:
            pass

    selectors = SelectorConfig(
        verified=True,
        verified_at="2026-11-18T08:00:00+05:30",
        verified_by="operator",
        unit_validated=True,
        capacity_displayed_on_portal=False,
        tourist_instructions_close="",
        important_info_acknowledge="",
        date_picker_trigger="",
        date_cell_template="",
        zone_url_templates={
            "Dhikala": "https://safari.corbettgov.org/?eventName=DhikalaZone&date={date}"
        },
        morning_availability_selector=".m",
        afternoon_availability_selector=".a",
    )
    collector = SafariAvailabilityCollector(
        test_config,
        repo,
        driver_factory=_FlakyZoneUrlDriver,
        selector_config=selectors,
        sleep_fn=lambda _: None,
    )
    res = collector.run(
        "manual",
        reference_time=datetime(2026, 11, 18, 10, 0, tzinfo=IST),
        window_days_override=2,
    )
    assert res.status == "partial"
    assert res.valid_snapshots == 2  # Day 2 succeeded cleanly despite Day 1 timeout

