"""Read-only data service prepared for future FastAPI integration (Section 9).

Per project scope, NO public HTTP API or customer-facing booking endpoint is
launched in v1. However, these pure read-only methods map 1:1 to the planned
future endpoints and return JSON-serializable stored observations with their
exact collection timestamps and demo/confidence metadata:

- `get_zones()`               -> future `GET /api/zones`
- `get_availability()`        -> future `GET /api/availability`
- `get_availability_by_date()`-> future `GET /api/availability/{date}`
- `get_daily_changes()`       -> future `GET /api/changes/daily`
- `get_history()`             -> future `GET /api/history`
"""

from __future__ import annotations

from typing import Any

from src.analytics.change_detector import ChangeDetectionService, compute_capacity_occupied_pct
from src.database.repository import SafariMonitorRepository


class ReadOnlyQueryService:
    """Read-only projection layer returning stored observations and timestamps only."""

    def __init__(self, repo: SafariMonitorRepository, timezone_name: str = "Asia/Kolkata") -> None:
        self.repo = repo
        self.changes = ChangeDetectionService(repo, timezone_name=timezone_name)

    def get_zones(self) -> list[dict[str, Any]]:
        """Data contract for future `GET /api/zones`."""
        return self.repo.list_zones(active_only=True)

    def get_availability(
        self,
        *,
        zone_name: str | None = None,
        session: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Data contract for future `GET /api/availability` (latest stored observation per slot)."""
        clauses = ["1 = 1"]
        params: list[Any] = []
        if zone_name:
            clauses.append("LOWER(z.zone_name) = LOWER(?)")
            params.append(zone_name)
        if session:
            clauses.append("s.session = ?")
            params.append(session.lower())
        if start_date:
            clauses.append("s.safari_date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("s.safari_date <= ?")
            params.append(end_date)

        rows = self.repo.backend.fetch_all(
            f"""
            SELECT s.id AS snapshot_id,
                   s.safari_date,
                   sd.weekday,
                   sd.is_weekend,
                   z.id AS zone_id,
                   z.zone_name,
                   z.source_zone_identifier,
                   z.safari_mode,
                   z.unit_label,
                   s.session,
                   s.available_slots,
                   s.total_capacity,
                   s.raw_displayed_value,
                   s.collection_status,
                   s.confidence,
                   s.captured_at,
                   cr.is_demo
              FROM availability_snapshots s
              JOIN (
                  SELECT safari_date, zone_id, session, MAX(id) AS latest_id
                    FROM availability_snapshots
                   GROUP BY safari_date, zone_id, session
              ) latest ON latest.latest_id = s.id
              JOIN zones z ON z.id = s.zone_id
              JOIN safari_dates sd ON sd.safari_date = s.safari_date
              JOIN collection_runs cr ON cr.id = s.collection_run_id
             WHERE {' AND '.join(clauses)}
             ORDER BY s.safari_date ASC, z.zone_name ASC, s.session ASC
            """,
            params,
        )
        for row in rows:
            row["is_weekend"] = bool(row["is_weekend"])
            row["is_demo"] = bool(row["is_demo"])
            row["capacity_occupied_pct"] = compute_capacity_occupied_pct(
                row["available_slots"], row["total_capacity"], confidence=row["confidence"]
            )
        return rows

    def get_availability_by_date(self, safari_date: str) -> list[dict[str, Any]]:
        """Data contract for future `GET /api/availability/{date}`."""
        return self.get_availability(start_date=safari_date, end_date=safari_date)

    def get_daily_changes(self, observed_date: str | None = None) -> dict[str, Any]:
        """Data contract for future `GET /api/changes/daily`."""
        summary_jeep = self.changes.summarize_daily_changes(
            observed_date=observed_date, safari_mode="jeep_permit"
        )
        target_date = summary_jeep["observed_date"] or observed_date
        summary_canter = self.changes.summarize_daily_changes(
            observed_date=target_date, safari_mode="canter_seat"
        )
        events = (
            self.repo.list_change_events(observed_date_prefix=target_date, limit=2000)
            if target_date
            else []
        )
        return {
            "observed_date": target_date,
            "note": (
                "Slot reductions represent observed decreases in publicly displayed availability, "
                "not confirmed bookings."
            ),
            "jeep_permits_summary": summary_jeep,
            "canter_seats_summary": summary_canter,
            "events": events,
        }

    def get_history(
        self,
        *,
        safari_date: str | None = None,
        zone_name: str | None = None,
        session: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Data contract for future `GET /api/history` (chronological snapshot series)."""
        clauses = ["1 = 1"]
        params: list[Any] = []
        if safari_date:
            clauses.append("s.safari_date = ?")
            params.append(safari_date)
        if zone_name:
            clauses.append("LOWER(z.zone_name) = LOWER(?)")
            params.append(zone_name)
        if session:
            clauses.append("s.session = ?")
            params.append(session.lower())
        params.append(limit)

        rows = self.repo.backend.fetch_all(
            f"""
            SELECT s.id AS snapshot_id,
                   s.collection_run_id,
                   s.safari_date,
                   z.zone_name,
                   z.safari_mode,
                   z.unit_label,
                   s.session,
                   s.available_slots,
                   s.total_capacity,
                   s.raw_displayed_value,
                   s.collection_status,
                   s.confidence,
                   s.captured_at,
                   cr.collection_type,
                   cr.is_demo
              FROM availability_snapshots s
              JOIN zones z ON z.id = s.zone_id
              JOIN collection_runs cr ON cr.id = s.collection_run_id
             WHERE {' AND '.join(clauses)}
             ORDER BY s.captured_at ASC, s.id ASC
             LIMIT ?
            """,
            params,
        )
        for row in rows:
            row["is_demo"] = bool(row["is_demo"])
        return rows
