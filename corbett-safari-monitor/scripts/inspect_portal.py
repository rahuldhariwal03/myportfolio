#!/usr/bin/env python3
"""Phase 1 Interactive Portal Inspector & Selector Assistant (Strictly Read-Only).

Run this ONCE on your own computer to inspect https://safari.corbettgov.org/ safely:
  1. Opens a real visible Chromium browser window (never spoofs location or bypasses gates).
  2. Saves your genuine consent & browser location permission in `data/browser_profile/`.
  3. While the window is open, close the advisory pop-ups, click "Allow" if the browser
     asks for your real location, and click one open safari date so the zones and
     Morning/Afternoon numbers are visible on screen.
  4. Automatically scans the visible page for the 8 official Corbett zone names and
     saves a draft `data/inspection/suggested_selectors.json` + screenshot that you
     can review and approve with ONE click inside the Streamlit Dashboard!

Usage:
    python scripts/inspect_portal.py
    python scripts/inspect_portal.py --wait-seconds 60
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collector.compliance import ReadOnlyGuard, inspect_visible_gates
from src.collector.dom_discovery import discover_candidate_selectors
from src.collector.selectors import load_selector_config
from src.config import load_config
from src.date_window import format_iso_timestamp, now_in_timezone


def _configure_utf8_console() -> None:
    """Prevent UnicodeEncodeError on Windows Command Prompt (cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


def run_interactive_inspection(wait_seconds: int = 60, interactive: bool = False) -> int:
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

    report_path = config.inspection_dir / f"inspection_{stamp}.json"
    html_path = config.inspection_dir / "latest_page.html"
    suggested_path = config.inspection_dir / "suggested_selectors.json"
    screenshot_path = config.inspection_dir / f"inspection_{stamp}.png"

    print("=" * 72)
    print(" CORBETT PORTAL READ-ONLY INSPECTOR")
    print("=" * 72)
    print(f"Portal URL      : {config.portal_url}")
    print(f"Browser profile : {profile_dir}")
    print("\nWhen the browser window opens, please do ONLY these 3 things:")
    print("  1. Close the tourist instruction / important info pop-up.")
    print("  2. If asked for Location, click 'Allow' (uses your real location — never bypass).")
    print("  3. Click one open calendar date so Zone names & Morning/Afternoon slots appear.")
    print("     (Do NOT enter visitor details, cart, or payment!)")
    if interactive and sys.stdin.isatty():
        print("\nNo timer rush — come back here and press ENTER once slots are visible.\n")
    else:
        print(f"\nWaiting {wait_seconds} seconds before capturing the visible page...\n")

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                locale="en-IN",
                timezone_id=config.timezone_name,
            )
            page = context.pages[0] if context.pages else context.new_page()

            # Read-only safety fence: block any booking/cart/OTP/payment requests
            page.route(
                "**/*",
                lambda route, req: (
                    route.abort()
                    if ReadOnlyGuard.should_block_network_request(req.url, req.method)
                    else route.continue_()
                ),
            )

            response = page.goto(
                config.portal_url,
                wait_until="domcontentloaded",
                timeout=config.playwright_timeout_ms,
            )
            if interactive and sys.stdin.isatty():
                input(
                    ">>> Take your time in the browser window. Once zone availability numbers\n"
                    "    are visible on screen, come back here and press ENTER to capture... "
                )
            else:
                page.wait_for_timeout(wait_seconds * 1000)

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
                    const pick = (sel, limit = 40) =>
                        Array.from(document.querySelectorAll(sel))
                            .filter(isVisible)
                            .slice(0, limit)
                            .map((el) => ({
                                tag: el.tagName.toLowerCase(),
                                id: el.id || null,
                                classes: Array.from(el.classList).slice(0, 6),
                                role: el.getAttribute('role'),
                                dataAttrs: Object.keys(el.dataset || {}),
                                text: (el.innerText || '').trim().slice(0, 120),
                            }));
                    return {
                        title: document.title,
                        finalUrl: window.location.href,
                        headings: pick('h1, h2, h3, h4, h5, h6'),
                        buttons: pick('button, [role=\"button\"]'),
                        inputsAndSelects: pick('input, select'),
                        tables: pick('table, [role=\"grid\"]'),
                        calendarCells: pick('[data-date], [data-day], .flatpickr-day, [role=\"gridcell\"]', 20),
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
            "portal_url": config.portal_url,
            "http_status": response.status if response else None,
            "screenshot_path": str(screenshot_path),
            "suggested_selectors_path": str(suggested_path),
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
            "visible_text_excerpt": " ".join(visible_text.split())[:3000],
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"Inspection report saved    : {report_path}")
        print(f"Suggested selectors saved  : {suggested_path}")
        print(f"Screenshot saved           : {screenshot_path}")

        if findings:
            print("\nDetected gates / notices:")
            for item in findings:
                tag = "BLOCKING" if item.is_blocking else "NOTICE"
                print(f"  [{tag}] {item.gate_type}: {item.message}")

        if discovery["found_zones_count"] > 0:
            print(f"\nFound {discovery['found_zones_count']} visible Corbett zone block(s):")
            for sample in discovery["matched_samples"]:
                print(
                    f"  - {sample['zone_name']:14s} | "
                    f"Morning: {sample['morning_sample']!r} | "
                    f"Afternoon: {sample['afternoon_sample']!r}"
                )
            sug = discovery["suggested_config"]
            nav = sug["navigation"]
            has_date_nav = bool(
                nav["date_cell_template"]
                or nav["date_url_template"]
                or nav["zone_url_templates"]
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
                        "\nDo the zone names and Morning/Afternoon values above match the live "
                        "website exactly? Type 'yes' to verify & enable automatic 30-day runs: "
                    )
                    .strip()
                    .lower()
                )
                if answer == "yes":
                    meaning = input(
                        "Confirm what a slot number represents (press ENTER for "
                        "'Remaining Jeep permits per shift; Dhikala = Canter seats'): "
                    ).strip()
                    sug["verified"] = True
                    sug["verified_at"] = format_iso_timestamp(ts)
                    sug["verified_by"] = "local_operator_cli"
                    sug["unit_validation"]["jeep_slots_confirmed_meaning"] = (
                        meaning or "Remaining Jeep permits per shift; Dhikala = Canter seats"
                    )
                    sug["unit_validation"]["canter_slots_confirmed_meaning"] = "Canter seats"
                    config.selectors_config_path.parent.mkdir(parents=True, exist_ok=True)
                    config.selectors_config_path.write_text(
                        json.dumps(sug, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    check_ready, check_err = load_selector_config(
                        config.selectors_config_path
                    ).validate_for_collection()
                    if not check_ready:
                        print(f"\nSaved config still needs one field: {check_err}")
                        print(f"Share {report_path} in chat to finish setup in 10 seconds.")
                        return 1
                    print(f"\nSUCCESS! Verified selectors saved to: {config.selectors_config_path}")
                    print("Test a quick 2-day automatic scan first:")
                    print("  python scripts/run_collector.py --type manual --days 2")
                    print("Then collect all 30 days automatically anytime:")
                    print("  python scripts/run_collector.py --type manual")
                    return 0

            if not has_date_nav:
                print(
                    f"\nNOTE: Zone slots were found, but the calendar's custom date element "
                    f"needs exact matching. Share `{report_path}` in chat so we can plug in "
                    f"the exact calendar selector for 100% hands-free 30-day scanning."
                )
            else:
                print(
                    "\nNEXT STEP: Open the Streamlit Dashboard -> '5. Collection Monitoring' -> "
                    "'Setup Checklist & Selector Approval' tab, confirm the numbers, and click Save!"
                )
        else:
            print(
                "\nNo zone cards were visible yet when the timer ended (the page may still "
                "have been paused or waiting on a date click). Re-run with "
                "`python scripts/inspect_portal.py --wait-seconds 90` when the portal is open."
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\nInspection could not complete in this environment: {exc}")
        print(
            "Run this command on your own computer after running: playwright install chromium"
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only headed Playwright inspector & selector helper for safari.corbettgov.org."
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=60,
        help="Seconds to keep the browser open while you allow location & pick a date (default: 60).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Wait until you press ENTER (instead of a countdown) and offer instant approval.",
    )
    args = parser.parse_args()
    return run_interactive_inspection(
        wait_seconds=max(10, args.wait_seconds),
        interactive=args.interactive,
    )


if __name__ == "__main__":
    raise SystemExit(main())
