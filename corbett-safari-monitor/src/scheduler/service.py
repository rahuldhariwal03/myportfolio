"""Configurable morning & evening collection scheduler (Phase 7).

Features:
- Driven entirely by `.env` (`MORNING_COLLECTION_TIME`, `EVENING_COLLECTION_TIME`,
  `COLLECTION_TIMEZONE`, `MONITORING_WINDOW_DAYS`) — zero hardcoded run times.
- Enforces `Asia/Kolkata` timezone by default.
- Prevents overlapping collection jobs (`max_instances=1`, `coalesce=True`).
- Validates that configured schedule times fall within the official portal's
  published operating window (05:30–23:30 IST).
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from src.collector.playwright_collector import CollectionRunResult, SafariAvailabilityCollector
from src.config import AppConfig
from src.database import SafariMonitorRepository, create_backend, initialize_schema
from src.date_window import calculate_rolling_window, now_in_timezone

logger = logging.getLogger(__name__)


def validate_schedule_times(config: AppConfig) -> list[str]:
    """Return any configuration warnings for the chosen morning/evening times."""
    warnings: list[str] = []
    if config.morning_collection_time == config.evening_collection_time:
        warnings.append(
            "MORNING_COLLECTION_TIME and EVENING_COLLECTION_TIME are identical; "
            "set distinct morning and evening HH:MM values."
        )
    for label, sched_time in (
        ("MORNING_COLLECTION_TIME", config.morning_collection_time),
        ("EVENING_COLLECTION_TIME", config.evening_collection_time),
    ):
        if not _time_in_range(sched_time, config.portal_open_time, config.portal_close_time):
            warnings.append(
                f"{label} ({sched_time.strftime('%H:%M')}) is outside the portal's "
                f"published operating hours ({config.portal_open_time.strftime('%H:%M')}–"
                f"{config.portal_close_time.strftime('%H:%M')} {config.timezone_name})."
            )
    return warnings


def _time_in_range(target: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= target <= end
    return target >= start or target <= end


def build_cron_triggers(config: AppConfig) -> dict[str, CronTrigger]:
    """Build morning and evening CronTriggers in the configured timezone."""
    tz = ZoneInfo(config.timezone_name)
    return {
        "morning_collection": CronTrigger(
            hour=config.morning_collection_time.hour,
            minute=config.morning_collection_time.minute,
            timezone=tz,
        ),
        "evening_collection": CronTrigger(
            hour=config.evening_collection_time.hour,
            minute=config.evening_collection_time.minute,
            timezone=tz,
        ),
    }


def preview_upcoming_runs(
    config: AppConfig, reference_time: datetime | None = None
) -> list[dict[str, str]]:
    """Compute the next scheduled morning and evening fire times + their 30-day rolling windows."""
    ref = reference_time or now_in_timezone(config.timezone_name)
    triggers = build_cron_triggers(config)
    previews: list[dict[str, str]] = []

    for job_id, trigger in triggers.items():
        next_fire = trigger.get_next_fire_time(previous_fire_time=None, now=ref)
        if next_fire is None:
            continue
        window = calculate_rolling_window(
            next_fire,
            window_days=config.monitoring_window_days,
            timezone_name=config.timezone_name,
        )
        previews.append(
            {
                "job_id": job_id,
                "collection_type": "morning" if "morning" in job_id else "evening",
                "next_run_at": next_fire.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "timezone": config.timezone_name,
                "window_start": window.start_date.isoformat(),
                "window_end": window.end_date.isoformat(),
                "window_days": str(window.window_days),
            }
        )

    previews.sort(key=lambda item: item["next_run_at"])
    return previews


def execute_scheduled_run(config: AppConfig, collection_type: str) -> CollectionRunResult:
    """Job callback invoked by APScheduler or manual admin trigger."""
    logger.info("Starting %s collection run (TZ=%s)...", collection_type, config.timezone_name)
    backend = create_backend(config.database_url)
    initialize_schema(backend, seed_official_zones=True)
    repo = SafariMonitorRepository(backend, timezone_name=config.timezone_name)
    collector = SafariAvailabilityCollector(config=config, repo=repo)
    result = collector.run(collection_type=collection_type)
    logger.info(
        "Finished %s run #%d -> status=%s, snapshots=%d, changes=%d",
        collection_type,
        result.run_id,
        result.status,
        result.snapshots_recorded,
        result.change_events_recorded,
    )
    return result


def create_scheduler(
    config: AppConfig,
    *,
    blocking: bool = True,
    job_runner: Callable[[AppConfig, str], CollectionRunResult] = execute_scheduled_run,
) -> BlockingScheduler | BackgroundScheduler:
    """Create and configure the two-run-per-day scheduler without hardcoding times."""
    tz = ZoneInfo(config.timezone_name)
    scheduler_cls = BlockingScheduler if blocking else BackgroundScheduler
    scheduler = scheduler_cls(
        timezone=tz,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,
        },
    )

    triggers = build_cron_triggers(config)
    scheduler.add_job(
        job_runner,
        trigger=triggers["morning_collection"],
        args=[config, "morning"],
        id="morning_collection",
        name="Morning Safari Availability Collection",
        replace_existing=True,
    )
    scheduler.add_job(
        job_runner,
        trigger=triggers["evening_collection"],
        args=[config, "evening"],
        id="evening_collection",
        name="Evening Safari Availability Collection",
        replace_existing=True,
    )
    return scheduler
