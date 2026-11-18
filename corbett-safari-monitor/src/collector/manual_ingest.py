"""Audited manual & CSV observation ingestion for real operator-verified portal checks.

Gives a beginner operator two zero-friction, 100% Terms-compliant ways to record
publicly displayed availability from https://safari.corbettgov.org/ into the live
database alongside (or before configuring) automated Playwright runs:
  1. Direct per-date zone form inside the Streamlit dashboard.
  2. Downloadable rolling-window CSV template + one-click CSV import.

Every value passes through the exact same `parse_availability_text` validation,
preserves `raw_displayed_value`, keeps missing values as `NULL` (never `0`), writes
append-only snapshots, and runs automatic Phase 5 availability change detection.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import pandas as pd

from src.analytics.change_detector import ChangeDetectionService
from src.collector.parser import (
    aggregate_date_operating_status,
    normalize_zone_name,
    parse_availability_text,
)
from src.database.repository import SafariMonitorRepository
from src.date_window import calculate_rolling_window, format_iso_timestamp, now_in_timezone


@dataclass(frozen=True)
class ManualObservationRow:
    """Single zone/date observation row entered by the operator or loaded from CSV."""

    safari_date: str
    zone_name: str
    morning_raw: str | None = None
    afternoon_raw: str | None = None
    morning_capacity_raw: str | None = None
    afternoon_capacity_raw: str | None = None


@dataclass(frozen=True)
class ManualIngestResult:
    """Outcome of recording a batch of operator-observed availability rows."""

    run_id: int
    status: str
    snapshots_recorded: int
    valid_snapshots: int
    skipped_blank_cells: int
    issue_cells: int
    change_events_recorded: int
    warnings: list[str]


def generate_observation_csv_template(
    zones: list[dict[str, object]],
    *,
    window_days: int = 7,
    timezone_name: str = "Asia/Kolkata",
    reference_date: date | None = None,
) -> bytes:
    """Create a clean CSV template covering the next N safari dates and all active zones."""
    window = calculate_rolling_window(
        reference_date, window_days=window_days, timezone_name=timezone_name
    )
    rows: list[dict[str, str]] = []
    for iso_d in window.iso_dates:
        for z in zones:
            rows.append(
                {
                    "safari_date": iso_d,
                    "zone_name": str(z["zone_name"]),
                    "morning_raw": "",
                    "afternoon_raw": "",
                    "morning_capacity_raw": "",
                    "afternoon_capacity_raw": "",
                }
            )
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")


def parse_observation_csv(csv_bytes: bytes) -> list[ManualObservationRow]:
    """Parse an uploaded CSV file into `ManualObservationRow` items."""
    text = csv_bytes.decode("utf-8-sig")
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    required_cols = {"safari_date", "zone_name", "morning_raw", "afternoon_raw"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {', '.join(sorted(missing))}. "
            "Download the template first to get the exact column headers."
        )

    rows: list[ManualObservationRow] = []
    for idx, rec in df.iterrows():
        s_date = str(rec.get("safari_date", "")).strip()
        z_name = str(rec.get("zone_name", "")).strip()
        m_raw = str(rec.get("morning_raw", "")).strip()
        a_raw = str(rec.get("afternoon_raw", "")).strip()
        m_cap = str(rec.get("morning_capacity_raw", "")).strip() or None
        a_cap = str(rec.get("afternoon_capacity_raw", "")).strip() or None

        # Skip completely empty template rows so operators only need to fill observed rows
        if not m_raw and not a_raw:
            continue
        if not s_date or not z_name:
            raise ValueError(f"Row {int(idx) + 2}: both safari_date and zone_name are required.")
        # Validate ISO date format
        try:
            date.fromisoformat(s_date)
        except ValueError as exc:
            raise ValueError(
                f"Row {int(idx) + 2}: invalid safari_date {s_date!r} (expected YYYY-MM-DD)."
            ) from exc

        rows.append(
            ManualObservationRow(
                safari_date=s_date,
                zone_name=z_name,
                morning_raw=m_raw or None,
                afternoon_raw=a_raw or None,
                morning_capacity_raw=m_cap,
                afternoon_capacity_raw=a_cap,
            )
        )
    return rows


def ingest_manual_observations(
    repo: SafariMonitorRepository,
    rows: Iterable[ManualObservationRow],
    *,
    collection_type: str = "manual",
    source_section: str = "operator_manual_entry",
    unit_validated: bool = True,
    record_blank_as_missing: bool = False,
    captured_at: datetime | None = None,
    timezone_name: str = "Asia/Kolkata",
) -> ManualIngestResult:
    """Validate and append operator-recorded observations into the LIVE database."""
    row_list = list(rows)
    if not row_list:
        raise ValueError("No observations provided. Fill at least one Morning or Afternoon value.")

    if collection_type not in {"manual", "morning", "evening"}:
        raise ValueError(f"collection_type must be manual, morning, or evening; got {collection_type!r}")

    obs_dt = captured_at or now_in_timezone(timezone_name)
    obs_iso = format_iso_timestamp(obs_dt)

    valid_dates = sorted({date.fromisoformat(r.safari_date).isoformat() for r in row_list})
    win_start = valid_dates[0]
    win_end = valid_dates[-1]

    known_zones = {z["zone_name"].lower(): z for z in repo.list_zones(active_only=False)}
    change_service = ChangeDetectionService(repo, timezone_name=timezone_name)

    snapshots_recorded = 0
    valid_snapshots = 0
    skipped_blank = 0
    issue_cells = 0
    warnings: list[str] = []

    with repo.backend.transaction():
        run_id = repo.start_collection_run(
            collection_type=collection_type,
            date_window_start=win_start,
            date_window_end=win_end,
            started_at=obs_iso,
            is_demo=False,
            source_url=f"https://safari.corbettgov.org/ ({source_section})",
        )

        seen_keys: set[tuple[str, int, str]] = set()
        statuses_by_date: dict[str, list[str]] = {}
        for item in row_list:
            canonical_lookup = normalize_zone_name(item.zone_name).lower()
            z_meta = known_zones.get(canonical_lookup) or known_zones.get(
                item.zone_name.strip().lower()
            )
            if z_meta is None:
                warnings.append(f"Skipped unknown zone {item.zone_name!r} on {item.safari_date}.")
                issue_cells += 1
                continue
            zone_id = int(z_meta["id"])
            z_canonical = str(z_meta["zone_name"])

            for session, raw_val, raw_cap in (
                ("morning", item.morning_raw, item.morning_capacity_raw),
                ("afternoon", item.afternoon_raw, item.afternoon_capacity_raw),
            ):
                cleaned_val = (raw_val or "").strip()
                if not cleaned_val and not record_blank_as_missing:
                    skipped_blank += 1
                    continue

                dedup_key = (item.safari_date, zone_id, session)
                if dedup_key in seen_keys:
                    warnings.append(
                        f"Skipped duplicate row for {z_canonical} / {item.safari_date} / {session}."
                    )
                    continue
                seen_keys.add(dedup_key)

                parsed = parse_availability_text(
                    cleaned_val if cleaned_val else None,
                    raw_capacity=raw_cap,
                    unit_validated=unit_validated,
                )
                statuses_by_date.setdefault(item.safari_date, []).append(parsed.collection_status)
                date_op = aggregate_date_operating_status(statuses_by_date[item.safari_date])
                repo.record_snapshot(
                    collection_run_id=run_id,
                    safari_date=item.safari_date,
                    zone_id=zone_id,
                    session=session,
                    available_slots=parsed.available_slots,
                    total_capacity=parsed.total_capacity,
                    raw_displayed_value=parsed.raw_displayed_value,
                    raw_capacity_value=parsed.raw_capacity_value,
                    collection_status=parsed.collection_status,
                    confidence=parsed.confidence,
                    source_section=source_section,
                    error_details=parsed.error_details,
                    date_operating_status=date_op,
                    captured_at=obs_iso,
                )
                snapshots_recorded += 1
                if parsed.collection_status == "success":
                    valid_snapshots += 1
                elif parsed.collection_status in {"missing", "parse_error", "error"}:
                    issue_cells += 1
                    if parsed.error_details:
                        warnings.append(
                            f"{z_canonical} {item.safari_date} ({session}): {parsed.error_details}"
                        )
                    repo.log_collection_event(
                        collection_run_id=run_id,
                        page_or_zone=f"{z_canonical} / {item.safari_date} / {session}",
                        status=parsed.collection_status,
                        error_message=parsed.error_details,
                        logged_at=obs_iso,
                    )

        change_ids = change_service.detect_and_record_for_run(run_id)
        if snapshots_recorded == 0:
            status = "failed"
            summary = "No non-empty valid zone observations were provided."
        elif issue_cells > 0:
            status = "partial"
            summary = f"{issue_cells} cell(s) stored as NULL with status notes."
        else:
            status = "completed"
            summary = None

        repo.log_collection_event(
            collection_run_id=run_id,
            page_or_zone=source_section,
            status="ok" if status == "completed" else status,
            error_message=(
                f"Recorded {snapshots_recorded} snapshot(s) ({valid_snapshots} valid) "
                f"and {len(change_ids)} change event(s)."
            ),
            logged_at=obs_iso,
        )
        repo.complete_collection_run(
            run_id, status=status, completed_at=obs_iso, error_summary=summary
        )

    return ManualIngestResult(
        run_id=run_id,
        status=status,
        snapshots_recorded=snapshots_recorded,
        valid_snapshots=valid_snapshots,
        skipped_blank_cells=skipped_blank,
        issue_cells=issue_cells,
        change_events_recorded=len(change_ids),
        warnings=warnings,
    )
