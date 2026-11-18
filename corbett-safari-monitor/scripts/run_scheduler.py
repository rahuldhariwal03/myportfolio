#!/usr/bin/env python3
"""Start or inspect the configurable morning & evening collection scheduler.

Usage:
    python scripts/run_scheduler.py --show-schedule
    python scripts/run_scheduler.py --run-now
    python scripts/run_scheduler.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.scheduler import (
    create_scheduler,
    execute_scheduled_run,
    preview_upcoming_runs,
    validate_schedule_times,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run or inspect the twice-daily Corbett safari availability scheduler."
    )
    parser.add_argument(
        "--show-schedule",
        action="store_true",
        help="Display configured morning/evening schedule and rolling 30-day windows, then exit.",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Trigger an immediate manual collection run and exit.",
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

    warnings = validate_schedule_times(config)
    for w in warnings:
        print(f"[CONFIG WARNING] {w}")

    previews = preview_upcoming_runs(config)
    print(f"Configured Timezone          : {config.timezone_name}")
    print(f"Morning Collection Time      : {config.morning_collection_time.strftime('%H:%M')}")
    print(f"Evening Collection Time      : {config.evening_collection_time.strftime('%H:%M')}")
    print(f"Rolling Monitoring Window    : {config.monitoring_window_days} days")
    print("\nUpcoming Scheduled Runs:")
    for item in previews:
        print(
            f"  - {item['job_id']:20s} | {item['next_run_at']} "
            f"| Monitors {item['window_start']} -> {item['window_end']}"
        )

    if args.show_schedule:
        return 0

    if args.run_now:
        print("\nExecuting immediate manual collection run...")
        result = execute_scheduled_run(config, "manual")
        print(
            f"Manual Run #{result.run_id} finished with status={result.status!r} "
            f"(snapshots={result.snapshots_recorded}, changes={result.change_events_recorded})"
        )
        if result.error_summary:
            print(f"Details: {result.error_summary}")
        return 0 if result.status in {"completed", "partial"} else 2

    scheduler = create_scheduler(config, blocking=True)
    print("\nScheduler running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
