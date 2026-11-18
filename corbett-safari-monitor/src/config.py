"""Environment-driven configuration for the Corbett Safari Monitor.

All schedule times, file locations, database URLs, and Playwright parameters are
read from environment variables (or a local `.env` file) so nothing operational
is hardcoded inside application logic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_hhmm(value: str, field_name: str) -> time:
    """Parse an HH:MM 24-hour clock string into a `datetime.time` object."""
    cleaned = value.strip()
    parts = cleaned.split(":")
    if len(parts) != 2:
        raise ValueError(f"{field_name} must be in HH:MM 24-hour format, got {value!r}")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise ValueError(f"{field_name} has invalid time {value!r}: {exc}") from exc


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _resolve_path(raw_path: str, base_dir: Path = PROJECT_ROOT) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def resolve_database_url(url: str, base_dir: Path = PROJECT_ROOT) -> str:
    """Resolve relative SQLite file paths against the project root."""
    cleaned = url.strip()
    if cleaned.startswith("sqlite:///") and cleaned != "sqlite:///:memory:":
        raw_file = cleaned[len("sqlite:///") :]
        file_path = Path(raw_file)
        if not file_path.is_absolute():
            resolved = (base_dir / file_path).resolve()
            return f"sqlite:///{resolved}"
    return cleaned


@dataclass(frozen=True)
class AppConfig:
    """Validated runtime settings loaded from environment variables."""

    portal_url: str
    database_url: str
    demo_database_url: str
    timezone_name: str
    morning_collection_time: time
    evening_collection_time: time
    monitoring_window_days: int
    portal_open_time: time
    portal_close_time: time
    stale_data_threshold_hours: int
    playwright_headless: bool
    playwright_timeout_ms: int
    playwright_user_data_dir: Path | None
    consent_wait_seconds: int
    request_min_delay_seconds: float
    request_max_delay_seconds: float
    max_retries_per_page: int
    retry_backoff_seconds: float
    save_diagnostic_screenshots: bool
    screenshots_dir: Path
    exports_dir: Path
    inspection_dir: Path
    selectors_config_path: Path
    log_level: str

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def ensure_directories(self) -> None:
        """Create local runtime directories (screenshots, exports, data) if missing."""
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.inspection_dir.mkdir(parents=True, exist_ok=True)
        for db_url in (self.database_url, self.demo_database_url):
            if db_url.startswith("sqlite:///") and db_url != "sqlite:///:memory:":
                Path(db_url[len("sqlite:///") :]).parent.mkdir(parents=True, exist_ok=True)


def load_config(env_file: Path | None = None, base_dir: Path = PROJECT_ROOT) -> AppConfig:
    """Load and validate configuration from `.env` (if present) and `os.environ`."""
    target_env = env_file if env_file is not None else base_dir / ".env"
    if target_env.exists():
        load_dotenv(dotenv_path=target_env, override=False)

    tz_name = os.getenv("COLLECTION_TIMEZONE", "Asia/Kolkata").strip()
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown COLLECTION_TIMEZONE {tz_name!r}") from exc

    window_days = int(os.getenv("MONITORING_WINDOW_DAYS", "30"))
    if window_days < 1 or window_days > 90:
        raise ValueError(f"MONITORING_WINDOW_DAYS must be between 1 and 90, got {window_days}")

    min_delay = float(os.getenv("REQUEST_MIN_DELAY_SECONDS", "4.0"))
    max_delay = float(os.getenv("REQUEST_MAX_DELAY_SECONDS", "8.0"))
    if min_delay < 1.0:
        raise ValueError("REQUEST_MIN_DELAY_SECONDS must be >= 1.0 to avoid excessive portal requests")
    if max_delay < min_delay:
        raise ValueError("REQUEST_MAX_DELAY_SECONDS must be >= REQUEST_MIN_DELAY_SECONDS")

    raw_profile = os.getenv("PLAYWRIGHT_USER_DATA_DIR", "").strip()
    user_data_dir = _resolve_path(raw_profile, base_dir) if raw_profile else None

    return AppConfig(
        portal_url=os.getenv("CORBETT_PORTAL_URL", "https://safari.corbettgov.org/").strip(),
        database_url=resolve_database_url(
            os.getenv("DATABASE_URL", "sqlite:///data/corbett_monitor.db"), base_dir
        ),
        demo_database_url=resolve_database_url(
            os.getenv("DEMO_DATABASE_URL", "sqlite:///data/demo_corbett_monitor.db"), base_dir
        ),
        timezone_name=tz_name,
        morning_collection_time=parse_hhmm(
            os.getenv("MORNING_COLLECTION_TIME", "07:30"), "MORNING_COLLECTION_TIME"
        ),
        evening_collection_time=parse_hhmm(
            os.getenv("EVENING_COLLECTION_TIME", "19:30"), "EVENING_COLLECTION_TIME"
        ),
        monitoring_window_days=window_days,
        portal_open_time=parse_hhmm(os.getenv("PORTAL_OPEN_TIME", "05:30"), "PORTAL_OPEN_TIME"),
        portal_close_time=parse_hhmm(os.getenv("PORTAL_CLOSE_TIME", "23:30"), "PORTAL_CLOSE_TIME"),
        stale_data_threshold_hours=int(os.getenv("STALE_DATA_THRESHOLD_HOURS", "14")),
        playwright_headless=_parse_bool(os.getenv("PLAYWRIGHT_HEADLESS", "false"), default=False),
        playwright_timeout_ms=int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000")),
        playwright_user_data_dir=user_data_dir,
        consent_wait_seconds=max(0, int(os.getenv("CONSENT_WAIT_SECONDS", "60"))),
        request_min_delay_seconds=min_delay,
        request_max_delay_seconds=max_delay,
        max_retries_per_page=max(0, int(os.getenv("MAX_RETRIES_PER_PAGE", "2"))),
        retry_backoff_seconds=max(1.0, float(os.getenv("RETRY_BACKOFF_SECONDS", "5.0"))),
        save_diagnostic_screenshots=_parse_bool(
            os.getenv("SAVE_DIAGNOSTIC_SCREENSHOTS", "true"), default=True
        ),
        screenshots_dir=_resolve_path(os.getenv("SCREENSHOTS_DIR", "data/screenshots"), base_dir),
        exports_dir=_resolve_path(os.getenv("EXPORTS_DIR", "data/exports"), base_dir),
        inspection_dir=_resolve_path(os.getenv("INSPECTION_DIR", "data/inspection"), base_dir),
        selectors_config_path=_resolve_path(
            os.getenv("SELECTORS_CONFIG_PATH", "config/selectors.json"), base_dir
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
