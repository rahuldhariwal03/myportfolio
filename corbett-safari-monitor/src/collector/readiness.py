"""Beginner-friendly environment & compliance readiness checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from src.collector.selectors import load_selector_config
from src.config import AppConfig
from src.date_window import is_within_portal_operating_hours, now_in_timezone


def _detect_chromium_binary() -> tuple[bool, str]:
    """Check whether Playwright's Chromium executable is installed locally."""
    if importlib.util.find_spec("playwright") is None:
        return False, "Install Python deps: `pip install -r requirements.txt`"

    cache_roots = [
        Path.home() / ".cache" / "ms-playwright",
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / "AppData" / "Local" / "ms-playwright",
    ]
    for root in cache_roots:
        if root.exists() and any(root.glob("chromium*")):
            return True, f"Chromium installed in {root}"
    return False, "Run `playwright install chromium` on your computer"


def check_system_readiness(config: AppConfig, live_zone_count: int) -> list[dict[str, Any]]:
    """Return ordered checklist items showing what is ready and what needs action."""
    chromium_ok, chromium_detail = _detect_chromium_binary()
    sel_cfg = load_selector_config(config.selectors_config_path)
    sel_ready, sel_reason = sel_cfg.validate_for_collection()

    suggested_path = config.inspection_dir / "suggested_selectors.json"
    if not sel_ready and suggested_path.exists():
        sel_detail = (
            "Draft `data/inspection/suggested_selectors.json` found — review & approve it below!"
        )
    elif sel_ready:
        sel_detail = f"Verified selector config active ({config.selectors_config_path.name})"
    else:
        sel_detail = sel_reason or "Run `python scripts/inspect_portal.py` on your computer first"

    now_ist = now_in_timezone(config.timezone_name)
    hours_ok = is_within_portal_operating_hours(
        now_ist,
        open_time=config.portal_open_time,
        close_time=config.portal_close_time,
        timezone_name=config.timezone_name,
    )

    profile_ok = (
        config.playwright_user_data_dir is not None and config.playwright_user_data_dir.exists()
    )

    return [
        {
            "step": "1. Live Database & 8 Official Zones",
            "ready": live_zone_count >= 8,
            "status": "Ready" if live_zone_count >= 8 else "Action needed",
            "detail": (
                f"SQLite initialized with {live_zone_count} official Corbett zones & append-only triggers."
                if live_zone_count >= 8
                else "Run `python scripts/init_db.py`"
            ),
        },
        {
            "step": "2. Manual / CSV Live Recording",
            "ready": True,
            "status": "Ready now",
            "detail": (
                "Works immediately — enter or upload what you see on safari.corbettgov.org "
                "in the 'Record Real Observation' tab below (zero selector setup needed)."
            ),
        },
        {
            "step": "3. Playwright Chromium Browser (for Automation)",
            "ready": chromium_ok,
            "status": "Ready" if chromium_ok else "Run on your laptop",
            "detail": chromium_detail,
        },
        {
            "step": "4. Local Browser Location Profile",
            "ready": profile_ok,
            "status": "Saved" if profile_ok else "Created on first local inspect",
            "detail": (
                f"Using persistent local profile `{config.playwright_user_data_dir}`."
                if profile_ok
                else "Run `python scripts/inspect_portal.py` locally and click 'Allow' on location."
            ),
        },
        {
            "step": "5. Verified Portal Selectors (`config/selectors.json`)",
            "ready": sel_ready,
            "status": "Verified" if sel_ready else "Pending local inspect",
            "detail": sel_detail,
        },
        {
            "step": "6. Official Portal Hours (05:30–23:30 IST)",
            "ready": hours_ok,
            "status": "Open now" if hours_ok else "Closed (night window)",
            "detail": f"Current time: {now_ist.strftime('%H:%M %Z')}",
        },
    ]
