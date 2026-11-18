"""Shared pytest fixtures for the Corbett Safari Monitor test suite."""

from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import AppConfig
from src.database import SafariMonitorRepository, create_backend, initialize_schema


@pytest.fixture()
def repo(tmp_path: Path) -> SafariMonitorRepository:
    """Fresh, isolated SQLite database initialized with all 6 tables, triggers, and 8 CTR zones."""
    db_url = f"sqlite:///{tmp_path / 'test_monitor.db'}"
    backend = create_backend(db_url)
    initialize_schema(backend, seed_official_zones=True)
    return SafariMonitorRepository(backend, timezone_name="Asia/Kolkata")


@pytest.fixture()
def test_config(tmp_path: Path) -> AppConfig:
    """Deterministic `AppConfig` rooted inside `tmp_path`."""
    return AppConfig(
        portal_url="https://safari.corbettgov.org/",
        database_url=f"sqlite:///{tmp_path / 'live.db'}",
        demo_database_url=f"sqlite:///{tmp_path / 'demo_monitor.db'}",
        timezone_name="Asia/Kolkata",
        morning_collection_time=time(7, 30),
        evening_collection_time=time(19, 30),
        monitoring_window_days=3,
        portal_open_time=time(5, 30),
        portal_close_time=time(23, 30),
        stale_data_threshold_hours=14,
        playwright_headless=True,
        playwright_timeout_ms=5000,
        playwright_user_data_dir=None,
        consent_wait_seconds=0,
        request_min_delay_seconds=1.0,
        request_max_delay_seconds=1.0,
        max_retries_per_page=1,
        retry_backoff_seconds=1.0,
        save_diagnostic_screenshots=True,
        screenshots_dir=tmp_path / "screenshots",
        exports_dir=tmp_path / "exports",
        inspection_dir=tmp_path / "inspection",
        selectors_config_path=tmp_path / "selectors.json",
        log_level="INFO",
    )
