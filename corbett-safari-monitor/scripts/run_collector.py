#!/usr/bin/env python3
"""Run a single read-only safari availability collection and change-detection cycle.

Usage:
    python scripts/run_collector.py --type manual
    python scripts/run_collector.py --type morning
    python scripts/run_collector.py --type evening
    python scripts/run_collector.py --preview-window
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collector import SafariAvailabilityCollector
from src.config import load_config
from src.database import SafariMonitorRepository, create_backend, initialize_schema
from src.date_window import calculate_rolling_window, now_in_timezone


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute a read-only Corbett safari availability collection run."
    )
    parser.add_argument(
        "--type",
        choices=("manual", "morning", "evening"),
        default="manual",
        help="Collection run label stored in `collection_runs.collection_type`.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Optional quick-test override for window length (e.g. `--days 2` to verify setup).",
    )
    parser.add_argument(
        "--preview-window",
        action="store_true",
        help="Print today's rolling 30-day window in Asia/Kolkata without contacting the portal.",
    )
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass

    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    now_dt = now_in_timezone(config.timezone_name)
    window = calculate_rolling_window(
        now_dt,
        window_days=config.monitoring_window_days,
        timezone_name=config.timezone_name,
    )

    if args.preview_window:
        print(f"Current time ({config.timezone_name}) : {now_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"Rolling window ({window.window_days} days)  : {window.start_date} -> {window.end_date}")
        print(
            f"Portal operating hours       : "
            f"{config.portal_open_time.strftime('%H:%M')} - {config.portal_close_time.strftime('%H:%M')} "
            f"{config.timezone_name}"
        )
        return 0

    config.ensure_directories()
    backend = create_backend(config.database_url)
    initialize_schema(backend, seed_official_zones=True)
    repo = SafariMonitorRepository(backend, timezone_name=config.timezone_name)

    collector = SafariAvailabilityCollector(config=config, repo=repo)
    result = collector.run(
        collection_type=args.type,
        window_days_override=args.days,
    )

    print(f"Collection Run #{result.run_id} finished")
    print(f"  Status                 : {result.status}")
    print(f"  Monitored window       : {result.date_window_start} -> {result.date_window_end}")
    print(f"  Snapshots recorded     : {result.snapshots_recorded} ({result.valid_snapshots} valid)")
    print(f"  Change events recorded : {result.change_events_recorded}")
    if result.error_summary:
        print(f"  Note / Error summary   : {result.error_summary}")

    return 0 if result.status in {"completed", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
