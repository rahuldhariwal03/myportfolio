"""Repository layer for collection runs, safari dates, zones, immutable snapshots,
change events, and diagnostic collection logs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.database.backend import DatabaseBackend
from src.date_window import describe_safari_date, format_iso_timestamp, now_in_timezone

VALID_RUN_STATUSES = {"running", "completed", "partial", "blocked", "failed", "interrupted"}
VALID_SESSIONS = {"morning", "afternoon"}


class SafariMonitorRepository:
    """High-level, append-safe data access layer over `DatabaseBackend`."""

    def __init__(self, backend: DatabaseBackend, timezone_name: str = "Asia/Kolkata") -> None:
        self.backend = backend
        self.timezone_name = timezone_name

    # ------------------------------------------------------------------
    # Collection runs & interruption recovery
    # ------------------------------------------------------------------
    def recover_interrupted_runs(self, note: str = "Marked interrupted during recovery check") -> int:
        """Detect stale `running` collection runs and mark them `interrupted`."""
        ts = format_iso_timestamp(now_in_timezone(self.timezone_name))
        return self.backend.execute(
            """
            UPDATE collection_runs
               SET status = 'interrupted',
                   completed_at = COALESCE(completed_at, ?),
                   error_summary = CASE
                       WHEN error_summary IS NULL OR error_summary = '' THEN ?
                       ELSE error_summary || ' | ' || ?
                   END
             WHERE status = 'running'
            """,
            (ts, note, note),
        )

    def start_collection_run(
        self,
        collection_type: str,
        date_window_start: date | str,
        date_window_end: date | str,
        started_at: datetime | str | None = None,
        is_demo: bool = False,
        source_url: str | None = None,
    ) -> int:
        """Create a new `collection_runs` row with status `'running'`."""
        start_iso = (
            started_at
            if isinstance(started_at, str)
            else format_iso_timestamp(started_at or now_in_timezone(self.timezone_name))
        )
        win_start = (
            date_window_start.isoformat()
            if isinstance(date_window_start, date)
            else date_window_start
        )
        win_end = (
            date_window_end.isoformat() if isinstance(date_window_end, date) else date_window_end
        )
        return self.backend.insert_returning_id(
            """
            INSERT INTO collection_runs (
                started_at, completed_at, collection_type,
                date_window_start, date_window_end, status,
                error_summary, is_demo, source_url
            ) VALUES (?, NULL, ?, ?, ?, 'running', NULL, ?, ?)
            """,
            (start_iso, collection_type, win_start, win_end, 1 if is_demo else 0, source_url),
        )

    def complete_collection_run(
        self,
        run_id: int,
        status: str,
        completed_at: datetime | str | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Finalize a collection run with its terminal status and optional error summary."""
        if status not in VALID_RUN_STATUSES or status == "running":
            raise ValueError(f"Invalid terminal run status: {status!r}")
        end_iso = (
            completed_at
            if isinstance(completed_at, str)
            else format_iso_timestamp(completed_at or now_in_timezone(self.timezone_name))
        )
        self.backend.execute(
            """
            UPDATE collection_runs
               SET completed_at = ?,
                   status = ?,
                   error_summary = ?
             WHERE id = ?
            """,
            (end_iso, status, error_summary, run_id),
        )

    def get_collection_run(self, run_id: int) -> dict[str, Any] | None:
        return self.backend.fetch_one("SELECT * FROM collection_runs WHERE id = ?", (run_id,))

    def list_collection_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.backend.fetch_all(
            "SELECT * FROM collection_runs ORDER BY started_at DESC, id DESC LIMIT ?",
            (limit,),
        )

    def get_latest_successful_run(self) -> dict[str, Any] | None:
        """Return the most recent run that captured valid observations (`completed` or `partial`)."""
        return self.backend.fetch_one(
            """
            SELECT * FROM collection_runs
             WHERE status IN ('completed', 'partial')
             ORDER BY COALESCE(completed_at, started_at) DESC, id DESC
             LIMIT 1
            """
        )

    # ------------------------------------------------------------------
    # Zones
    # ------------------------------------------------------------------
    def upsert_zone(
        self,
        zone_name: str,
        source_zone_identifier: str | None = None,
        entry_gate: str | None = None,
        safari_mode: str = "jeep_permit",
        unit_label: str = "Jeep permits",
        operating_season: str | None = None,
    ) -> int:
        """Ensure a zone exists and return its `id`. Updates `source_zone_identifier` only if newly verified."""
        cleaned = zone_name.strip()
        existing = self.backend.fetch_one(
            "SELECT id, source_zone_identifier FROM zones WHERE LOWER(zone_name) = LOWER(?)",
            (cleaned,),
        )
        if existing is not None:
            if source_zone_identifier and not existing["source_zone_identifier"]:
                self.backend.execute(
                    "UPDATE zones SET source_zone_identifier = ? WHERE id = ?",
                    (source_zone_identifier, existing["id"]),
                )
            return int(existing["id"])

        return self.backend.insert_returning_id(
            """
            INSERT INTO zones (
                zone_name, source_zone_identifier, entry_gate,
                safari_mode, unit_label, operating_season, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (cleaned, source_zone_identifier, entry_gate, safari_mode, unit_label, operating_season),
        )

    def get_zone_by_name(self, zone_name: str) -> dict[str, Any] | None:
        return self.backend.fetch_one(
            "SELECT * FROM zones WHERE LOWER(zone_name) = LOWER(?)",
            (zone_name.strip(),),
        )

    def list_zones(self, active_only: bool = True) -> list[dict[str, Any]]:
        if active_only:
            return self.backend.fetch_all(
                "SELECT * FROM zones WHERE is_active = 1 ORDER BY id ASC"
            )
        return self.backend.fetch_all("SELECT * FROM zones ORDER BY id ASC")

    # ------------------------------------------------------------------
    # Safari dates
    # ------------------------------------------------------------------
    def ensure_safari_date(
        self,
        safari_date: date | str,
        operating_status: str = "unknown",
        observed_at: str | None = None,
    ) -> int:
        """Register a safari date with its weekday/weekend metadata and latest operating status."""
        iso_date, weekday, is_weekend = describe_safari_date(safari_date)
        existing = self.backend.fetch_one(
            "SELECT id, operating_status FROM safari_dates WHERE safari_date = ?",
            (iso_date,),
        )
        if existing is not None:
            if operating_status != "unknown":
                self.backend.execute(
                    """
                    UPDATE safari_dates
                       SET operating_status = ?,
                           last_observed_at = COALESCE(?, last_observed_at)
                     WHERE id = ?
                    """,
                    (operating_status, observed_at, existing["id"]),
                )
            return int(existing["id"])

        return self.backend.insert_returning_id(
            """
            INSERT INTO safari_dates (
                safari_date, weekday, is_weekend, operating_status, last_observed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (iso_date, weekday, 1 if is_weekend else 0, operating_status, observed_at),
        )

    def list_safari_dates(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if start_date:
            clauses.append("safari_date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("safari_date <= ?")
            params.append(end_date)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.backend.fetch_all(
            f"SELECT * FROM safari_dates {where_sql} ORDER BY safari_date ASC",
            params,
        )

    # ------------------------------------------------------------------
    # Append-only availability snapshots
    # ------------------------------------------------------------------
    def record_snapshot(
        self,
        *,
        collection_run_id: int,
        safari_date: date | str,
        zone_id: int,
        session: str,
        available_slots: int | None,
        total_capacity: int | None = None,
        raw_displayed_value: str | None = None,
        raw_capacity_value: str | None = None,
        collection_status: str = "success",
        confidence: str = "verified",
        source_section: str | None = None,
        error_details: str | None = None,
        date_operating_status: str = "open",
        captured_at: datetime | str | None = None,
    ) -> int:
        """Append a single immutable availability observation.

        Enforces:
        - `session` must be `'morning'` or `'afternoon'`.
        - Missing/error observations keep `available_slots = None` (never coerced to 0).
        - If `available_slots > total_capacity`, rejects via validation error unless parsed
          as a `parse_error` with `available_slots = None`.
        - Duplicate `(collection_run_id, safari_date, zone_id, session)` raises an IntegrityError.
        """
        norm_session = session.strip().lower()
        if norm_session not in VALID_SESSIONS:
            raise ValueError(f"session must be 'morning' or 'afternoon', got {session!r}")

        if collection_status == "success" and available_slots is None:
            raise ValueError(
                "collection_status='success' requires a non-null integer available_slots; "
                "use 'missing' or 'parse_error' for unavailable observations."
            )
        if collection_status != "success" and available_slots is not None:
            raise ValueError(
                f"collection_status={collection_status!r} must store available_slots=None, "
                f"got {available_slots!r}."
            )
        if available_slots is not None and available_slots < 0:
            raise ValueError(f"available_slots cannot be negative: {available_slots}")
        if total_capacity is not None and total_capacity <= 0:
            raise ValueError(f"total_capacity must be positive when present: {total_capacity}")
        if (
            available_slots is not None
            and total_capacity is not None
            and available_slots > total_capacity
        ):
            raise ValueError(
                f"available_slots ({available_slots}) cannot exceed total_capacity ({total_capacity})"
            )

        captured_iso = (
            captured_at
            if isinstance(captured_at, str)
            else format_iso_timestamp(captured_at or now_in_timezone(self.timezone_name))
        )
        iso_date = safari_date.isoformat() if isinstance(safari_date, date) else safari_date
        self.ensure_safari_date(
            iso_date,
            operating_status=date_operating_status or "unknown",
            observed_at=captured_iso,
        )

        return self.backend.insert_returning_id(
            """
            INSERT INTO availability_snapshots (
                collection_run_id, safari_date, zone_id, session,
                available_slots, total_capacity,
                raw_displayed_value, raw_capacity_value,
                collection_status, confidence,
                source_section, error_details, date_operating_status,
                captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                collection_run_id,
                iso_date,
                zone_id,
                norm_session,
                available_slots,
                total_capacity,
                raw_displayed_value,
                raw_capacity_value,
                collection_status,
                confidence,
                source_section,
                error_details,
                date_operating_status,
                captured_iso,
            ),
        )

    def get_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        return self.backend.fetch_one(
            "SELECT * FROM availability_snapshots WHERE id = ?",
            (snapshot_id,),
        )

    def get_previous_valid_snapshot(
        self,
        *,
        safari_date: str,
        zone_id: int,
        session: str,
        before_captured_at: str,
        current_snapshot_id: int,
    ) -> dict[str, Any] | None:
        """Find the immediately preceding VALID snapshot for the same date, zone, and session.

        Skips any missing, closed, paused, blocked, or parse-error snapshots so
        missing data is NEVER treated as zero.
        """
        return self.backend.fetch_one(
            """
            SELECT *
              FROM availability_snapshots
             WHERE safari_date = ?
               AND zone_id = ?
               AND session = ?
               AND collection_status = 'success'
               AND available_slots IS NOT NULL
               AND id != ?
               AND (
                   captured_at < ?
                   OR (captured_at = ? AND id < ?)
               )
             ORDER BY captured_at DESC, id DESC
             LIMIT 1
            """,
            (
                safari_date,
                zone_id,
                session,
                current_snapshot_id,
                before_captured_at,
                before_captured_at,
                current_snapshot_id,
            ),
        )

    def list_snapshots_for_run(self, collection_run_id: int) -> list[dict[str, Any]]:
        return self.backend.fetch_all(
            """
            SELECT s.*, z.zone_name, z.safari_mode, z.unit_label
              FROM availability_snapshots s
              JOIN zones z ON z.id = s.zone_id
             WHERE s.collection_run_id = ?
             ORDER BY s.safari_date ASC, z.zone_name ASC, s.session ASC, s.id ASC
            """,
            (collection_run_id,),
        )

    # ------------------------------------------------------------------
    # Append-only change events
    # ------------------------------------------------------------------
    def record_change_event(
        self,
        *,
        collection_run_id: int,
        previous_snapshot_id: int,
        current_snapshot_id: int,
        safari_date: str,
        zone_id: int,
        session: str,
        previous_available: int,
        current_available: int,
        change_amount: int,
        availability_reduction: int,
        availability_increase: int,
        previous_capacity: int | None,
        current_capacity: int | None,
        capacity_occupied_pct: float | None,
        change_type: str,
        previous_captured_at: str,
        observed_at: str,
    ) -> int:
        """Insert an immutable availability change event."""
        return self.backend.insert_returning_id(
            """
            INSERT INTO change_events (
                collection_run_id, previous_snapshot_id, current_snapshot_id,
                safari_date, zone_id, session,
                previous_available, current_available,
                change_amount, availability_reduction, availability_increase,
                previous_capacity, current_capacity, capacity_occupied_pct,
                change_type, previous_captured_at, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                collection_run_id,
                previous_snapshot_id,
                current_snapshot_id,
                safari_date,
                zone_id,
                session,
                previous_available,
                current_available,
                change_amount,
                availability_reduction,
                availability_increase,
                previous_capacity,
                current_capacity,
                capacity_occupied_pct,
                change_type,
                previous_captured_at,
                observed_at,
            ),
        )

    def list_change_events(
        self,
        *,
        observed_date_prefix: str | None = None,
        safari_date: str | None = None,
        zone_id: int | None = None,
        session: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if observed_date_prefix:
            clauses.append("SUBSTR(ce.observed_at, 1, 10) = ?")
            params.append(observed_date_prefix)
        if safari_date:
            clauses.append("ce.safari_date = ?")
            params.append(safari_date)
        if zone_id is not None:
            clauses.append("ce.zone_id = ?")
            params.append(zone_id)
        if session:
            clauses.append("ce.session = ?")
            params.append(session.lower())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return self.backend.fetch_all(
            f"""
            SELECT ce.*, z.zone_name, z.safari_mode, z.unit_label,
                   cr.collection_type, cr.is_demo
              FROM change_events ce
              JOIN zones z ON z.id = ce.zone_id
              JOIN collection_runs cr ON cr.id = ce.collection_run_id
              {where_sql}
             ORDER BY ce.observed_at DESC, ce.id DESC
             LIMIT ?
            """,
            params,
        )

    # ------------------------------------------------------------------
    # Collection logs
    # ------------------------------------------------------------------
    def log_collection_event(
        self,
        *,
        collection_run_id: int,
        page_or_zone: str,
        status: str,
        error_message: str | None = None,
        screenshot_path: str | None = None,
        logged_at: datetime | str | None = None,
    ) -> int:
        log_iso = (
            logged_at
            if isinstance(logged_at, str)
            else format_iso_timestamp(logged_at or now_in_timezone(self.timezone_name))
        )
        return self.backend.insert_returning_id(
            """
            INSERT INTO collection_logs (
                collection_run_id, page_or_zone, status,
                error_message, screenshot_path, logged_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (collection_run_id, page_or_zone, status, error_message, screenshot_path, log_iso),
        )

    def list_collection_logs(
        self,
        *,
        collection_run_id: int | None = None,
        errors_only: bool = False,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if collection_run_id is not None:
            clauses.append("cl.collection_run_id = ?")
            params.append(collection_run_id)
        if errors_only:
            clauses.append("cl.status NOT IN ('ok', 'success', 'info')")
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return self.backend.fetch_all(
            f"""
            SELECT cl.*, cr.collection_type, cr.started_at AS run_started_at, cr.is_demo
              FROM collection_logs cl
              JOIN collection_runs cr ON cr.id = cl.collection_run_id
              {where_sql}
             ORDER BY cl.logged_at DESC, cl.id DESC
             LIMIT ?
            """,
            params,
        )

    # ------------------------------------------------------------------
    # Dataset meta summary
    # ------------------------------------------------------------------
    def get_database_summary(self) -> dict[str, int]:
        """Return quick row counts across all 6 core tables."""
        tables = (
            "collection_runs",
            "safari_dates",
            "zones",
            "availability_snapshots",
            "change_events",
            "collection_logs",
        )
        counts: dict[str, int] = {}
        for table in tables:
            row = self.backend.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
            counts[table] = int(row["cnt"]) if row else 0
        demo_row = self.backend.fetch_one(
            "SELECT COUNT(*) AS cnt FROM collection_runs WHERE is_demo = 1"
        )
        counts["demo_runs"] = int(demo_row["cnt"]) if demo_row else 0
        return counts
