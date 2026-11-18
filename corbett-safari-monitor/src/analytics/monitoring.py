"""Collection health monitoring, missing date/zone detection, staleness checks, and CSV exports."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from src.database.repository import SafariMonitorRepository
from src.date_window import now_in_timezone, to_timezone


class CollectionMonitoringService:
    """Evaluates collection reliability, freshness, missing coverage, and CSV export datasets."""

    def __init__(
        self,
        repo: SafariMonitorRepository,
        timezone_name: str = "Asia/Kolkata",
        stale_threshold_hours: int = 14,
    ) -> None:
        self.repo = repo
        self.timezone_name = timezone_name
        self.stale_threshold_hours = stale_threshold_hours

    def get_freshness_status(self, reference_now: datetime | None = None) -> dict[str, Any]:
        """Report the last successful observation timestamp and explicitly flag stale data."""
        latest_run = self.repo.get_latest_successful_run()
        if latest_run is None:
            return {
                "has_successful_run": False,
                "last_success_at": None,
                "age_hours": None,
                "is_stale": True,
                "status_label": "No successful collection yet",
                "latest_run": None,
            }

        ts_str = latest_run["completed_at"] or latest_run["started_at"]
        last_dt = to_timezone(datetime.fromisoformat(ts_str), self.timezone_name)
        current_dt = to_timezone(
            reference_now or now_in_timezone(self.timezone_name),
            self.timezone_name,
        )
        age_hours = round(max(0.0, (current_dt - last_dt).total_seconds() / 3600.0), 2)
        is_stale = age_hours > self.stale_threshold_hours

        return {
            "has_successful_run": True,
            "last_success_at": last_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "last_success_iso": ts_str,
            "age_hours": age_hours,
            "is_stale": is_stale,
            "status_label": (
                f"Stale ({age_hours:.1f}h old — exceeds {self.stale_threshold_hours}h threshold)"
                if is_stale
                else f"Fresh ({age_hours:.1f}h ago)"
            ),
            "latest_run": latest_run,
        }

    def get_run_health_summary(self) -> dict[str, Any]:
        """Compute run counts by status and overall collection success rate."""
        runs = self.repo.list_collection_runs(limit=1000)
        if not runs:
            return {
                "total_runs": 0,
                "completed_runs": 0,
                "partial_runs": 0,
                "blocked_runs": 0,
                "failed_runs": 0,
                "interrupted_runs": 0,
                "running_runs": 0,
                "success_rate_pct": None,
                "snapshot_success_rate_pct": None,
            }

        counts: dict[str, int] = {}
        for r in runs:
            counts[r["status"]] = counts.get(r["status"], 0) + 1

        finished = [r for r in runs if r["status"] != "running"]
        completed = counts.get("completed", 0)
        run_success_rate = (
            round((completed / len(finished)) * 100.0, 1) if finished else None
        )

        snap_totals = self.repo.backend.fetch_one(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN collection_status = 'success' THEN 1 ELSE 0 END) AS ok_count
              FROM availability_snapshots
             WHERE collection_status NOT IN ('zone_closed', 'window_not_open')
            """
        )
        snap_rate: float | None = None
        if snap_totals and snap_totals["total"]:
            total_n = int(snap_totals["total"])
            ok_n = int(snap_totals["ok_count"] or 0)
            raw_pct = (ok_n / total_n) * 100.0
            # Never round an imperfect capture rate up to 100.0%
            snap_rate = 99.99 if (ok_n < total_n and round(raw_pct, 2) >= 100.0) else round(raw_pct, 2)

        return {
            "total_runs": len(runs),
            "completed_runs": completed,
            "partial_runs": counts.get("partial", 0),
            "blocked_runs": counts.get("blocked", 0),
            "failed_runs": counts.get("failed", 0),
            "interrupted_runs": counts.get("interrupted", 0),
            "running_runs": counts.get("running", 0),
            "success_rate_pct": run_success_rate,
            "snapshot_success_rate_pct": snap_rate,
        }

    def detect_run_coverage_gaps(self, collection_run_id: int | None = None) -> dict[str, Any]:
        """Identify missing safari dates and missing zones for a target collection run."""
        run = (
            self.repo.get_collection_run(collection_run_id)
            if collection_run_id is not None
            else self.repo.get_latest_successful_run()
        )
        if run is None:
            runs = self.repo.list_collection_runs(limit=1)
            run = runs[0] if runs else None
        if run is None:
            return {
                "run_id": None,
                "expected_dates": [],
                "missing_dates": [],
                "incomplete_dates": [],
                "missing_zones": [],
                "failed_observations": pd.DataFrame(),
            }

        run_id = int(run["id"])
        win_start = date.fromisoformat(run["date_window_start"])
        win_end = date.fromisoformat(run["date_window_end"])
        span = (win_end - win_start).days + 1
        expected_dates = [(win_start + timedelta(days=i)).isoformat() for i in range(max(0, span))]

        active_zones = self.repo.list_zones(active_only=True)
        expected_zone_names = {z["zone_name"] for z in active_zones}

        snaps = self.repo.list_snapshots_for_run(run_id)
        snaps_df = pd.DataFrame(snaps) if snaps else pd.DataFrame()

        if snaps_df.empty:
            return {
                "run_id": run_id,
                "run_status": run["status"],
                "window_start": run["date_window_start"],
                "window_end": run["date_window_end"],
                "expected_dates": expected_dates,
                "missing_dates": expected_dates,
                "incomplete_dates": expected_dates,
                "missing_zones": sorted(expected_zone_names),
                "failed_observations": pd.DataFrame(),
            }

        valid_or_closed = snaps_df[
            snaps_df["collection_status"].isin({"success", "zone_closed", "window_not_open"})
        ]
        observed_valid_dates = set(valid_or_closed["safari_date"].unique())
        all_recorded_dates = set(snaps_df["safari_date"].unique())
        missing_dates = [d for d in expected_dates if d not in all_recorded_dates]

        # Also flag dates where at least one observation failed/was missing
        error_df = snaps_df[
            ~snaps_df["collection_status"].isin({"success", "zone_closed", "window_not_open"})
        ].copy()
        dates_with_errors = set(error_df["safari_date"].unique()) if not error_df.empty else set()
        incomplete_dates = sorted(
            set(missing_dates)
            | dates_with_errors
            | {d for d in expected_dates if d not in observed_valid_dates}
        )

        zones_with_valid = set(valid_or_closed["zone_name"].unique())
        missing_zones = sorted(expected_zone_names - zones_with_valid)

        return {
            "run_id": run_id,
            "run_status": run["status"],
            "window_start": run["date_window_start"],
            "window_end": run["date_window_end"],
            "expected_dates": expected_dates,
            "missing_dates": missing_dates,
            "incomplete_dates": incomplete_dates,
            "missing_zones": missing_zones,
            "failed_observations": error_df.reset_index(drop=True),
        }

    def get_last_successful_observation_by_zone(self) -> pd.DataFrame:
        """Return the most recent valid observation timestamp and coverage count per zone."""
        rows = self.repo.backend.fetch_all(
            """
            SELECT z.zone_name,
                   z.source_zone_identifier,
                   z.entry_gate,
                   z.safari_mode,
                   z.unit_label,
                   MAX(CASE WHEN s.collection_status = 'success' THEN s.captured_at END) AS last_success_at,
                   COUNT(CASE WHEN s.collection_status = 'success' THEN 1 END) AS valid_snapshots,
                   COUNT(CASE WHEN s.collection_status IN ('missing', 'parse_error', 'error', 'blocked') THEN 1 END) AS issue_snapshots
              FROM zones z
              LEFT JOIN availability_snapshots s ON s.zone_id = z.id
             WHERE z.is_active = 1
             GROUP BY z.id, z.zone_name, z.source_zone_identifier, z.entry_gate, z.safari_mode, z.unit_label
             ORDER BY z.zone_name ASC
            """
        )
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    @staticmethod
    def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
        """Export a DataFrame to UTF-8 CSV bytes preserving empty cells for NULLs (never 0)."""
        return df.to_csv(index=False, na_rep="").encode("utf-8")
