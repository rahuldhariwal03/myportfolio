#!/usr/bin/env python3
"""Initialize the Corbett Safari Monitor database schema and official zones.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --demo
    python scripts/init_db.py --database-url sqlite:///data/custom.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config, resolve_database_url
from src.database import SafariMonitorRepository, create_backend, initialize_schema


def init_database(database_url: str, timezone_name: str = "Asia/Kolkata") -> dict[str, int]:
    """Initialize schema, constraints, triggers, and official zones; return table counts."""
    backend = create_backend(database_url)
    initialize_schema(backend, seed_official_zones=True)
    repo = SafariMonitorRepository(backend, timezone_name=timezone_name)
    return repo.get_database_summary()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize Corbett Safari Monitor database tables and official zones."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Initialize the isolated DEMO sample database instead of the live database.",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Optional explicit DATABASE_URL override.",
    )
    args = parser.parse_args()

    config = load_config()
    config.ensure_directories()

    if args.database_url:
        target_url = resolve_database_url(args.database_url)
        label = "CUSTOM"
    elif args.demo:
        target_url = config.demo_database_url
        label = "DEMO"
    else:
        target_url = config.database_url
        label = "LIVE"

    summary = init_database(target_url, timezone_name=config.timezone_name)
    print(f"[{label}] Database initialized successfully: {target_url}")
    for table_name, count in summary.items():
        if table_name != "demo_runs":
            print(f"  - {table_name:24s}: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
