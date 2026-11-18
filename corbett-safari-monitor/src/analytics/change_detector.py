"""Availability change detection engine (Phase 5).

Important analytical rules:
1. Only VALID snapshots (`collection_status == 'success'` and `available_slots IS NOT NULL`)
   are ever compared. Missing, paused, blocked, closed, or malformed observations are
   NEVER coerced to zero.
2. Availability reductions are NEVER labeled as "confirmed bookings" — cancellations,
   departmental holds, weather restrictions, and capacity adjustments can all shift counts.
3. Percentage of capacity occupied is calculated ONLY when both `available_slots` and
   `total_capacity` are validated (`confidence == 'verified'`, `0 <= available <= capacity`,
   `capacity > 0`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from src.database.repository import SafariMonitorRepository
from src.date_window import to_timezone


@dataclass(frozen=True)
class ChangeComputation:
    """Pure calculation output between two valid observations."""

    previous_available: int
    current_available: int
    net_change: int
    availability_reduction: int
    availability_increase: int
    previous_capacity: int | None
    current_capacity: int | None
    capacity_occupied_pct: float | None
    change_type: str


def compute_capacity_occupied_pct(
    available_slots: int | None,
    total_capacity: int | None,
    confidence: str = "verified",
) -> float | None:
    """Compute validated occupancy percentage, or `None` if inputs are unvalidated/missing."""
    if confidence != "verified":
        return None
    if available_slots is None or total_capacity is None:
        return None
    if total_capacity <= 0:
        return None
    if available_slots < 0 or available_slots > total_capacity:
        return None
    occupied = total_capacity - available_slots
    return round((occupied / total_capacity) * 100.0, 2)


def calculate_slot_change(
    previous_available: int | None,
    current_available: int | None,
    *,
    previous_capacity: int | None = None,
    current_capacity: int | None = None,
    current_confidence: str = "verified",
) -> ChangeComputation | None:
    """Calculate reduction, increase, net change, change_type, and validated occupancy %.

    Returns `None` if either observation is `None` (never treats missing as zero).
    """
    if previous_available is None or current_available is None:
        return None
    if previous_available < 0 or current_available < 0:
        raise ValueError("Slot counts cannot be negative")

    net_change = current_available - previous_available
    reduction = max(0, previous_available - current_available)
    increase = max(0, current_available - previous_available)

    capacity_changed = (
        previous_capacity is not None
        and current_capacity is not None
        and previous_capacity != current_capacity
    )
    if capacity_changed:
        if net_change < 0:
            change_type = "capacity_changed_reduction"
        elif net_change > 0:
            change_type = "capacity_changed_increase"
        else:
            change_type = "capacity_changed_no_slot_delta"
    else:
        if net_change < 0:
            change_type = "reduction"
        elif net_change > 0:
            change_type = "increase"
        else:
            change_type = "no_change"

    occupied_pct = compute_capacity_occupied_pct(
        current_available, current_capacity, confidence=current_confidence
    )

    return ChangeComputation(
        previous_available=previous_available,
        current_available=current_available,
        net_change=net_change,
        availability_reduction=reduction,
        availability_increase=increase,
        previous_capacity=previous_capacity,
        current_capacity=current_capacity,
        capacity_occupied_pct=occupied_pct,
        change_type=change_type,
    )


class ChangeDetectionService:
    """Records and summarizes consecutive-run, morning/evening, daily, and 24-hour changes."""

    def __init__(self, repo: SafariMonitorRepository, timezone_name: str = "Asia/Kolkata") -> None:
        self.repo = repo
        self.timezone_name = timezone_name

    def detect_and_record_for_snapshot(self, snapshot_id: int) -> int | None:
        """Compare one snapshot against its previous valid observation and persist a change_event.

        Idempotent: if a `change_event` already exists for `snapshot_id`, returns its ID.
        Returns `None` when the snapshot is invalid/missing or is the first valid observation.
        """
        existing = self.repo.backend.fetch_one(
            "SELECT id FROM change_events WHERE current_snapshot_id = ?",
            (snapshot_id,),
        )
        if existing is not None:
            return int(existing["id"])

        current = self.repo.get_snapshot(snapshot_id)
        if current is None:
            return None
        if current["collection_status"] != "success" or current["available_slots"] is None:
            return None

        previous = self.repo.get_previous_valid_snapshot(
            safari_date=current["safari_date"],
            zone_id=int(current["zone_id"]),
            session=current["session"],
            before_captured_at=current["captured_at"],
            current_snapshot_id=int(current["id"]),
        )
        if previous is None:
            return None

        calc = calculate_slot_change(
            int(previous["available_slots"]),
            int(current["available_slots"]),
            previous_capacity=previous["total_capacity"],
            current_capacity=current["total_capacity"],
            current_confidence=current["confidence"],
        )
        if calc is None:
            return None

        return self.repo.record_change_event(
            collection_run_id=int(current["collection_run_id"]),
            previous_snapshot_id=int(previous["id"]),
            current_snapshot_id=int(current["id"]),
            safari_date=current["safari_date"],
            zone_id=int(current["zone_id"]),
            session=current["session"],
            previous_available=calc.previous_available,
            current_available=calc.current_available,
            change_amount=calc.net_change,
            availability_reduction=calc.availability_reduction,
            availability_increase=calc.availability_increase,
            previous_capacity=calc.previous_capacity,
            current_capacity=calc.current_capacity,
            capacity_occupied_pct=calc.capacity_occupied_pct,
            change_type=calc.change_type,
            previous_captured_at=previous["captured_at"],
            observed_at=current["captured_at"],
        )

    def detect_and_record_for_run(self, collection_run_id: int) -> list[int]:
        """Compute and persist change events for all valid snapshots in a collection run."""
        snapshots = self.repo.list_snapshots_for_run(collection_run_id)
        created_ids: list[int] = []
        for snap in snapshots:
            event_id = self.detect_and_record_for_snapshot(int(snap["id"]))
            if event_id is not None:
                created_ids.append(event_id)
        return created_ids

    def get_change_events_dataframe(self, safari_mode: str | None = None) -> pd.DataFrame:
        """Load change events joined with zone metadata and local observation dates."""
        rows = self.repo.backend.fetch_all(
            """
            SELECT ce.*,
                   z.zone_name,
                   z.safari_mode,
                   z.unit_label,
                   cr.collection_type,
                   cr.is_demo,
                   sd.weekday,
                   sd.is_weekend
              FROM change_events ce
              JOIN zones z ON z.id = ce.zone_id
              JOIN collection_runs cr ON cr.id = ce.collection_run_id
              JOIN safari_dates sd ON sd.safari_date = ce.safari_date
             ORDER BY ce.observed_at ASC, ce.id ASC
            """
        )
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if safari_mode and safari_mode != "all":
            df = df[df["safari_mode"] == safari_mode].copy()
        if df.empty:
            return df

        df["observed_dt"] = df["observed_at"].apply(
            lambda ts: to_timezone(datetime.fromisoformat(ts), self.timezone_name)
        )
        df["observed_date"] = df["observed_dt"].apply(lambda dt: dt.date().isoformat())
        df["run_period"] = df["collection_type"].apply(_normalize_run_period)
        return df

    def summarize_daily_changes(
        self,
        observed_date: str | None = None,
        safari_mode: str | None = None,
    ) -> dict[str, Any]:
        """Calculate daily reduction, daily increase, daily net change, and morning/evening split.

        If `observed_date` is omitted, summarizes the most recent local date that has change events.
        """
        df = self.get_change_events_dataframe(safari_mode=safari_mode)
        if df.empty:
            return {
                "observed_date": observed_date,
                "daily_reduction": 0,
                "daily_increase": 0,
                "daily_net_change": 0,
                "morning_reduction": 0,
                "morning_increase": 0,
                "morning_net_change": 0,
                "evening_reduction": 0,
                "evening_increase": 0,
                "evening_net_change": 0,
                "manual_net_change": 0,
                "comparisons_count": 0,
                "changed_series_count": 0,
            }

        target_date = observed_date or str(df["observed_date"].max())
        day_df = df[df["observed_date"] == target_date]
        morning_df = day_df[day_df["run_period"] == "morning"]
        evening_df = day_df[day_df["run_period"] == "evening"]
        manual_df = day_df[day_df["run_period"] == "manual"]

        return {
            "observed_date": target_date,
            "daily_reduction": int(day_df["availability_reduction"].sum()) if not day_df.empty else 0,
            "daily_increase": int(day_df["availability_increase"].sum()) if not day_df.empty else 0,
            "daily_net_change": int(day_df["change_amount"].sum()) if not day_df.empty else 0,
            "morning_reduction": int(morning_df["availability_reduction"].sum()) if not morning_df.empty else 0,
            "morning_increase": int(morning_df["availability_increase"].sum()) if not morning_df.empty else 0,
            "morning_net_change": int(morning_df["change_amount"].sum()) if not morning_df.empty else 0,
            "evening_reduction": int(evening_df["availability_reduction"].sum()) if not evening_df.empty else 0,
            "evening_increase": int(evening_df["availability_increase"].sum()) if not evening_df.empty else 0,
            "evening_net_change": int(evening_df["change_amount"].sum()) if not evening_df.empty else 0,
            "manual_net_change": int(manual_df["change_amount"].sum()) if not manual_df.empty else 0,
            "comparisons_count": int(len(day_df)),
            "changed_series_count": int((day_df["change_amount"] != 0).sum()) if not day_df.empty else 0,
        }

    def summarize_zone_daily_changes(
        self,
        observed_date: str | None = None,
        safari_mode: str | None = None,
    ) -> pd.DataFrame:
        """Return zone-wise reduction, increase, net change, and morning/evening split for a date."""
        df = self.get_change_events_dataframe(safari_mode=safari_mode)
        if df.empty:
            return pd.DataFrame()

        target_date = observed_date or str(df["observed_date"].max())
        day_df = df[df["observed_date"] == target_date]
        if day_df.empty:
            return pd.DataFrame()

        grouped = (
            day_df.groupby(["zone_name", "safari_mode", "unit_label"], as_index=False)
            .agg(
                slots_reduced=("availability_reduction", "sum"),
                slots_increased=("availability_increase", "sum"),
                net_change=("change_amount", "sum"),
                observations_compared=("id", "count"),
            )
            .sort_values(["slots_reduced", "zone_name"], ascending=[False, True])
        )

        # Attach morning-run vs evening-run reductions for direct comparison
        period_pivot = day_df.pivot_table(
            index="zone_name",
            columns="run_period",
            values="availability_reduction",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        for col in ("morning", "evening"):
            if col not in period_pivot.columns:
                period_pivot[col] = 0
        period_pivot = period_pivot.rename(
            columns={
                "morning": "morning_run_reduction",
                "evening": "evening_run_reduction",
            }
        )
        keep_cols = ["zone_name", "morning_run_reduction", "evening_run_reduction"]
        return grouped.merge(period_pivot[keep_cols], on="zone_name", how="left")

    def calculate_24h_changes(
        self,
        *,
        min_hours: float = 18.0,
        max_hours: float = 30.0,
        safari_mode: str | None = None,
    ) -> pd.DataFrame:
        """Compute rolling ~24-hour change for each `(safari_date, zone_id, session)`.

        Compares the latest valid snapshot of each series against the valid snapshot
        closest to `latest_captured_at - 24h` within `[min_hours, max_hours]`.
        Series lacking a valid baseline inside that window are omitted (never compared to 0).
        """
        rows = self.repo.backend.fetch_all(
            """
            SELECT s.id, s.safari_date, s.zone_id, s.session,
                   s.available_slots, s.total_capacity, s.confidence, s.captured_at,
                   z.zone_name, z.safari_mode, z.unit_label
              FROM availability_snapshots s
              JOIN zones z ON z.id = s.zone_id
             WHERE s.collection_status = 'success'
               AND s.available_slots IS NOT NULL
             ORDER BY s.safari_date ASC, s.zone_id ASC, s.session ASC, s.captured_at ASC, s.id ASC
            """
        )
        if not rows:
            return pd.DataFrame()

        by_series: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
        for row in rows:
            if safari_mode and safari_mode != "all" and row["safari_mode"] != safari_mode:
                continue
            key = (str(row["safari_date"]), int(row["zone_id"]), str(row["session"]))
            by_series.setdefault(key, []).append(row)

        results: list[dict[str, Any]] = []
        target_delta = timedelta(hours=24)
        min_delta = timedelta(hours=min_hours)
        max_delta = timedelta(hours=max_hours)

        for (s_date, z_id, session), items in by_series.items():
            if len(items) < 2:
                continue
            latest = items[-1]
            latest_dt = datetime.fromisoformat(latest["captured_at"])

            best_candidate: dict[str, Any] | None = None
            best_distance: timedelta | None = None
            for earlier in items[:-1]:
                earlier_dt = datetime.fromisoformat(earlier["captured_at"])
                elapsed = latest_dt - earlier_dt
                if min_delta <= elapsed <= max_delta:
                    distance = abs(elapsed - target_delta)
                    if best_distance is None or distance < best_distance:
                        best_distance = distance
                        best_candidate = earlier

            if best_candidate is None:
                continue

            calc = calculate_slot_change(
                int(best_candidate["available_slots"]),
                int(latest["available_slots"]),
                previous_capacity=best_candidate["total_capacity"],
                current_capacity=latest["total_capacity"],
                current_confidence=latest["confidence"],
            )
            if calc is None:
                continue

            elapsed_hours = round(
                (latest_dt - datetime.fromisoformat(best_candidate["captured_at"])).total_seconds()
                / 3600.0,
                2,
            )
            results.append(
                {
                    "safari_date": s_date,
                    "zone_id": z_id,
                    "zone_name": latest["zone_name"],
                    "safari_mode": latest["safari_mode"],
                    "unit_label": latest["unit_label"],
                    "session": session,
                    "baseline_available_24h": calc.previous_available,
                    "current_available": calc.current_available,
                    "change_24h": calc.net_change,
                    "reduction_24h": calc.availability_reduction,
                    "increase_24h": calc.availability_increase,
                    "capacity_occupied_pct": calc.capacity_occupied_pct,
                    "elapsed_hours": elapsed_hours,
                    "baseline_captured_at": best_candidate["captured_at"],
                    "latest_captured_at": latest["captured_at"],
                }
            )

        return pd.DataFrame(results)


def _normalize_run_period(collection_type: str) -> str:
    lowered = collection_type.lower()
    if "morning" in lowered:
        return "morning"
    if "evening" in lowered:
        return "evening"
    return "manual"
