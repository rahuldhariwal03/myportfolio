"""Compliant, strictly read-only Playwright availability collector (Phases 3 & 4).

Key guarantees:
- Uses Playwright to read visible information only — never submits booking forms,
  enters visitor details, interacts with cart/payment, or alters portal state.
- NEVER spoofs browser geolocation, suppresses CAPTCHA, or bypasses access gates.
  In local headed mode (`PLAYWRIGHT_HEADLESS=false`), pauses politely if a genuine
  declaration/location prompt is shown so the human operator can click Allow once —
  then automatically collects all 30 dates and zones hands-free.
- Automatically handles calendar month transitions (e.g. Nov 30 -> Dec 1), date URLs,
  zone dropdowns, and per-zone URLs (such as `?eventName=DhikalaZone&date={date}`).
- Preserves previously stored data across any failure; logs every attempt and saves
  diagnostic screenshots when failures or blocking gates occur.
- Automatically computes and stores Phase 5 availability change events on completion.
"""

from __future__ import annotations

import logging
import os
import random
import time as time_module
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol
from urllib.parse import urlparse

from src.analytics.change_detector import ChangeDetectionService
from src.collector.compliance import (
    HUMAN_RESOLVABLE_GATE_TYPES,
    ReadOnlyGuard,
    first_blocking_gate,
    inspect_visible_gates,
)
from src.collector.parser import (
    aggregate_date_operating_status,
    normalize_zone_name,
    parse_availability_text,
)
from src.collector.selectors import (
    SelectorConfig,
    format_date_template,
    load_selector_config,
)
from src.config import AppConfig
from src.database.repository import SafariMonitorRepository
from src.date_window import (
    DateWindow,
    calculate_rolling_window,
    format_iso_timestamp,
    is_within_portal_operating_hours,
    now_in_timezone,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawZoneCard:
    """Raw visible strings read from a single zone card or single-zone view."""

    zone_name: str
    source_zone_identifier: str | None
    morning_raw: str | None
    morning_capacity_raw: str | None
    afternoon_raw: str | None
    afternoon_capacity_raw: str | None
    error: str | None = None


@dataclass(frozen=True)
class PageInspectionState:
    """Visible state of the currently loaded browser page."""

    url: str
    http_status: int | None
    visible_text: str
    html: str


@dataclass(frozen=True)
class CollectionRunResult:
    """Summary returned after a manual or scheduled collection run completes."""

    run_id: int
    status: str
    date_window_start: str
    date_window_end: str
    snapshots_recorded: int
    valid_snapshots: int
    change_events_recorded: int
    error_summary: str | None


class CollectorBusyError(RuntimeError):
    """Raised when another collector or inspector process holds the active run lock."""


@contextmanager
def _single_run_lock(lock_path: Path) -> Iterator[None]:
    """Prevent two Playwright jobs from fighting over the same local browser profile."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            existing_pid = int(lock_path.read_text(encoding="utf-8").strip())
            if existing_pid != os.getpid() and _is_pid_alive(existing_pid):
                raise CollectorBusyError(
                    f"Another collection/inspection process (PID {existing_pid}) is already "
                    "running. Close the other browser/terminal window or wait for it to finish."
                )
        except CollectorBusyError:
            raise
        except Exception:  # noqa: BLE001
            # Stale or unreadable lock file — safe to overwrite
            pass

    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(
                os.getpid()
            ):
                lock_path.unlink()
        except Exception:  # noqa: BLE001
            pass


def _is_pid_alive(pid: int) -> bool:
    """Cross-platform check (Windows/macOS/Linux) whether process `pid` is still running."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            alive = bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and (
                exit_code.value == 259  # STILL_ACTIVE
            )
            kernel32.CloseHandle(handle)
            return alive
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class BrowserDriver(Protocol):
    """Minimal browser interface implemented by Playwright (and test fixtures)."""

    def open_portal(self, url: str) -> PageInspectionState: ...

    def dismiss_consent_if_visible(self, selector: str) -> bool: ...

    def select_date(
        self, iso_date: str, selectors: SelectorConfig
    ) -> tuple[PageInspectionState, str | None]: ...

    def read_zone_cards(self, selectors: SelectorConfig) -> list[RawZoneCard]: ...

    def capture_screenshot(self, target_path: Path) -> str | None: ...

    def close(self) -> None: ...


class PlaywrightBrowserDriver:
    """Real Playwright Chromium session with read-only network and action guards.

    IMPORTANT: Never passes synthetic `geolocation` coordinates. If the official portal
    requests browser location verification, the operator's real local browser/OS setting
    handles it in headed mode, or collection stops cleanly and reports `blocked`.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._pw_context_manager: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._last_selected_ym: tuple[int, int] | None = None
        parsed = urlparse(config.portal_url)
        self._allowed_hosts = {
            h
            for h in (
                parsed.hostname.lower() if parsed.hostname else None,
                "safari.corbettgov.org",
                "booking.corbettgov.org",
                "corbettgov.org",
            )
            if h
        }

    def _ensure_started(self) -> Any:
        if self._page is not None:
            return self._page

        from playwright.sync_api import sync_playwright

        self._pw_context_manager = sync_playwright()
        self._playwright = self._pw_context_manager.start()

        if self.config.playwright_user_data_dir is not None:
            self.config.playwright_user_data_dir.mkdir(parents=True, exist_ok=True)
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.config.playwright_user_data_dir),
                headless=self.config.playwright_headless,
                locale="en-IN",
                timezone_id=self.config.timezone_name,
            )
            self._page = (
                self._context.pages[0] if self._context.pages else self._context.new_page()
            )
        else:
            self._browser = self._playwright.chromium.launch(
                headless=self.config.playwright_headless
            )
            self._context = self._browser.new_context(
                locale="en-IN",
                timezone_id=self.config.timezone_name,
            )
            self._page = self._context.new_page()

        self._page.set_default_timeout(self.config.playwright_timeout_ms)

        # Network-level read-only safety fence (aborts any booking/cart/OTP/payment mutation)
        def _guard_route(route: Any, request: Any) -> None:
            if ReadOnlyGuard.should_block_network_request(request.url, request.method):
                logger.warning(
                    "ReadOnlyGuard aborted mutating/booking request: %s %s",
                    request.method,
                    request.url,
                )
                route.abort()
            else:
                route.continue_()

        self._page.route("**/*", _guard_route)
        return self._page

    def current_state(self, http_status: int | None = None) -> PageInspectionState:
        page = self._ensure_started()
        visible_text = page.evaluate("() => (document.body ? document.body.innerText : '')") or ""
        html = page.content() or ""
        return PageInspectionState(
            url=page.url,
            http_status=http_status,
            visible_text=" ".join(visible_text.split()),
            html=html,
        )

    def _wait_for_availability_render(self, selectors: SelectorConfig, timeout_ms: int = 6000) -> None:
        """Give client-side SPA components time to finish rendering slot numbers after navigation."""
        page = self._ensure_started()
        wait_target = (
            selectors.zone_card_selector.strip()
            or selectors.morning_availability_selector.strip()
            or selectors.afternoon_availability_selector.strip()
        )
        if not wait_target:
            page.wait_for_timeout(1200)
            return
        try:
            page.locator(wait_target).first.wait_for(state="visible", timeout=timeout_ms)
            page.wait_for_timeout(450)
        except Exception:  # noqa: BLE001
            # Date may genuinely be closed or show no cards — let caller inspect cleanly
            page.wait_for_timeout(600)

    def open_portal(self, url: str) -> PageInspectionState:
        ReadOnlyGuard.assert_safe_url(url, allowed_hosts=self._allowed_hosts)
        page = self._ensure_started()
        response = page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        status = response.status if response is not None else None
        return self.current_state(http_status=status)

    def dismiss_consent_if_visible(self, selector: str) -> bool:
        if not selector.strip():
            return False
        ReadOnlyGuard.assert_safe_interaction_label(selector)
        page = self._ensure_started()
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            locator.click()
            page.wait_for_timeout(900)
            return True
        return False

    def select_date(
        self, iso_date: str, selectors: SelectorConfig
    ) -> tuple[PageInspectionState, str | None]:
        page = self._ensure_started()
        target_d = date.fromisoformat(iso_date)
        target_ym = (target_d.year, target_d.month)

        # Strategy A: Direct URL navigation per date (e.g. `https://safari.corbettgov.org/?date={date}`)
        if selectors.date_url_template.strip():
            target_url = format_date_template(selectors.date_url_template, iso_date)
            ReadOnlyGuard.assert_safe_url(target_url, allowed_hosts=self._allowed_hosts)
            resp = page.goto(target_url, wait_until="domcontentloaded")
            self._wait_for_availability_render(selectors)
            self._last_selected_ym = target_ym
            status_code = resp.status if resp is not None else None
            return self.current_state(http_status=status_code), self._read_date_status(selectors)

        # Strategy B: Calendar date picker click (with automatic next-month rollover!)
        if selectors.date_picker_trigger.strip():
            ReadOnlyGuard.assert_safe_interaction_label(selectors.date_picker_trigger)
            trigger = page.locator(selectors.date_picker_trigger).first
            if trigger.count() > 0 and trigger.is_visible():
                trigger.click()
                page.wait_for_timeout(450)

        if selectors.date_cell_template.strip():
            cell_selector = format_date_template(selectors.date_cell_template, iso_date)
            ReadOnlyGuard.assert_safe_interaction_label(cell_selector)
            cell = page.locator(cell_selector).first

            # If crossing into a new calendar month (e.g. Nov 30 -> Dec 1) and the cell isn't
            # visible yet, click the configured Next-Month arrow cleanly.
            if (
                (cell.count() == 0 or not cell.is_visible())
                and selectors.calendar_next_month_selector.strip()
                and (self._last_selected_ym is None or target_ym > self._last_selected_ym)
            ):
                months_ahead = (
                    (target_ym[0] - self._last_selected_ym[0]) * 12
                    + (target_ym[1] - self._last_selected_ym[1])
                    if self._last_selected_ym is not None
                    else 1
                )
                ReadOnlyGuard.assert_safe_interaction_label(selectors.calendar_next_month_selector)
                for _ in range(max(1, min(months_ahead, 3))):
                    next_btn = page.locator(selectors.calendar_next_month_selector).first
                    if next_btn.count() > 0 and next_btn.is_visible() and not next_btn.is_disabled():
                        next_btn.click()
                        page.wait_for_timeout(600)
                    cell = page.locator(cell_selector).first
                    if cell.count() > 0 and cell.is_visible():
                        break

            if cell.count() == 0 or not cell.is_visible():
                return self.current_state(), "missing_date_cell"

            aria_disabled = (cell.get_attribute("aria-disabled") or "").strip().lower()
            cell_classes = (cell.get_attribute("class") or "").lower()
            if (
                cell.is_disabled()
                or aria_disabled == "true"
                or "disabled" in cell_classes.split()
                or "flatpickr-disabled" in cell_classes.split()
            ):
                self._last_selected_ym = target_ym
                return self.current_state(), "closed_or_disabled"

            cell.click()
            self._last_selected_ym = target_ym
            self._wait_for_availability_render(selectors)

        return self.current_state(), self._read_date_status(selectors)

    def _read_date_status(self, selectors: SelectorConfig) -> str:
        if not selectors.date_status_selector.strip():
            return "open"
        page = self._ensure_started()
        status_loc = page.locator(selectors.date_status_selector).first
        if status_loc.count() > 0 and status_loc.is_visible():
            return (status_loc.inner_text() or "").strip() or "open"
        return "open"

    def open_zone_date_url(
        self, zone_name: str, url_template: str, iso_date: str, selectors: SelectorConfig
    ) -> tuple[PageInspectionState, RawZoneCard]:
        """Navigate to a zone-specific date URL (e.g. `?eventName=DhikalaZone&date={date}`) and read slots."""
        target_url = format_date_template(url_template, iso_date, zone_id=zone_name)
        ReadOnlyGuard.assert_safe_url(target_url, allowed_hosts=self._allowed_hosts)
        page = self._ensure_started()
        resp = page.goto(target_url, wait_until="domcontentloaded")
        self._wait_for_availability_render(selectors)
        status_code = resp.status if resp is not None else None
        state = self.current_state(http_status=status_code)

        # Dismiss popups if they re-appear after navigation
        for modal_sel in (selectors.tourist_instructions_close, selectors.important_info_acknowledge):
            if modal_sel.strip():
                self.dismiss_consent_if_visible(modal_sel)

        root = (
            page.locator(selectors.zone_card_selector).first
            if selectors.zone_card_selector.strip()
            and page.locator(selectors.zone_card_selector).count() > 0
            else page.locator("body")
        )
        card = RawZoneCard(
            zone_name=zone_name,
            source_zone_identifier=None,
            morning_raw=_read_optional_text(root, selectors.morning_availability_selector),
            morning_capacity_raw=_read_optional_text(root, selectors.morning_capacity_selector),
            afternoon_raw=_read_optional_text(root, selectors.afternoon_availability_selector),
            afternoon_capacity_raw=_read_optional_text(root, selectors.afternoon_capacity_selector),
        )
        return state, card

    def read_zone_cards(self, selectors: SelectorConfig) -> list[RawZoneCard]:
        page = self._ensure_started()

        # Optional Zone-Dropdown layout: pick each zone option, read Morning & Afternoon
        if selectors.zone_dropdown_selector.strip() and selectors.zone_dropdown_options:
            ReadOnlyGuard.assert_safe_interaction_label(selectors.zone_dropdown_selector)
            results: list[RawZoneCard] = []
            dropdown = page.locator(selectors.zone_dropdown_selector).first
            if dropdown.count() == 0 or not dropdown.is_visible():
                return results
            for opt_label in selectors.zone_dropdown_options:
                try:
                    dropdown.select_option(label=opt_label)
                    self._wait_for_availability_render(selectors, timeout_ms=4000)
                    scope = (
                        page.locator(selectors.zone_card_selector).first
                        if selectors.zone_card_selector.strip()
                        and page.locator(selectors.zone_card_selector).count() > 0
                        else page.locator("body")
                    )
                    results.append(
                        RawZoneCard(
                            zone_name=opt_label,
                            source_zone_identifier=None,
                            morning_raw=_read_optional_text(
                                scope, selectors.morning_availability_selector
                            ),
                            morning_capacity_raw=_read_optional_text(
                                scope, selectors.morning_capacity_selector
                            ),
                            afternoon_raw=_read_optional_text(
                                scope, selectors.afternoon_availability_selector
                            ),
                            afternoon_capacity_raw=_read_optional_text(
                                scope, selectors.afternoon_capacity_selector
                            ),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        RawZoneCard(
                            zone_name=opt_label,
                            source_zone_identifier=None,
                            morning_raw=None,
                            morning_capacity_raw=None,
                            afternoon_raw=None,
                            afternoon_capacity_raw=None,
                            error=str(exc),
                        )
                    )
            return results

        # Standard Multi-Zone Card / Table-Row layout
        cards = page.locator(selectors.zone_card_selector)
        count = cards.count()
        results = []

        for idx in range(count):
            card = cards.nth(idx)
            try:
                # Skip hidden duplicate DOM cards (e.g. responsive mobile/desktop duplicates)
                if not card.is_visible():
                    continue

                if selectors.zone_expand_selector.strip():
                    ReadOnlyGuard.assert_safe_interaction_label(selectors.zone_expand_selector)
                    expander = card.locator(selectors.zone_expand_selector).first
                    if expander.count() > 0 and expander.is_visible():
                        expander.click()
                        page.wait_for_timeout(450)

                name_loc = card.locator(selectors.zone_name_selector).first
                zone_name = (
                    (name_loc.inner_text() or "").strip()
                    if name_loc.count() > 0 and name_loc.is_visible()
                    else ""
                )
                if not zone_name:
                    continue

                zone_ident: str | None = None
                if selectors.zone_id_attribute.strip():
                    raw_attr = card.get_attribute(selectors.zone_id_attribute)
                    zone_ident = raw_attr.strip() if raw_attr else None

                morning_raw = _read_optional_text(card, selectors.morning_availability_selector)
                morning_cap = _read_optional_text(card, selectors.morning_capacity_selector)
                afternoon_raw = _read_optional_text(card, selectors.afternoon_availability_selector)
                afternoon_cap = _read_optional_text(card, selectors.afternoon_capacity_selector)

                results.append(
                    RawZoneCard(
                        zone_name=zone_name,
                        source_zone_identifier=zone_ident,
                        morning_raw=morning_raw,
                        morning_capacity_raw=morning_cap,
                        afternoon_raw=afternoon_raw,
                        afternoon_capacity_raw=afternoon_cap,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    RawZoneCard(
                        zone_name=f"card_{idx}",
                        source_zone_identifier=None,
                        morning_raw=None,
                        morning_capacity_raw=None,
                        afternoon_raw=None,
                        afternoon_capacity_raw=None,
                        error=str(exc),
                    )
                )
        return results

    def capture_screenshot(self, target_path: Path) -> str | None:
        if self._page is None:
            return None
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self._page.screenshot(path=str(target_path), full_page=True)
            return str(target_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save diagnostic screenshot to %s: %s", target_path, exc)
            return None

    def close(self) -> None:
        for obj, method in (
            (self._context, "close"),
            (self._browser, "close"),
            (self._pw_context_manager, "__exit__"),
        ):
            if obj is not None:
                try:
                    if method == "__exit__":
                        obj.__exit__(None, None, None)
                    else:
                        getattr(obj, method)()
                except Exception:  # noqa: BLE001
                    pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._pw_context_manager = None
        self._last_selected_ym = None


def _read_optional_text(parent_locator: Any, selector: str) -> str | None:
    if not selector.strip():
        return None
    loc = parent_locator.locator(selector)
    count = loc.count()
    for i in range(count):
        candidate = loc.nth(i)
        if candidate.is_visible():
            return candidate.inner_text()
    return None


class SafariAvailabilityCollector:
    """Orchestrates a compliant rolling-window collection run, logging, and change detection."""

    def __init__(
        self,
        config: AppConfig,
        repo: SafariMonitorRepository,
        *,
        driver_factory: Callable[[], BrowserDriver] | None = None,
        selector_config: SelectorConfig | None = None,
        sleep_fn: Callable[[float], None] = time_module.sleep,
    ) -> None:
        self.config = config
        self.repo = repo
        self.driver_factory = driver_factory or (lambda: PlaywrightBrowserDriver(config))
        self.selector_config = selector_config
        self.sleep_fn = sleep_fn
        self.change_service = ChangeDetectionService(repo, timezone_name=config.timezone_name)

    def run(
        self,
        collection_type: str = "manual",
        *,
        reference_time: datetime | None = None,
        enforce_operating_hours: bool = True,
        window_days_override: int | None = None,
    ) -> CollectionRunResult:
        """Execute one full read-only collection run and persist snapshots + change events."""
        self.config.ensure_directories()
        lock_file = self.config.inspection_dir.parent / ".collector.lock"

        with _single_run_lock(lock_file):
            return self._run_locked(
                collection_type=collection_type,
                reference_time=reference_time,
                enforce_operating_hours=enforce_operating_hours,
                window_days_override=window_days_override,
            )

    def _run_locked(
        self,
        *,
        collection_type: str,
        reference_time: datetime | None,
        enforce_operating_hours: bool,
        window_days_override: int | None,
    ) -> CollectionRunResult:
        # Recover any stale runs left over from an earlier crash/power loss
        recovered = self.repo.recover_interrupted_runs()
        if recovered:
            logger.warning("Recovered %d previously interrupted collection run(s).", recovered)

        effective_days = (
            max(1, min(90, window_days_override))
            if window_days_override is not None
            else self.config.monitoring_window_days
        )
        now_dt = reference_time or now_in_timezone(self.config.timezone_name)
        window: DateWindow = calculate_rolling_window(
            now_dt,
            window_days=effective_days,
            timezone_name=self.config.timezone_name,
        )

        run_id = self.repo.start_collection_run(
            collection_type=collection_type,
            date_window_start=window.start_date,
            date_window_end=window.end_date,
            started_at=now_dt,
            is_demo=False,
            source_url=self.config.portal_url,
        )

        # 1. Respect official portal operating window (05:30–23:30 IST per corbettgov.org/faq)
        if enforce_operating_hours and not is_within_portal_operating_hours(
            now_dt,
            open_time=self.config.portal_open_time,
            close_time=self.config.portal_close_time,
            timezone_name=self.config.timezone_name,
        ):
            msg = (
                f"Skipped run outside official portal operating hours "
                f"({self.config.portal_open_time.strftime('%H:%M')}–"
                f"{self.config.portal_close_time.strftime('%H:%M')} {self.config.timezone_name})."
            )
            self.repo.log_collection_event(
                collection_run_id=run_id,
                page_or_zone="schedule_guard",
                status="outside_operating_hours",
                error_message=msg,
                logged_at=now_dt,
            )
            self.repo.complete_collection_run(
                run_id, status="blocked", completed_at=now_dt, error_summary=msg
            )
            return CollectionRunResult(
                run_id=run_id,
                status="blocked",
                date_window_start=window.start_date.isoformat(),
                date_window_end=window.end_date.isoformat(),
                snapshots_recorded=0,
                valid_snapshots=0,
                change_events_recorded=0,
                error_summary=msg,
            )

        selectors = self.selector_config or load_selector_config(self.config.selectors_config_path)
        driver: BrowserDriver | None = None
        snapshots_recorded = 0
        valid_snapshots = 0
        had_errors = False
        error_notes: list[str] = []

        try:
            driver = self.driver_factory()
            entry_state = self._with_retry(
                lambda: driver.open_portal(self.config.portal_url),
                context_label="portal_entry",
                run_id=run_id,
            )

            # 2. Politely dismiss configured standard advisory modals on entry
            for modal_selector in (
                selectors.tourist_instructions_close,
                selectors.important_info_acknowledge,
            ):
                if modal_selector.strip() and driver.dismiss_consent_if_visible(modal_selector):
                    self.repo.log_collection_event(
                        collection_run_id=run_id,
                        page_or_zone="consent_modal",
                        status="info",
                        error_message=f"Acknowledged visible informational modal ({modal_selector}).",
                    )
                    if hasattr(driver, "current_state"):
                        entry_state = driver.current_state(http_status=entry_state.http_status)

            # In local headed mode, if a location prompt OR an un-dismissed declaration/consent
            # modal is on screen, give the operator `consent_wait_seconds` to click Accept/Allow
            # genuinely — then auto-collect all 30 days hands-free!
            def _needs_human_acceptance(found: list[Any]) -> str | None:
                blk = first_blocking_gate(found)
                if blk is not None and blk.gate_type in HUMAN_RESOLVABLE_GATE_TYPES:
                    return blk.gate_type
                unconfigured_consent = not (
                    selectors.tourist_instructions_close.strip()
                    or selectors.important_info_acknowledge.strip()
                )
                if unconfigured_consent:
                    for item in found:
                        if item.gate_type in {"consent_notice", "tourist_instructions_notice"}:
                            return item.gate_type
                return None

            findings = inspect_visible_gates(
                visible_text=entry_state.visible_text,
                html=entry_state.html,
                http_status=entry_state.http_status,
            )
            pending_prompt = _needs_human_acceptance(findings)
            if (
                pending_prompt is not None
                and not self.config.playwright_headless
                and self.config.consent_wait_seconds > 0
                and hasattr(driver, "current_state")
            ):
                logger.info(
                    "ACTION NEEDED IN BROWSER WINDOW (%s): Please accept the declaration/consent "
                    "and click 'Allow' on location (waiting up to %ds). Once accepted, all %d "
                    "dates and zones will be collected automatically!",
                    pending_prompt,
                    self.config.consent_wait_seconds,
                    window.window_days,
                )
                waited = 0.0
                poll_step = 2.0
                while waited < self.config.consent_wait_seconds:
                    self.sleep_fn(poll_step)
                    waited += poll_step
                    entry_state = driver.current_state(http_status=entry_state.http_status)
                    findings = inspect_visible_gates(
                        visible_text=entry_state.visible_text,
                        html=entry_state.html,
                        http_status=entry_state.http_status,
                    )
                    if _needs_human_acceptance(findings) is None:
                        logger.info(
                            "Declaration/location accepted! Starting automatic %d-day scan.",
                            window.window_days,
                        )
                        break

            blocker = first_blocking_gate(findings)

            for info in findings:
                if not info.is_blocking:
                    self.repo.log_collection_event(
                        collection_run_id=run_id,
                        page_or_zone="portal_entry",
                        status=info.gate_type,
                        error_message=info.message,
                    )

            if blocker is not None:
                shot = self._maybe_screenshot(driver, run_id, f"gate_{blocker.gate_type}")
                self.repo.log_collection_event(
                    collection_run_id=run_id,
                    page_or_zone="portal_entry",
                    status=blocker.gate_type,
                    error_message=f"{blocker.message} [Matched: {blocker.matched_text!r}]",
                    screenshot_path=shot,
                )
                self.repo.complete_collection_run(
                    run_id, status="blocked", error_summary=blocker.message
                )
                return CollectionRunResult(
                    run_id=run_id,
                    status="blocked",
                    date_window_start=window.start_date.isoformat(),
                    date_window_end=window.end_date.isoformat(),
                    snapshots_recorded=0,
                    valid_snapshots=0,
                    change_events_recorded=0,
                    error_summary=blocker.message,
                )

            # 4. Verify selector contract is confirmed (never guess selectors or duplicate one date!)
            ready, reason = selectors.validate_for_collection()
            if not ready:
                shot = self._maybe_screenshot(driver, run_id, "selectors_unverified")
                self.repo.log_collection_event(
                    collection_run_id=run_id,
                    page_or_zone="selector_validation",
                    status="selectors_unverified",
                    error_message=reason,
                    screenshot_path=shot,
                )
                self.repo.complete_collection_run(
                    run_id, status="blocked", error_summary=reason
                )
                return CollectionRunResult(
                    run_id=run_id,
                    status="blocked",
                    date_window_start=window.start_date.isoformat(),
                    date_window_end=window.end_date.isoformat(),
                    snapshots_recorded=0,
                    valid_snapshots=0,
                    change_events_recorded=0,
                    error_summary=reason,
                )

            known_zones = {
                z["zone_name"].lower(): z for z in self.repo.list_zones(active_only=False)
            }
            use_main_calendar = bool(
                selectors.date_cell_template.strip() or selectors.date_url_template.strip()
            )
            use_zone_urls = bool(selectors.zone_url_templates)

            # 5. Automatically iterate rolling 30-day window (zero manual date clicking!)
            total_dates = len(window.iso_dates)
            halted_by_gate = False
            for idx, iso_date in enumerate(window.iso_dates):
                if halted_by_gate:
                    break
                if idx > 0:
                    self._polite_pause()

                logger.info(
                    "[%d/%d] Collecting safari availability for date %s...",
                    idx + 1,
                    total_dates,
                    iso_date,
                )

                cards_for_date: list[RawZoneCard] = []
                calendar_date_closed_status: str | None = None
                raw_date_status: str | None = None
                zone_url_failed = False

                # 5a. Main calendar or single date URL pass
                if use_main_calendar:
                    try:
                        date_state, raw_date_status = self._with_retry(
                            lambda d=iso_date: driver.select_date(d, selectors),
                            context_label=f"date:{iso_date}",
                            run_id=run_id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        had_errors = True
                        msg = f"Failed selecting date {iso_date}: {exc}"
                        error_notes.append(msg)
                        shot = self._maybe_screenshot(driver, run_id, f"date_err_{iso_date}")
                        self.repo.ensure_safari_date(iso_date, operating_status="unknown")
                        self.repo.log_collection_event(
                            collection_run_id=run_id,
                            page_or_zone=f"date:{iso_date}",
                            status="error",
                            error_message=msg,
                            screenshot_path=shot,
                        )
                        date_state = None
                        raw_date_status = "error"

                    if date_state is not None:
                        mid_blocker = first_blocking_gate(
                            inspect_visible_gates(
                                visible_text=date_state.visible_text,
                                html=date_state.html,
                                http_status=date_state.http_status,
                            )
                        )
                        if mid_blocker is not None:
                            had_errors = True
                            halted_by_gate = True
                            shot = self._maybe_screenshot(
                                driver, run_id, f"midrun_{mid_blocker.gate_type}_{iso_date}"
                            )
                            msg = f"Stopped at {iso_date}: {mid_blocker.message}"
                            error_notes.append(msg)
                            self.repo.log_collection_event(
                                collection_run_id=run_id,
                                page_or_zone=f"date:{iso_date}",
                                status=mid_blocker.gate_type,
                                error_message=msg,
                                screenshot_path=shot,
                            )
                            break

                        if raw_date_status in {"missing_date_cell", "closed_or_disabled"}:
                            calendar_date_closed_status = (
                                "window_not_open"
                                if raw_date_status == "missing_date_cell"
                                else "closed"
                            )
                            self.repo.ensure_safari_date(
                                iso_date,
                                operating_status=calendar_date_closed_status,
                                observed_at=format_iso_timestamp(
                                    now_in_timezone(self.config.timezone_name)
                                ),
                            )
                            self.repo.log_collection_event(
                                collection_run_id=run_id,
                                page_or_zone=f"date:{iso_date}",
                                status=calendar_date_closed_status,
                                error_message=f"Calendar date {iso_date} reported {raw_date_status}.",
                            )
                        else:
                            cards_for_date.extend(driver.read_zone_cards(selectors))

                # 5b. Optional per-zone URL pass (e.g. `?eventName=DhikalaZone&date={date}`)
                if use_zone_urls and not halted_by_gate and hasattr(driver, "open_zone_date_url"):
                    for z_label, z_url_tpl in selectors.zone_url_templates.items():
                        self._polite_pause()
                        try:
                            z_state, z_card = self._with_retry(
                                lambda zl=z_label, zt=z_url_tpl, d=iso_date: (
                                    driver.open_zone_date_url(zl, zt, d, selectors)
                                ),
                                context_label=f"zone_url:{z_label}:{iso_date}",
                                run_id=run_id,
                            )
                            z_blocker = first_blocking_gate(
                                inspect_visible_gates(
                                    visible_text=z_state.visible_text,
                                    html=z_state.html,
                                    http_status=z_state.http_status,
                                )
                            )
                            if z_blocker is not None:
                                had_errors = True
                                halted_by_gate = True
                                shot = self._maybe_screenshot(
                                    driver,
                                    run_id,
                                    f"midrun_{z_blocker.gate_type}_{z_label}_{iso_date}",
                                )
                                msg = f"Stopped at {z_label} {iso_date}: {z_blocker.message}"
                                error_notes.append(msg)
                                self.repo.log_collection_event(
                                    collection_run_id=run_id,
                                    page_or_zone=f"{z_label} / {iso_date}",
                                    status=z_blocker.gate_type,
                                    error_message=msg,
                                    screenshot_path=shot,
                                )
                                break
                            cards_for_date.append(z_card)
                        except Exception as exc:  # noqa: BLE001
                            had_errors = True
                            zone_url_failed = True
                            msg = f"Failed loading {z_label} URL on {iso_date}: {exc}"
                            error_notes.append(msg)
                            shot = self._maybe_screenshot(
                                driver, run_id, f"zone_url_err_{z_label}_{iso_date}"
                            )
                            self.repo.log_collection_event(
                                collection_run_id=run_id,
                                page_or_zone=f"{z_label} / {iso_date}",
                                status="error",
                                error_message=msg,
                                screenshot_path=shot,
                            )

                if halted_by_gate:
                    break

                if not cards_for_date:
                    if (
                        calendar_date_closed_status is None
                        and raw_date_status != "error"
                        and not zone_url_failed
                    ):
                        had_errors = True
                        shot = self._maybe_screenshot(driver, run_id, f"no_zones_{iso_date}")
                        msg = f"No visible zone cards found for {iso_date}"
                        error_notes.append(msg)
                        self.repo.ensure_safari_date(iso_date, operating_status="unknown")
                        self.repo.log_collection_event(
                            collection_run_id=run_id,
                            page_or_zone=f"date:{iso_date}",
                            status="missing",
                            error_message=msg,
                            screenshot_path=shot,
                        )
                    continue

                captured_iso = format_iso_timestamp(now_in_timezone(self.config.timezone_name))
                seen_zone_ids: set[int] = set()
                date_session_statuses: list[str] = []

                for card in cards_for_date:
                    if card.error:
                        had_errors = True
                        error_notes.append(f"{iso_date} {card.zone_name}: {card.error}")
                        shot = self._maybe_screenshot(
                            driver, run_id, f"zone_err_{iso_date}_{card.zone_name}"
                        )
                        self.repo.log_collection_event(
                            collection_run_id=run_id,
                            page_or_zone=f"{card.zone_name} / {iso_date}",
                            status="error",
                            error_message=card.error,
                            screenshot_path=shot,
                        )
                        continue

                    # Canonicalize spelling variations ("Bijrani Zone" -> "Bijrani", "Garjiya" -> "Garjia")
                    canonical_name = normalize_zone_name(card.zone_name)
                    if not canonical_name:
                        continue
                    zone_meta = known_zones.get(canonical_name.lower())
                    target_zone_name = str(zone_meta["zone_name"]) if zone_meta else canonical_name
                    zone_id = self.repo.upsert_zone(
                        zone_name=target_zone_name,
                        source_zone_identifier=card.source_zone_identifier,
                        safari_mode=str(zone_meta["safari_mode"]) if zone_meta else "unknown",
                        unit_label=str(zone_meta["unit_label"]) if zone_meta else "Unverified units",
                    )

                    # Guard against duplicate responsive DOM cards for the same zone on one date
                    if zone_id in seen_zone_ids:
                        self.repo.log_collection_event(
                            collection_run_id=run_id,
                            page_or_zone=f"{target_zone_name} / {iso_date}",
                            status="duplicate_skipped",
                            error_message=(
                                f"Skipped duplicate DOM card for {target_zone_name!r} "
                                f"(raw label {card.zone_name!r}) on {iso_date}."
                            ),
                            logged_at=captured_iso,
                        )
                        continue
                    seen_zone_ids.add(zone_id)

                    for session, raw_val, raw_cap in (
                        ("morning", card.morning_raw, card.morning_capacity_raw),
                        ("afternoon", card.afternoon_raw, card.afternoon_capacity_raw),
                    ):
                        parsed = parse_availability_text(
                            raw_val,
                            raw_capacity=raw_cap,
                            unit_validated=selectors.unit_validated,
                        )
                        date_session_statuses.append(parsed.collection_status)
                        per_row_date_op = (
                            "open"
                            if parsed.collection_status == "success"
                            else (
                                "closed"
                                if parsed.collection_status == "zone_closed"
                                else (
                                    "window_not_open"
                                    if parsed.collection_status == "window_not_open"
                                    else "partial"
                                )
                            )
                        )
                        self.repo.record_snapshot(
                            collection_run_id=run_id,
                            safari_date=iso_date,
                            zone_id=zone_id,
                            session=session,
                            available_slots=parsed.available_slots,
                            total_capacity=parsed.total_capacity,
                            raw_displayed_value=parsed.raw_displayed_value,
                            raw_capacity_value=parsed.raw_capacity_value,
                            collection_status=parsed.collection_status,
                            confidence=parsed.confidence,
                            source_section=selectors.source_section_label,
                            error_details=parsed.error_details,
                            date_operating_status=per_row_date_op,
                            captured_at=captured_iso,
                        )
                        snapshots_recorded += 1
                        if parsed.collection_status == "success":
                            valid_snapshots += 1
                        elif parsed.collection_status in {"missing", "parse_error", "error"}:
                            had_errors = True
                            self.repo.log_collection_event(
                                collection_run_id=run_id,
                                page_or_zone=f"{target_zone_name} / {iso_date} / {session}",
                                status=parsed.collection_status,
                                error_message=parsed.error_details,
                                logged_at=captured_iso,
                            )

                # Set accurate aggregate operating_status for the full safari date
                if date_session_statuses:
                    self.repo.ensure_safari_date(
                        iso_date,
                        operating_status=aggregate_date_operating_status(date_session_statuses),
                        observed_at=captured_iso,
                    )

            # 6. Compute consecutive-run availability changes for all newly recorded valid snapshots
            change_ids = self.change_service.detect_and_record_for_run(run_id)

            if snapshots_recorded == 0:
                terminal_status = "blocked" if halted_by_gate else "failed"
            elif had_errors:
                terminal_status = "partial"
            else:
                terminal_status = "completed"

            summary_text = (
                "; ".join(error_notes[:5])
                if error_notes
                else (
                    "Some observations were missing or unparseable (stored as NULL)."
                    if had_errors
                    else None
                )
            )
            self.repo.log_collection_event(
                collection_run_id=run_id,
                page_or_zone="run_summary",
                status=terminal_status,
                error_message=(
                    f"Recorded {snapshots_recorded} snapshots ({valid_snapshots} valid) "
                    f"and {len(change_ids)} change events."
                ),
            )
            self.repo.complete_collection_run(
                run_id, status=terminal_status, error_summary=summary_text
            )
            return CollectionRunResult(
                run_id=run_id,
                status=terminal_status,
                date_window_start=window.start_date.isoformat(),
                date_window_end=window.end_date.isoformat(),
                snapshots_recorded=snapshots_recorded,
                valid_snapshots=valid_snapshots,
                change_events_recorded=len(change_ids),
                error_summary=summary_text,
            )

        except Exception as exc:  # noqa: BLE001
            err_msg = _format_friendly_collector_error(exc)
            shot = self._maybe_screenshot(driver, run_id, "fatal_error") if driver else None
            change_ids = (
                self.change_service.detect_and_record_for_run(run_id)
                if snapshots_recorded > 0
                else []
            )
            terminal = "partial" if valid_snapshots > 0 else "failed"
            self.repo.log_collection_event(
                collection_run_id=run_id,
                page_or_zone="collector_runtime",
                status="error",
                error_message=err_msg,
                screenshot_path=shot,
            )
            self.repo.complete_collection_run(
                run_id, status=terminal, error_summary=err_msg
            )
            return CollectionRunResult(
                run_id=run_id,
                status=terminal,
                date_window_start=window.start_date.isoformat(),
                date_window_end=window.end_date.isoformat(),
                snapshots_recorded=snapshots_recorded,
                valid_snapshots=valid_snapshots,
                change_events_recorded=len(change_ids),
                error_summary=err_msg,
            )
        finally:
            if driver is not None:
                driver.close()

    def _with_retry(self, fn: Callable[[], Any], *, context_label: str, run_id: int) -> Any:
        last_exc: Exception | None = None
        total_attempts = self.config.max_retries_per_page + 1
        for attempt in range(total_attempts):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = str(exc)
                # Do not retry missing Playwright binaries, profile locks, or safety violations
                if any(
                    fatal in msg
                    for fatal in (
                        "Executable doesn't exist",
                        "Read-only guard",
                        "Blocked navigation",
                        "ProcessSingleton",
                        "user data directory is already in use",
                    )
                ):
                    raise
                if attempt + 1 < total_attempts:
                    delay = self.config.retry_backoff_seconds * (2**attempt)
                    self.repo.log_collection_event(
                        collection_run_id=run_id,
                        page_or_zone=context_label,
                        status="retry",
                        error_message=(
                            f"Attempt {attempt + 1}/{total_attempts} failed ({exc}); "
                            f"retrying in {delay:.1f}s."
                        ),
                    )
                    self.sleep_fn(delay)
        assert last_exc is not None
        raise last_exc

    def _polite_pause(self) -> None:
        delay = random.uniform(
            self.config.request_min_delay_seconds,
            self.config.request_max_delay_seconds,
        )
        self.sleep_fn(delay)

    def _maybe_screenshot(
        self, driver: BrowserDriver | None, run_id: int, tag: str
    ) -> str | None:
        if driver is None or not self.config.save_diagnostic_screenshots:
            return None
        safe_tag = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in tag)[:60]
        filename = f"run_{run_id:04d}_{safe_tag}.png"
        return driver.capture_screenshot(self.config.screenshots_dir / filename)


def _format_friendly_collector_error(exc: Exception) -> str:
    raw = str(exc).strip()
    if "Executable doesn't exist" in raw:
        return (
            "Playwright Chromium browser binary is not installed in this environment. "
            "On your local machine run: `playwright install chromium` (or `setup_and_run.bat`)."
        )
    if "ProcessSingleton" in raw or "user data directory is already in use" in raw:
        return (
            "The local Playwright browser profile (`data/browser_profile`) is currently open in "
            "another window. Close that Chromium window first and run the collector again."
        )
    if (
        "ERR_NAME_NOT_RESOLVED" in raw
        or "ERR_TUNNEL_CONNECTION_FAILED" in raw
        or "ERR_CONNECTION" in raw
        or "ERR_INTERNET_DISCONNECTED" in raw
    ):
        return (
            f"Network cannot reach the official portal from this environment ({raw[:160]}). "
            "Check your internet connection and run from your local machine."
        )
    return raw[:500]
