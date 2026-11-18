#!/usr/bin/env python3
"""Phase 1 Interactive Portal Inspector & One-Time Calibration Helper (Strictly Read-Only).

Can be launched EITHER directly from the Streamlit Dashboard ("Open Corbett Portal" button)
OR from PowerShell/Terminal:
    python scripts/inspect_portal.py --interactive
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collector.compliance import ReadOnlyGuard, inspect_visible_gates
from src.collector.dom_discovery import discover_candidate_selectors
from src.collector.playwright_collector import launch_persistent_browser
from src.collector.selectors import load_selector_config
from src.config import load_config
from src.date_window import format_iso_timestamp, now_in_timezone


def _configure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def run_interactive_inspection(
    wait_seconds: int = 60,
    *,
    interactive: bool = False,
    wait_for_signal: bool = False,
) -> int:
    _configure_utf8_console()
    config = load_config()
    config.ensure_directories()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: pip install -r requirements.txt")
        return 1

    ts = now_in_timezone(config.timezone_name)
    stamp = ts.strftime("%Y%m%d_%H%M%S")
    profile_dir = config.playwright_user_data_dir or (PROJECT_ROOT / "data" / "browser_profile")
    profile_dir.mkdir(parents=True, exist_ok=True)

    state_file = config.inspection_dir / "calibration_state.json"
    signal_file = config.inspection_dir / "capture_now.signal"
    signal_file.unlink(missing_ok=True)

    report_path = config.inspection_dir / f"inspection_{stamp}.json"
    latest_report_path = config.inspection_dir / "inspection_latest.json"
    html_path = config.inspection_dir / "latest_page.html"
    suggested_path = config.inspection_dir / "suggested_selectors.json"
    screenshot_path = config.inspection_dir / f"inspection_{stamp}.png"

    def _write_state(status: str, detail: str = "") -> None:
        state_file.write_text(
            json.dumps(
                {
                    "status": status,
                    "pid": os.getpid(),
                    "updated_at": format_iso_timestamp(now_in_timezone(config.timezone_name)),
                    "detail": detail,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    print("=" * 72)
    print(" CORBETT PORTAL READ-ONLY ONE-TIME CALIBRATION")
    print("=" * 72)
    print(f"Portal URL : {config.portal_url}")
    print("\nIn the browser window that opens:")
    print("  1. Accept/close the declaration & tourist notice (tick 'Don't show this again').")
    print("  2. Click 'Allow' on the browser Location prompt (uses your real OS location).")
    print("  3. Click ONE open safari date so Zones & Morning/Afternoon slots are visible.")
    print("     (Stop there — never enter visitor details, cart, or payment.)\n")

    console_errors: list[str] = []

    try:
        _write_state("opening", "Opening official portal in your local browser...")
        with sync_playwright() as pw:
            context, channel_used = launch_persistent_browser(
                pw,
                profile_dir,
                headless=False,
                timezone_name=config.timezone_name,
            )
            print(f"Browser launched : {channel_used}")
            page = context.pages[0] if context.pages else context.new_page()

            page.on(
                "pageerror",
                lambda err: console_errors.append(str(err)[:200]),
            )

            # Read-only safety fence: allows all passive scripts/assets/reads so the SPA
            # loads cleanly, while blocking any order/cart/OTP/payment submission.
            page.route(
                "**/*",
                lambda route, req: (
                    route.abort()
                    if ReadOnlyGuard.should_block_network_request(
                        req.url, req.method, getattr(req, "resource_type", None)
                    )
                    else route.continue_()
                ),
            )

            response = page.goto(
                config.portal_url,
                wait_until="domcontentloaded",
                timeout=max(config.playwright_timeout_ms, 45000),
            )
            _write_state(
                "waiting_for_user",
                f"Browser ({channel_used}) is open on {config.portal_url}. "
                "Accept consent, click Allow on Location, select 1 open date, then click "
                "'Step 2: Capture Open Browser Page Now'.",
            )

            if wait_for_signal:
                # Stay open up to 10 minutes until user clicks 'Capture Now' in the dashboard
                for _ in range(600):
                    if signal_file.exists():
                        signal_file.unlink(missing_ok=True)
                        break
                    if page.is_closed():
                        _write_state("closed", "Browser window was closed before capture.")
                        return 1
                    page.wait_for_timeout(1000)
            elif interactive and sys.stdin.isatty():
                input(
                    ">>> Browser stays open as long as you need. Once zone availability numbers\n"
                    "    are visible on screen, come back here and press ENTER to capture... "
                )
            else:
                print(f"Waiting {wait_seconds} seconds before capturing...\n")
                page.wait_for_timeout(wait_seconds * 1000)

            _write_state("capturing", "Reading visible page structure & saving snapshot...")
            final_url = page.url
            visible_text = page.evaluate("() => (document.body ? document.body.innerText : '')") or ""
            rendered_html = page.content() or ""
            element_summary = page.evaluate(
                """() => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && rect.width > 0
                            && rect.height > 0;
                    };
                    const pick = (sel, limit = 45) =>
                        Array.from(document.querySelectorAll(sel))
                            .filter(isVisible)
                            .slice(0, limit)
                            .map((el) => ({
                                tag: el.tagName.toLowerCase(),
                                id: el.id || null,
                                classes: Array.from(el.classList).slice(0, 6),
                                role: el.getAttribute('role'),
                                ariaLabel: el.getAttribute('aria-label'),
                                name: el.getAttribute('name'),
                                dataAttrs: Object.assign({}, el.dataset || {}),
                                text: (el.innerText || el.value || '').trim().slice(0, 140),
                            }));
                    const selectOptions = Array.from(document.querySelectorAll('select'))
                        .filter(isVisible)
                        .map((sel) => ({
                            id: sel.id || null,
                            name: sel.getAttribute('name'),
                            classes: Array.from(sel.classList).slice(0, 5),
                            options: Array.from(sel.options).slice(0, 20).map((o) => ({
                                value: o.value,
                                text: (o.text || '').trim(),
                            })),
                        }));
                    return {
                        title: document.title,
                        finalUrl: window.location.href,
                        headings: pick('h1, h2, h3, h4, h5, h6'),
                        buttons: pick('button, [role=\"button\"], a.btn'),
                        inputsAndSelects: pick('input, select'),
                        selectOptions,
                        tables: pick('table, [role=\"grid\"]'),
                        calendarCells: pick(
                            '[data-date], [data-day], .flatpickr-day, [role=\"gridcell\"], td.day, .calendar td, .datepicker td',
                            25
                        ),
                    };
                }"""
            )

            findings = inspect_visible_gates(
                visible_text=" ".join(visible_text.split()),
                http_status=response.status if response else None,
            )
            discovery = discover_candidate_selectors(
                rendered_html, portal_url=config.portal_url, final_url=final_url
            )

            page.screenshot(path=str(screenshot_path), full_page=True)
            context.close()

        html_path.write_text(rendered_html, encoding="utf-8")
        suggested_path.write_text(
            json.dumps(discovery, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        report = {
            "inspected_at": format_iso_timestamp(ts),
            "browser_channel": channel_used,
            "portal_url": config.portal_url,
            "final_url": final_url,
            "http_status": response.status if response else None,
            "screenshot_path": str(screenshot_path),
            "suggested_selectors_path": str(suggested_path),
            "console_errors": console_errors[:10],
            "detected_gates_and_notices": [
                {
                    "gate_type": f.gate_type,
                    "is_blocking": f.is_blocking,
                    "message": f.message,
                    "matched_text": f.matched_text,
                }
                for f in findings
            ],
            "selector_discovery": discovery,
            "dom_summary": element_summary,
            "visible_text_excerpt": " ".join(visible_text.split())[:4000],
        }
        report_json = json.dumps(report, indent=2, ensure_ascii=False)
        report_path.write_text(report_json, encoding="utf-8")
        latest_report_path.write_text(report_json, encoding="utf-8")

        _write_state(
            "captured",
            f"Captured {final_url} ({discovery['found_zones_count']} zone block(s) detected). "
            "Review & click Save in 'Setup Checklist & Selector Approval' (or download "
            "inspection_latest.json if selectors need tuning).",
        )

        print(f"\nInspection report saved   : {latest_report_path}")
        print(f"Suggested selectors saved : {suggested_path}")
        print(f"Screenshot saved          : {screenshot_path}")

        if findings:
            print("\nDetected gates / notices:")
            for item in findings:
                tag = "BLOCKING" if item.is_blocking else "NOTICE"
                print(f"  [{tag}] {item.gate_type}: {item.message}")

        if discovery["found_zones_count"] > 0:
            print(f"\nFound {discovery['found_zones_count']} visible Corbett zone block(s):")
            for sample in discovery["matched_samples"]:
                print(
                    f"  - {str(sample['zone_name']):14s} | "
                    f"Morning: {sample['morning_sample']!r} | "
                    f"Afternoon: {sample['afternoon_sample']!r}"
                )
            sug = discovery["suggested_config"]
            nav = sug["navigation"]
            has_date_nav = bool(
                nav["date_cell_template"] or nav["date_url_template"] or nav["zone_url_templates"]
            )
            has_sessions = bool(
                sug["availability"]["morning_availability_selector"]
                and sug["availability"]["afternoon_availability_selector"]
            )
            print(
                f"\nAuto-date switching detected: {'YES' if has_date_nav else 'NEEDS REVIEW'} "
                f"(date_cell={nav['date_cell_template']!r}, "
                f"next_month={nav['calendar_next_month_selector']!r}, "
                f"date_url={nav['date_url_template']!r}, "
                f"zone_urls={list(nav['zone_url_templates'].keys())})"
            )
            if interactive and sys.stdin.isatty() and has_sessions and has_date_nav:
                answer = (
                    input(
                        "\nDo the numbers above match the live website? "
                        "Type 'yes' to verify & enable automatic 30-day runs: "
                    )
                    .strip()
                    .lower()
                )
                if answer == "yes":
                    sug["verified"] = True
                    sug["verified_at"] = format_iso_timestamp(ts)
                    sug["verified_by"] = "local_operator_cli"
                    sug["unit_validation"]["jeep_slots_confirmed_meaning"] = (
                        "Remaining Jeep permits per shift; Dhikala = Canter seats"
                    )
                    sug["unit_validation"]["canter_slots_confirmed_meaning"] = "Canter seats"
                    config.selectors_config_path.parent.mkdir(parents=True, exist_ok=True)
                    config.selectors_config_path.write_text(
                        json.dumps(sug, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    ok, err = load_selector_config(
                        config.selectors_config_path
                    ).validate_for_collection()
                    if ok:
                        print(f"\nSUCCESS! Verified selectors saved to {config.selectors_config_path}")
                        return 0
                    print(f"\nStill needs one field: {err}")
        else:
            print(f"\nVisible page preview: {' '.join(visible_text.split())[:350]}")
            print(
                f"\nShare `{latest_report_path}` in chat so we can configure exact automatic "
                "selectors for Corbett's page structure."
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        _write_state("error", str(exc)[:400])
        print(f"\nCalibration error: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only local Chrome/Edge calibration helper for safari.corbettgov.org."
    )
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--wait-for-signal",
        action="store_true",
        help="Used by the dashboard button: keeps browser open until 'Capture Now' is clicked.",
    )
    args = parser.parse_args()
    return run_interactive_inspection(
        wait_seconds=max(10, args.wait_seconds),
        interactive=args.interactive,
        wait_for_signal=args.wait_for_signal,
    )


if __name__ == "__main__":
    raise SystemExit(main())
