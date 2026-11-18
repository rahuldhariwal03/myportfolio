"""Historical trend, lead-time, weekday/weekend, zone/session, and future analytics.

All metrics are strictly descriptive summaries of stored observations — the system
never generates speculative predictions or labels slot decreases as bookings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from src.analytics.change_detector import compute_capacity_occupied_pct
from src.database.repository import SafariMonitorRepository
from src.date_window import calculate_lead_time_days, to_timezone

DEFAULT_LEAD_TIME_MILESTONES: tuple[int, ...] = (30, 20, 15, 10, 5, 1)


class TrendAnalyticsService:
    """Computes latest zone availability tables, historical curves, and lead-time patterns."""

    def __init__(self, repo: SafariMonitorRepository, timezone_name: str = "Asia/Kolkata") -> None:
        self.repo = repo
        self.timezone_name = timezone_name

    def get_all_snapshots_dataframe(self, valid_only: bool = False) -> pd.DataFrame:
        """Load snapshots enriched with zone, date, lead-time, and validated occupancy %."""
        where_clause = (
            "WHERE s.collection_status = 'success' AND s.available_slots IS NOT NULL"
            if valid_only
            else ""
        )
        rows = self.repo.backend.fetch_all(
            f"""
            SELECT s.id,
                   s.collection_run_id,
                   s.safari_date,
                   s.zone_id,
                   z.zone_name,
                   z.source_zone_identifier,
                   z.entry_gate,
                   z.safari_mode,
                   z.unit_label,
                   s.session,
                   s.available_slots,
                   s.total_capacity,
                   s.raw_displayed_value,
                   s.raw_capacity_value,
                   s.collection_status,
                   s.confidence,
                   s.source_section,
                   s.error_details,
                   s.date_operating_status,
                   s.captured_at,
                   sd.weekday,
                   sd.is_weekend,
                   cr.collection_type,
                   cr.is_demo
              FROM availability_snapshots s
              JOIN zones z ON z.id = s.zone_id
              JOIN safari_dates sd ON sd.safari_date = s.safari_date
              JOIN collection_runs cr ON cr.id = s.collection_run_id
              {where_clause}
             ORDER BY s.captured_at ASC, s.safari_date ASC, z.zone_name ASC, s.session ASC
            """
        )
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["captured_dt"] = df["captured_at"].apply(
            lambda ts: to_timezone(datetime.fromisoformat(ts), self.timezone_name)
        )
        df["observed_date"] = df["captured_dt"].apply(lambda dt: dt.date().isoformat())
        df["observed_month"] = df["captured_dt"].apply(lambda dt: dt.strftime("%Y-%m"))
        df["safari_month"] = df["safari_date"].str.slice(0, 7)
        df["day_type"] = df["is_weekend"].apply(lambda flag: "Weekend" if int(flag) == 1 else "Weekday")
        df["lead_time_days"] = [
            calculate_lead_time_days(s_date, cap_dt, self.timezone_name)
            for s_date, cap_dt in zip(df["safari_date"], df["captured_dt"])
        ]
        df["capacity_occupied_pct"] = [
            compute_capacity_occupied_pct(
                None if pd.isna(avail) else int(avail),
                None if pd.isna(cap) else int(cap),
                confidence=str(conf),
            )
            for avail, cap, conf in zip(
                df["available_slots"], df["total_capacity"], df["confidence"]
            )
        ]
        return df

    def get_latest_snapshots_per_series(self) -> pd.DataFrame:
        """Return the latest recorded snapshot (any status) for every `(safari_date, zone, session)`."""
        df = self.get_all_snapshots_dataframe(valid_only=False)
        if df.empty:
            return df
        df = df.sort_values(["captured_at", "id"], ascending=[True, True])
        return (
            df.groupby(["safari_date", "zone_id", "session"], as_index=False)
            .tail(1)
            .sort_values(["safari_date", "zone_name", "session"])
            .reset_index(drop=True)
        )

    def get_latest_valid_snapshots_per_series(self) -> pd.DataFrame:
        """Return the latest VALID (`success` + non-null) snapshot per `(safari_date, zone, session)`."""
        df = self.get_all_snapshots_dataframe(valid_only=True)
        if df.empty:
            return df
        df = df.sort_values(["captured_at", "id"], ascending=[True, True])
        return (
            df.groupby(["safari_date", "zone_id", "session"], as_index=False)
            .tail(1)
            .sort_values(["safari_date", "zone_name", "session"])
            .reset_index(drop=True)
        )

    def build_zone_availability_table(
        self,
        *,
        safari_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        zones: list[str] | None = None,
        session: str | None = None,
    ) -> pd.DataFrame:
        """Build the Page 2 table: `Zone | Date | Morning | Afternoon | Total available` + metadata.

        Important NULL handling:
        - Missing/closed/error sessions stay `NA` (displayed as `N/A (status)` in UI), never `0`.
        - `total_available` sums only observed non-null sessions for the same zone & date
          (where morning and afternoon always share the same unit type). If both are missing,
          `total_available` is `NA`, NOT `0`.
        """
        latest = self.get_latest_snapshots_per_series()
        if latest.empty:
            return pd.DataFrame()

        if safari_date:
            latest = latest[latest["safari_date"] == safari_date]
        if start_date:
            latest = latest[latest["safari_date"] >= start_date]
        if end_date:
            latest = latest[latest["safari_date"] <= end_date]
        if zones:
            latest = latest[latest["zone_name"].isin(zones)]
        if session and session.lower() in {"morning", "afternoon"}:
            latest = latest[latest["session"] == session.lower()]
        if latest.empty:
            return pd.DataFrame()

        records: list[dict[str, Any]] = []
        for (z_name, s_date), grp in latest.groupby(["zone_name", "safari_date"], sort=True):
            first = grp.iloc[0]
            m_rows = grp[grp["session"] == "morning"]
            a_rows = grp[grp["session"] == "afternoon"]

            m_val = _extract_nullable_int(m_rows, "available_slots")
            a_val = _extract_nullable_int(a_rows, "available_slots")
            m_cap = _extract_nullable_int(m_rows, "total_capacity")
            a_cap = _extract_nullable_int(a_rows, "total_capacity")

            m_status = str(m_rows.iloc[0]["collection_status"]) if not m_rows.empty else "not_filtered"
            a_status = str(a_rows.iloc[0]["collection_status"]) if not a_rows.empty else "not_filtered"
            m_raw = m_rows.iloc[0]["raw_displayed_value"] if not m_rows.empty else None
            a_raw = a_rows.iloc[0]["raw_displayed_value"] if not a_rows.empty else None

            non_null_vals = [v for v in (m_val, a_val) if v is not None]
            total_available = sum(non_null_vals) if non_null_vals else None

            total_cap = (
                (m_cap or 0) + (a_cap or 0)
                if (m_val is not None and m_cap is not None) or (a_val is not None and a_cap is not None)
                else None
            )
            both_verified = all(
                str(r["confidence"]) == "verified"
                for _, r in grp.iterrows()
                if r["collection_status"] == "success"
            )
            occupied_pct = (
                compute_capacity_occupied_pct(
                    total_available,
                    total_cap,
                    confidence="verified" if (both_verified and non_null_vals) else "unverified",
                )
                if (m_val is not None and m_cap is not None and (a_val is None or a_cap is not None))
                or (a_val is not None and a_cap is not None and (m_val is None or m_cap is not None))
                else None
            )

            records.append(
                {
                    "Zone": z_name,
                    "Date": s_date,
                    "Weekday": first["weekday"],
                    "Day Type": first["day_type"],
                    "Morning": m_val,
                    "Afternoon": a_val,
                    "Total available": total_available,
                    "Unit": first["unit_label"],
                    "Safari Mode": first["safari_mode"],
                    "Occupied %": occupied_pct,
                    "Morning Status": m_status,
                    "Afternoon Status": a_status,
                    "Morning Raw": m_raw,
                    "Afternoon Raw": a_raw,
                    "Last Captured": str(grp["captured_at"].max()),
                }
            )

        out = pd.DataFrame(records).sort_values(["Date", "Zone"]).reset_index(drop=True)
        for col in ("Morning", "Afternoon", "Total available"):
            out[col] = out[col].astype("Int64")
        return out

    def get_comparable_slot_totals(self, active_window_only: bool = True) -> dict[str, Any]:
        """Return latest valid slot sums separated by comparable unit (`jeep_permit` vs `canter_seat`).

        When `active_window_only=True`, restricts to the latest successful collection run's
        rolling monitoring window (e.g. today's 30 forward dates) so already-elapsed historical
        safari dates are never mixed into current available slot totals.
        """
        latest_valid = self.get_latest_valid_snapshots_per_series()
        if latest_valid.empty:
            return {
                "jeep_permit_slots": None,
                "canter_seat_slots": None,
                "jeep_zones_count": 0,
                "canter_zones_count": 0,
                "monitored_dates_count": 0,
                "historical_dates_count": 0,
                "window_start": None,
                "window_end": None,
            }

        historical_dates_count = int(latest_valid["safari_date"].nunique())
        latest_run = self.repo.get_latest_successful_run()
        win_start: str | None = None
        win_end: str | None = None
        scoped = latest_valid
        if active_window_only and latest_run is not None:
            win_start = str(latest_run["date_window_start"])
            win_end = str(latest_run["date_window_end"])
            scoped = latest_valid[
                (latest_valid["safari_date"] >= win_start)
                & (latest_valid["safari_date"] <= win_end)
            ]

        jeep = scoped[scoped["safari_mode"] == "jeep_permit"]
        canter = scoped[scoped["safari_mode"] == "canter_seat"]
        return {
            "jeep_permit_slots": int(jeep["available_slots"].sum()) if not jeep.empty else None,
            "canter_seat_slots": int(canter["available_slots"].sum()) if not canter.empty else None,
            "jeep_zones_count": int(jeep["zone_name"].nunique()) if not jeep.empty else 0,
            "canter_zones_count": int(canter["zone_name"].nunique()) if not canter.empty else 0,
            "monitored_dates_count": int(scoped["safari_date"].nunique()),
            "historical_dates_count": historical_dates_count,
            "window_start": win_start,
            "window_end": win_end,
        }

    def compute_lead_time_summary(
        self,
        milestones: tuple[int, ...] = DEFAULT_LEAD_TIME_MILESTONES,
        safari_mode: str = "jeep_permit",
        zones: list[str] | None = None,
    ) -> pd.DataFrame:
        """Summarize availability at target lead times (default: 30, 20, 15, 10, 5, 1 days before safari).

        Uses exact lead-time matches first; when a collection cadence lands +/-1 day around a
        milestone, reports exact matches exclusively so lead-time buckets remain faithful.
        """
        df = self.get_all_snapshots_dataframe(valid_only=True)
        if df.empty:
            return pd.DataFrame()
        if safari_mode and safari_mode != "all":
            df = df[df["safari_mode"] == safari_mode]
        if zones:
            df = df[df["zone_name"].isin(zones)]
        subset = df[df["lead_time_days"].isin(milestones)].copy()
        if subset.empty:
            return pd.DataFrame()

        summary = (
            subset.groupby(["lead_time_days", "zone_name", "unit_label"], as_index=False)
            .agg(
                avg_available_slots=("available_slots", "mean"),
                median_available_slots=("available_slots", "median"),
                min_available_slots=("available_slots", "min"),
                max_available_slots=("available_slots", "max"),
                avg_occupied_pct=("capacity_occupied_pct", "mean"),
                observations=("id", "count"),
            )
            .sort_values(["lead_time_days", "zone_name"], ascending=[False, True])
        )
        summary["avg_available_slots"] = summary["avg_available_slots"].round(2)
        summary["avg_occupied_pct"] = summary["avg_occupied_pct"].round(2)
        return summary

    def compute_weekday_vs_weekend(self, safari_mode: str = "jeep_permit") -> pd.DataFrame:
        """Compare average available slots and occupancy between weekdays and weekends per zone/session."""
        df = self.get_latest_valid_snapshots_per_series()
        if df.empty:
            return pd.DataFrame()
        if safari_mode and safari_mode != "all":
            df = df[df["safari_mode"] == safari_mode]
        if df.empty:
            return pd.DataFrame()

        summary = (
            df.groupby(["zone_name", "day_type", "session", "unit_label"], as_index=False)
            .agg(
                avg_available=("available_slots", "mean"),
                avg_occupied_pct=("capacity_occupied_pct", "mean"),
                zero_slot_dates=("available_slots", lambda s: int((s == 0).sum())),
                dates_observed=("safari_date", "nunique"),
            )
            .sort_values(["zone_name", "day_type", "session"])
        )
        summary["avg_available"] = summary["avg_available"].round(2)
        summary["avg_occupied_pct"] = summary["avg_occupied_pct"].round(2)
        return summary

    def compute_session_comparison(self, safari_mode: str = "jeep_permit") -> pd.DataFrame:
        """Compare Morning vs Afternoon availability and occupancy by zone."""
        df = self.get_latest_valid_snapshots_per_series()
        if df.empty:
            return pd.DataFrame()
        if safari_mode and safari_mode != "all":
            df = df[df["safari_mode"] == safari_mode]
        if df.empty:
            return pd.DataFrame()

        summary = (
            df.groupby(["zone_name", "session", "unit_label"], as_index=False)
            .agg(
                avg_available=("available_slots", "mean"),
                total_available=("available_slots", "sum"),
                avg_occupied_pct=("capacity_occupied_pct", "mean"),
                fully_unavailable_count=("available_slots", lambda s: int((s == 0).sum())),
                dates_count=("safari_date", "nunique"),
            )
            .sort_values(["zone_name", "session"])
        )
        summary["avg_available"] = summary["avg_available"].round(2)
        summary["avg_occupied_pct"] = summary["avg_occupied_pct"].round(2)
        return summary

    # ------------------------------------------------------------------
    # Section 8: Future-ready descriptive intelligence (no fake predictions)
    # ------------------------------------------------------------------
    def compute_research_intelligence(self, min_change_events: int = 5) -> dict[str, pd.DataFrame]:
        """Descriptive indicators for fastest-changing zones, zero-slot dates, high-availability
        dates, monthly summaries, and unusual slot movements.
        """
        latest_valid = self.get_latest_valid_snapshots_per_series()
        change_rows = self.repo.list_change_events(limit=10000)
        changes_df = pd.DataFrame(change_rows) if change_rows else pd.DataFrame()

        # 1. Fastest-changing zones (ranked by total observed reduction & mean movement magnitude)
        if not changes_df.empty and len(changes_df) >= min_change_events:
            changes_df["abs_movement"] = changes_df["change_amount"].abs()
            fastest_zones = (
                changes_df.groupby(["zone_name", "safari_mode", "unit_label"], as_index=False)
                .agg(
                    total_observed_reduction=("availability_reduction", "sum"),
                    total_observed_increase=("availability_increase", "sum"),
                    net_change=("change_amount", "sum"),
                    avg_reduction_per_step=("availability_reduction", "mean"),
                    comparisons=("id", "count"),
                )
                .sort_values("total_observed_reduction", ascending=False)
                .reset_index(drop=True)
            )
            fastest_zones["avg_reduction_per_step"] = fastest_zones["avg_reduction_per_step"].round(2)
        else:
            fastest_zones = pd.DataFrame()

        # 2. Dates reaching 0 availability (fully unavailable zone-sessions)
        if not latest_valid.empty:
            zero_dates = (
                latest_valid[latest_valid["available_slots"] == 0][
                    ["safari_date", "weekday", "day_type", "zone_name", "session", "unit_label", "captured_at"]
                ]
                .sort_values(["safari_date", "zone_name", "session"])
                .reset_index(drop=True)
            )
            # 3. Dates with consistently high availability (validated occupancy <= 25%)
            verified = latest_valid.dropna(subset=["capacity_occupied_pct"])
            high_avail_dates = (
                verified.groupby(["safari_date", "weekday", "day_type"], as_index=False)
                .agg(
                    avg_occupied_pct=("capacity_occupied_pct", "mean"),
                    zones_reporting=("zone_name", "nunique"),
                )
                .query("avg_occupied_pct <= 25.0")
                .sort_values(["avg_occupied_pct", "safari_date"])
                .reset_index(drop=True)
            )
            high_avail_dates["avg_occupied_pct"] = high_avail_dates["avg_occupied_pct"].round(2)

            # 4. Month-to-month comparison scaffold (ready as history accumulates)
            monthly = (
                latest_valid.groupby(["safari_month", "safari_mode", "unit_label"], as_index=False)
                .agg(
                    avg_available=("available_slots", "mean"),
                    avg_occupied_pct=("capacity_occupied_pct", "mean"),
                    dates_covered=("safari_date", "nunique"),
                )
                .sort_values(["safari_month", "safari_mode"])
            )
            monthly["avg_available"] = monthly["avg_available"].round(2)
            monthly["avg_occupied_pct"] = monthly["avg_occupied_pct"].round(2)
        else:
            zero_dates = pd.DataFrame()
            high_avail_dates = pd.DataFrame()
            monthly = pd.DataFrame()

        # 5. Unusual availability increases or decreases (descriptive outlier detection per safari_mode)
        unusual_list: list[pd.DataFrame] = []
        if not changes_df.empty and len(changes_df) >= min_change_events:
            for _, mode_grp in changes_df.groupby("safari_mode"):
                nonzero = mode_grp[mode_grp["change_amount"] != 0].copy()
                if len(nonzero) < 5:
                    continue
                abs_vals = nonzero["change_amount"].abs()
                q75 = float(abs_vals.quantile(0.75))
                q25 = float(abs_vals.quantile(0.25))
                iqr = q75 - q25
                threshold = max(q75 + 1.5 * iqr, 5.0)
                flagged = nonzero[
                    (abs_vals >= threshold)
                    | (nonzero["availability_increase"] >= 3)
                    | (nonzero["change_type"].str.startswith("capacity_changed"))
                ].copy()
                if not flagged.empty:
                    unusual_list.append(flagged)

        unusual_df = (
            pd.concat(unusual_list, ignore_index=True)
            .sort_values("observed_at", ascending=False)
            .head(50)
            if unusual_list
            else pd.DataFrame()
        )

        return {
            "fastest_zones": fastest_zones,
            "fully_unavailable": zero_dates,
            "high_availability_dates": high_avail_dates,
            "monthly_summary": monthly,
            "unusual_movements": unusual_df,
        }


def _extract_nullable_int(rows: pd.DataFrame, col: str) -> int | None:
    if rows.empty:
        return None
    val = rows.iloc[0][col]
    if pd.isna(val):
        return None
    return int(val)
