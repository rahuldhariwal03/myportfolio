"""All 5 pages of the Corbett Safari Availability Monitoring & Intelligence dashboard."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.analytics import (
    DEFAULT_LEAD_TIME_MILESTONES,
    ChangeDetectionService,
    CollectionMonitoringService,
    TrendAnalyticsService,
)
from src.collector import (
    ManualObservationRow,
    check_system_readiness,
    generate_observation_csv_template,
    ingest_manual_observations,
    load_selector_config,
    parse_observation_csv,
)
from src.config import AppConfig
from src.dashboard.theme import CHART_LAYOUT, PALETTE, render_top_header
from src.database import SafariMonitorRepository, create_backend, initialize_schema
from src.date_window import calculate_rolling_window, format_iso_timestamp, now_in_timezone
from src.scheduler import preview_upcoming_runs, validate_schedule_times


def _style_fig(fig: go.Figure, height: int = 370) -> go.Figure:
    fig.update_layout(**CHART_LAYOUT, height=height)
    fig.update_xaxes(showgrid=False, linecolor="#CBD5E1")
    fig.update_yaxes(gridcolor="#EEF2F0", zerolinecolor="#CBD5E1")
    return fig


def _format_slot_display(value: Any, status: str) -> str:
    """Format nullable slot counts honestly so NULL/missing is NEVER displayed as 0."""
    if pd.isna(value):
        label_map = {
            "missing": "NULL (missing)",
            "zone_closed": "NULL (closed)",
            "window_not_open": "NULL (not open)",
            "portal_paused": "NULL (paused)",
            "parse_error": "NULL (unverified)",
            "blocked": "NULL (blocked)",
            "error": "NULL (error)",
            "not_filtered": "—",
        }
        return label_map.get(status, "NULL")
    return str(int(value))


# ==============================================================================
# PAGE 1: OVERVIEW
# ==============================================================================
def render_overview_page(
    *,
    config: AppConfig,
    repo: SafariMonitorRepository,
    trends: TrendAnalyticsService,
    changes: ChangeDetectionService,
    monitor: CollectionMonitoringService,
    is_demo_mode: bool,
) -> None:
    freshness = monitor.get_freshness_status()
    render_top_header(
        page_title="Overview · Safari Availability Intelligence",
        page_subtitle=(
            "High-level snapshot of monitored safari dates, comparable slot availability, "
            "daily slot movement, and collection health."
        ),
        is_demo_mode=is_demo_mode,
        freshness=freshness,
    )

    health = monitor.get_run_health_summary()
    slot_totals = trends.get_comparable_slot_totals()
    zones = repo.list_zones(active_only=True)
    today_iso = now_in_timezone(config.timezone_name).date().isoformat()
    rolling_window = calculate_rolling_window(
        window_days=config.monitoring_window_days,
        timezone_name=config.timezone_name,
    )

    # Summarize today's observed changes (falling back cleanly to latest observed date with label)
    jeep_today = changes.summarize_daily_changes(
        observed_date=today_iso, safari_mode="jeep_permit"
    )
    canter_today = changes.summarize_daily_changes(
        observed_date=today_iso, safari_mode="canter_seat"
    )
    day_label = f"Today ({today_iso})"
    if jeep_today["comparisons_count"] == 0 and canter_today["comparisons_count"] == 0:
        jeep_latest = changes.summarize_daily_changes(safari_mode="jeep_permit")
        if jeep_latest["observed_date"]:
            target = jeep_latest["observed_date"]
            jeep_today = jeep_latest
            canter_today = changes.summarize_daily_changes(
                observed_date=target, safari_mode="canter_seat"
            )
            day_label = f"Latest Date ({target})"

    # Row 1 KPIs: Collection timestamp, Monitored dates, Zones, Success rate
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Latest Successful Collection",
        freshness["last_success_at"].split(" ")[1] + " IST"
        if freshness["has_successful_run"]
        else "None yet",
        freshness["last_success_at"].split(" ")[0]
        if freshness["has_successful_run"]
        else "Awaiting local run",
        delta_color="off",
    )
    c2.metric(
        "Monitored Safari Dates",
        str(slot_totals["monitored_dates_count"]),
        f"Window: {rolling_window.start_date} → {rolling_window.end_date}",
        delta_color="off",
    )
    c3.metric(
        "Official Safari Zones",
        str(len(zones)),
        "7 Jeep permit · 1 Canter seat",
        delta_color="off",
    )
    success_display = (
        f"{health['success_rate_pct']:.1f}%"
        if health["success_rate_pct"] is not None
        else "N/A"
    )
    snap_sub = (
        f"Cell capture: {health['snapshot_success_rate_pct']:.2f}%"
        if health["snapshot_success_rate_pct"] is not None
        else f"{health['total_runs']} run(s) logged"
    )
    c4.metric("Collection Success Rate", success_display, snap_sub, delta_color="off")

    # Row 2 KPIs: Comparable available slots + Today's reduction & increase
    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Observed Jeep Permits Available",
        f"{slot_totals['jeep_permit_slots']:,}"
        if slot_totals["jeep_permit_slots"] is not None
        else "N/A",
        f"Comparable across {slot_totals['jeep_zones_count']} Jeep zones",
        delta_color="off",
    )
    k2.metric(
        "Observed Canter Seats (Dhikala)",
        f"{slot_totals['canter_seat_slots']:,}"
        if slot_totals["canter_seat_slots"] is not None
        else "N/A",
        "Kept separate (seats ≠ Jeep permits)",
        delta_color="off",
    )
    k3.metric(
        f"Availability Reduction · {day_label}",
        f"{jeep_today['daily_reduction']:,} permits",
        f"Dhikala Canter: -{canter_today['daily_reduction']:,} seats",
        delta_color="off",
    )
    k4.metric(
        f"Availability Increase · {day_label}",
        f"+{jeep_today['daily_increase']:,} permits",
        f"Dhikala Canter: +{canter_today['daily_increase']:,} seats",
        delta_color="off",
    )

    st.markdown(
        """
        <div class="csm-note">
            <strong>Methodological Note:</strong> Jeep zones (Bijrani, Jhirna, Dhela, Garjia,
            Durgadevi, Sonanadi, Pakhro) allocate per-vehicle permits (up to 6 visitors/Gypsy),
            while Dhikala day safaris allocate shared 16-seater Canter seats. Totals are reported
            separately so unlike units are never summed. Slot reductions reflect observed changes
            in displayed availability — <em>never</em> confirmed bookings.
        </div>
        """,
        unsafe_allow_html=True,
    )

    latest_valid = trends.get_latest_valid_snapshots_per_series()
    if slot_totals.get("window_start") and slot_totals.get("window_end") and not latest_valid.empty:
        latest_valid = latest_valid[
            (latest_valid["safari_date"] >= slot_totals["window_start"])
            & (latest_valid["safari_date"] <= slot_totals["window_end"])
        ]
    if not latest_valid.empty:
        col_left, col_right = st.columns([3, 2])
        with col_left:
            st.subheader("Current Window Availability by Zone & Session")
            zone_sess = (
                latest_valid.groupby(["zone_name", "safari_mode", "unit_label", "session"], as_index=False)
                .agg(
                    total_available=("available_slots", "sum"),
                    avg_occupied_pct=("capacity_occupied_pct", "mean"),
                )
            )
            jeep_zs = zone_sess[zone_sess["safari_mode"] == "jeep_permit"]
            if not jeep_zs.empty:
                fig = px.bar(
                    jeep_zs,
                    x="zone_name",
                    y="total_available",
                    color="session",
                    barmode="group",
                    color_discrete_map={
                        "morning": PALETTE["morning"],
                        "afternoon": PALETTE["afternoon"],
                    },
                    labels={
                        "zone_name": "Safari Zone",
                        "total_available": "Total Available Jeep Permits (Window)",
                        "session": "Session",
                    },
                    title="Day Jeep Permit Zones — Morning vs Afternoon Slots",
                )
                st.plotly_chart(_style_fig(fig, 360), width="stretch")

        with col_right:
            st.subheader("Validated Capacity Occupancy (%)")
            occ_df = (
                latest_valid.dropna(subset=["capacity_occupied_pct"])
                .groupby(["zone_name", "unit_label"], as_index=False)
                .agg(avg_occupied_pct=("capacity_occupied_pct", "mean"))
                .sort_values("avg_occupied_pct", ascending=True)
            )
            if not occ_df.empty:
                occ_df["avg_occupied_pct"] = occ_df["avg_occupied_pct"].round(1)
                fig_occ = px.bar(
                    occ_df,
                    x="avg_occupied_pct",
                    y="zone_name",
                    orientation="h",
                    text="avg_occupied_pct",
                    color="avg_occupied_pct",
                    color_continuous_scale=["#5C8D73", "#D97706", "#B83253"],
                    labels={
                        "avg_occupied_pct": "Avg Occupied Capacity (%)",
                        "zone_name": "Zone",
                    },
                    title="Mean Window Occupancy Across All 8 Zones",
                )
                fig_occ.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                fig_occ.update_layout(coloraxis_showscale=False)
                fig_occ.update_xaxes(range=[0, 112])
                st.plotly_chart(_style_fig(fig_occ, 360), width="stretch")
            else:
                st.info(
                    "Capacity occupancy % is shown only when both total capacity and available "
                    "slots are validated against the portal."
                )
    else:
        st.subheader("Registered Official Corbett Tiger Reserve Zones")
        zones_df = pd.DataFrame(zones)[
            [
                "zone_name",
                "source_zone_identifier",
                "entry_gate",
                "safari_mode",
                "unit_label",
                "operating_season",
            ]
        ].rename(
            columns={
                "zone_name": "Zone",
                "source_zone_identifier": "Verified Portal ID",
                "entry_gate": "Entry Gate",
                "safari_mode": "Mode",
                "unit_label": "Comparable Unit",
                "operating_season": "Published Season (corbettgov.org)",
            }
        )
        st.dataframe(zones_df, width="stretch", hide_index=True)

    with st.expander("Phase 1 Official Portal Inspection & Compliance Summary", expanded=not latest_valid.size):
        st.markdown(
            """
            - **Portal Routing:** `https://booking.corbettgov.org/` redirects to `https://safari.corbettgov.org/`
              (*Booking Portal of corbettgov.org*, Zipr / eCorbett v3.0). `/canter` redirects to
              `https://safari.corbettgov.org/?eventName=DhikalaZone&date=...`.
            - **Observed Visible Gates:** (1) Supreme Court mobile-phone restriction notice,
              (2) Non-refundable & monsoon **T + 7 days** policy modal, (3) **Mandatory Browser Location
              Verification** before calendar/slots load, (4) Department pause/maintenance banner,
              and (5) client clock-sync verification.
            - **Operating Hours & IP Rules:** Portal operates **05:30 AM – 11:30 PM IST** (`corbettgov.org/faq`)
              and restricts cloud/S2S IP ranges (`corbettgov.org/terms` Clause 10 & `/ipranges`).
            - **Zero-Bypass Policy:** This monitor never spoofs location, never touches booking/payment flows,
              and never invents unverified selectors. Full report: `docs/phase1_website_inspection.md`.
            """
        )


# ==============================================================================
# PAGE 2: ZONE-WISE AVAILABILITY
# ==============================================================================
def render_zone_availability_page(
    *,
    repo: SafariMonitorRepository,
    trends: TrendAnalyticsService,
    monitor: CollectionMonitoringService,
    is_demo_mode: bool,
) -> None:
    freshness = monitor.get_freshness_status()
    render_top_header(
        page_title="Zone-Wise Safari Availability",
        page_subtitle=(
            "Latest stored Morning and Afternoon observations per safari zone and date. "
            "Missing or unverified observations are preserved as NULL (never zero)."
        ),
        is_demo_mode=is_demo_mode,
        freshness=freshness,
    )

    all_zones = [z["zone_name"] for z in repo.list_zones(active_only=True)]
    all_dates = [d["safari_date"] for d in repo.list_safari_dates()]
    if not all_dates:
        st.info(
            "No safari availability snapshots are stored in this database yet. "
            "Switch to **Demo / Sample Test Database** in the sidebar to preview table filtering, "
            "or run a compliant local collection."
        )
        return

    min_d = date.fromisoformat(min(all_dates))
    max_d = date.fromisoformat(max(all_dates))
    latest_run = repo.get_latest_successful_run()
    default_start = (
        max(min_d, date.fromisoformat(latest_run["date_window_start"]))
        if latest_run is not None
        else min_d
    )
    default_end = (
        min(max_d, date.fromisoformat(latest_run["date_window_end"]))
        if latest_run is not None
        else max_d
    )

    # Filter bar: Safari date, Date range, Zone, Session
    f1, f2, f3, f4 = st.columns([1.2, 1.5, 1.8, 1.0])
    with f1:
        exact_date_choice = st.selectbox(
            "Safari Date (Single)",
            options=["All dates in range", *all_dates],
            index=0,
        )
    with f2:
        selected_range = st.date_input(
            "Date Range",
            value=(default_start, default_end),
            min_value=min_d,
            max_value=max_d,
            disabled=(exact_date_choice != "All dates in range"),
        )
    with f3:
        selected_zones = st.multiselect(
            "Zone Filter",
            options=all_zones,
            default=all_zones,
        )
    with f4:
        session_choice = st.selectbox(
            "Session",
            options=["All", "Morning", "Afternoon"],
            index=0,
        )

    show_audit_cols = st.checkbox(
        "Show unit labels, validated occupancy %, raw portal strings, and capture timestamps",
        value=False,
    )

    start_iso: str | None = None
    end_iso: str | None = None
    exact_iso: str | None = None
    if exact_date_choice != "All dates in range":
        exact_iso = exact_date_choice
    elif isinstance(selected_range, (tuple, list)) and len(selected_range) == 2:
        start_iso = selected_range[0].isoformat()
        end_iso = selected_range[1].isoformat()
    elif isinstance(selected_range, date):
        start_iso = selected_range.isoformat()
        end_iso = selected_range.isoformat()

    table_df = trends.build_zone_availability_table(
        safari_date=exact_iso,
        start_date=start_iso,
        end_date=end_iso,
        zones=selected_zones or [],
        session=None if session_choice == "All" else session_choice.lower(),
    )

    if table_df.empty:
        st.warning("No observations match the selected filters.")
        return

    # Summary strip for filtered view
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Rows Displayed", f"{len(table_df):,}")
    s2.metric("Dates Covered", str(table_df["Date"].nunique()))
    s3.metric("Zones Covered", str(table_df["Zone"].nunique()))
    null_cells = int(
        (table_df["Morning Status"] == "missing").sum()
        + (table_df["Afternoon Status"] == "missing").sum()
    )
    s4.metric("Missing (NULL) Sessions", str(null_cells))

    # Build clean display copy where NULL is explicitly marked instead of ambiguous
    display_df = table_df.copy()
    display_df["Morning"] = [
        _format_slot_display(v, st_val)
        for v, st_val in zip(display_df["Morning"], display_df["Morning Status"])
    ]
    display_df["Afternoon"] = [
        _format_slot_display(v, st_val)
        for v, st_val in zip(display_df["Afternoon"], display_df["Afternoon Status"])
    ]
    display_df["Total available"] = [
        "NULL" if pd.isna(v) else f"{int(v)} ({u})"
        for v, u in zip(display_df["Total available"], display_df["Unit"])
    ]

    core_cols = ["Zone", "Date", "Morning", "Afternoon", "Total available"]
    audit_cols = [
        "Weekday",
        "Day Type",
        "Unit",
        "Occupied %",
        "Morning Raw",
        "Afternoon Raw",
        "Last Captured",
    ]
    cols_to_show = core_cols + audit_cols if show_audit_cols else core_cols

    st.dataframe(display_df[cols_to_show], width="stretch", hide_index=True, height=480)

    # Interactive heatmap for quick visual scan of Jeep permit zones
    jeep_subset = table_df[table_df["Safari Mode"] == "jeep_permit"].copy()
    if not jeep_subset.empty and jeep_subset["Date"].nunique() > 1:
        st.subheader("Availability Heatmap (Jeep Permit Zones)")
        jeep_subset["TotalNumeric"] = jeep_subset["Total available"].astype("float")
        pivot = jeep_subset.pivot(index="Zone", columns="Date", values="TotalNumeric")
        fig_hm = px.imshow(
            pivot,
            color_continuous_scale=["#B83253", "#F59E0B", "#E2E8F0", "#1B5E3A"],
            aspect="auto",
            labels={"x": "Safari Date", "y": "Zone", "color": "Available Permits"},
            title="Combined Morning + Afternoon Jeep Permits by Date (blank = NULL / missing)",
        )
        st.plotly_chart(_style_fig(fig_hm, 320), width="stretch")

    st.download_button(
        label="Download Filtered Zone Availability (CSV)",
        data=monitor.dataframe_to_csv_bytes(table_df),
        file_name=f"corbett_zone_availability_{'demo' if is_demo_mode else 'live'}.csv",
        mime="text/csv",
    )


# ==============================================================================
# PAGE 3: DAILY CHANGES
# ==============================================================================
def render_daily_changes_page(
    *,
    changes: ChangeDetectionService,
    monitor: CollectionMonitoringService,
    is_demo_mode: bool,
) -> None:
    freshness = monitor.get_freshness_status()
    render_top_header(
        page_title="Daily Availability Changes",
        page_subtitle=(
            "Consecutive-run, morning-vs-evening, and 24-hour movements in publicly displayed "
            "safari availability."
        ),
        is_demo_mode=is_demo_mode,
        freshness=freshness,
    )

    all_changes = changes.get_change_events_dataframe()
    if all_changes.empty:
        st.info(
            "At least two valid collection runs for overlapping safari dates are required to "
            "compute availability changes. Switch to **Demo / Sample Test Database** to inspect "
            "verified change calculations and charts."
        )
        return

    observed_dates = sorted(all_changes["observed_date"].unique(), reverse=True)
    # Default to the most recent date that has BOTH morning and evening runs if present, else latest
    c_filter1, c_filter2 = st.columns([1.4, 1.8])
    with c_filter1:
        selected_obs_date = st.selectbox(
            "Observation Date (Asia/Kolkata)",
            options=observed_dates,
            index=0,
        )
    with c_filter2:
        scope_label = st.radio(
            "Comparable Unit Scope",
            options=["Jeep Permits (7 Day-Safari Zones)", "Dhikala Canter Seats (16-Seater)"],
            horizontal=True,
        )
    safari_mode = "jeep_permit" if scope_label.startswith("Jeep") else "canter_seat"
    unit_suffix = "permits" if safari_mode == "jeep_permit" else "seats"

    summary = changes.summarize_daily_changes(
        observed_date=selected_obs_date, safari_mode=safari_mode
    )
    df_24h = changes.calculate_24h_changes(safari_mode=safari_mode)
    net_24h = int(df_24h["change_24h"].sum()) if not df_24h.empty else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Slots Reduced on Selected Date",
        f"{summary['daily_reduction']:,} {unit_suffix}",
        f"{summary['changed_series_count']} date/zone/session slots changed",
        delta_color="off",
    )
    m2.metric(
        "Slots Increased on Selected Date",
        f"+{summary['daily_increase']:,} {unit_suffix}",
        "Includes releases / cancellations / adjustments",
        delta_color="off",
    )
    net_val = summary["daily_net_change"]
    m3.metric(
        "Daily Net Change",
        f"{net_val:+,} {unit_suffix}",
        f"{summary['comparisons_count']:,} valid comparisons",
        delta_color="off",
    )
    m4.metric(
        "Rolling 24-Hour Net Change",
        f"{net_24h:+,} {unit_suffix}" if net_24h is not None else "Awaiting 24h pair",
        f"Across {len(df_24h):,} matched 24h series" if not df_24h.empty else "18–30h window",
        delta_color="off",
    )

    st.markdown(
        """
        <div class="csm-note">
            <strong>Important Interpretation Rule:</strong> Availability reductions are
            <strong>not</strong> confirmed bookings. Permit cancellations, departmental quota holds,
            weather closures, and vehicle capacity updates can all decrease or increase displayed counts.
            Missing (<code>NULL</code>) snapshots are skipped — never compared as zero.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Morning vs Evening Run Comparison + Zone-Wise Daily Changes
    col_a, col_b = st.columns([1.15, 1.85])
    with col_a:
        st.subheader("Morning vs Evening Run Comparison")
        me_df = pd.DataFrame(
            [
                {
                    "Collection Run": "Morning Run",
                    "Slots Reduced": summary["morning_reduction"],
                    "Slots Increased": summary["morning_increase"],
                    "Net Change": summary["morning_net_change"],
                },
                {
                    "Collection Run": "Evening Run",
                    "Slots Reduced": summary["evening_reduction"],
                    "Slots Increased": summary["evening_increase"],
                    "Net Change": summary["evening_net_change"],
                },
            ]
        )
        me_long = me_df.melt(
            id_vars="Collection Run",
            value_vars=["Slots Reduced", "Slots Increased"],
            var_name="Movement",
            value_name="Slots",
        )
        fig_me = px.bar(
            me_long,
            x="Collection Run",
            y="Slots",
            color="Movement",
            barmode="group",
            text="Slots",
            color_discrete_map={
                "Slots Reduced": PALETTE["reduction"],
                "Slots Increased": PALETTE["increase"],
            },
            title=f"Observed Movement by Run ({selected_obs_date})",
        )
        fig_me.update_traces(textposition="outside")
        st.plotly_chart(_style_fig(fig_me, 340), width="stretch")
        st.dataframe(me_df, width="stretch", hide_index=True)

    with col_b:
        st.subheader("Zone-Wise Daily Movement")
        zone_changes = changes.summarize_zone_daily_changes(
            observed_date=selected_obs_date, safari_mode=safari_mode
        )
        if not zone_changes.empty:
            fig_zone = go.Figure()
            fig_zone.add_trace(
                go.Bar(
                    name="Slots Reduced",
                    x=zone_changes["zone_name"],
                    y=-zone_changes["slots_reduced"],
                    marker_color=PALETTE["reduction"],
                )
            )
            fig_zone.add_trace(
                go.Bar(
                    name="Slots Increased",
                    x=zone_changes["zone_name"],
                    y=zone_changes["slots_increased"],
                    marker_color=PALETTE["increase"],
                )
            )
            fig_zone.add_trace(
                go.Scatter(
                    name="Net Change",
                    x=zone_changes["zone_name"],
                    y=zone_changes["net_change"],
                    mode="lines+markers",
                    marker=dict(size=8, color="#13251B"),
                    line=dict(width=2, color="#13251B"),
                )
            )
            fig_zone.update_layout(
                barmode="relative",
                title=f"Zone-Wise Slot Reductions, Increases & Net Change ({unit_suffix})",
                xaxis_title="Safari Zone",
                yaxis_title=f"Slot Change ({unit_suffix})",
            )
            st.plotly_chart(_style_fig(fig_zone, 340), width="stretch")

            st.dataframe(
                zone_changes.rename(
                    columns={
                        "zone_name": "Zone",
                        "unit_label": "Unit",
                        "slots_reduced": "Reduced",
                        "slots_increased": "Increased",
                        "net_change": "Net Change",
                        "morning_run_reduction": "Morning Run Reduced",
                        "evening_run_reduction": "Evening Run Reduced",
                        "observations_compared": "Pairs Compared",
                    }
                )[
                    [
                        "Zone",
                        "Reduced",
                        "Increased",
                        "Net Change",
                        "Morning Run Reduced",
                        "Evening Run Reduced",
                        "Pairs Compared",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(f"No change events recorded for {scope_label} on {selected_obs_date}.")

    # Multi-day daily movement timeline
    st.subheader("Daily Reduction vs Increase Timeline")
    mode_changes = changes.get_change_events_dataframe(safari_mode=safari_mode)
    if not mode_changes.empty:
        daily_timeline = (
            mode_changes.groupby("observed_date", as_index=False)
            .agg(
                slots_reduced=("availability_reduction", "sum"),
                slots_increased=("availability_increase", "sum"),
                net_change=("change_amount", "sum"),
            )
            .sort_values("observed_date")
        )
        fig_tl = go.Figure()
        fig_tl.add_trace(
            go.Bar(
                name="Daily Reduction",
                x=daily_timeline["observed_date"],
                y=daily_timeline["slots_reduced"],
                marker_color=PALETTE["reduction"],
            )
        )
        fig_tl.add_trace(
            go.Bar(
                name="Daily Increase",
                x=daily_timeline["observed_date"],
                y=daily_timeline["slots_increased"],
                marker_color=PALETTE["increase"],
            )
        )
        fig_tl.update_layout(
            barmode="group",
            title=f"Observed Daily Reductions & Increases Over Time ({unit_suffix})",
            xaxis_title="Observation Date (IST)",
            yaxis_title=f"Slots ({unit_suffix})",
        )
        st.plotly_chart(_style_fig(fig_tl, 320), width="stretch")

    # Detailed non-zero change events table + CSV download
    day_detail = mode_changes[
        (mode_changes["observed_date"] == selected_obs_date)
        & (mode_changes["change_amount"] != 0)
    ].sort_values(["availability_reduction", "availability_increase"], ascending=[False, False])

    st.subheader(f"Individual Slot Movements on {selected_obs_date} ({len(day_detail)} changed)")
    if not day_detail.empty:
        detail_cols = [
            "zone_name",
            "safari_date",
            "session",
            "run_period",
            "previous_available",
            "current_available",
            "availability_reduction",
            "availability_increase",
            "change_amount",
            "capacity_occupied_pct",
            "change_type",
            "observed_at",
        ]
        st.dataframe(
            day_detail[detail_cols].rename(
                columns={
                    "zone_name": "Zone",
                    "safari_date": "Safari Date",
                    "session": "Session",
                    "run_period": "Run",
                    "previous_available": "Prev Available",
                    "current_available": "Curr Available",
                    "availability_reduction": "Reduction",
                    "availability_increase": "Increase",
                    "change_amount": "Net Change",
                    "capacity_occupied_pct": "Occupied %",
                    "change_type": "Change Type",
                    "observed_at": "Observed At",
                }
            ),
            width="stretch",
            hide_index=True,
            height=340,
        )

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            label=f"Download {selected_obs_date} Change Events (CSV)",
            data=monitor.dataframe_to_csv_bytes(
                mode_changes[mode_changes["observed_date"] == selected_obs_date].drop(
                    columns=["observed_dt"], errors="ignore"
                )
            ),
            file_name=f"corbett_daily_changes_{selected_obs_date}_{'demo' if is_demo_mode else 'live'}.csv",
            mime="text/csv",
        )
    with dl2:
        if not df_24h.empty:
            st.download_button(
                label="Download 24-Hour Rolling Changes (CSV)",
                data=monitor.dataframe_to_csv_bytes(df_24h),
                file_name=f"corbett_24h_changes_{'demo' if is_demo_mode else 'live'}.csv",
                mime="text/csv",
            )


# ==============================================================================
# PAGE 4: HISTORICAL TRENDS
# ==============================================================================
def render_historical_trends_page(
    *,
    trends: TrendAnalyticsService,
    monitor: CollectionMonitoringService,
    is_demo_mode: bool,
) -> None:
    freshness = monitor.get_freshness_status()
    render_top_header(
        page_title="Historical Availability Trends & Lead-Time Patterns",
        page_subtitle=(
            "Analyze how displayed availability evolves across collection runs, zones, "
            "morning vs afternoon sessions, weekdays vs weekends, and safari lead times."
        ),
        is_demo_mode=is_demo_mode,
        freshness=freshness,
    )

    valid_df = trends.get_all_snapshots_dataframe(valid_only=True)
    if valid_df.empty:
        st.info(
            "No historical observations are stored in this database yet. "
            "Switch to **Demo / Sample Test Database** in the sidebar to inspect trend visualizations, "
            "or accumulate live morning/evening runs."
        )
        return

    scope_label = st.radio(
        "Unit Scope for Trend Comparisons",
        options=["Jeep Permits (7 Day-Safari Zones)", "Dhikala Canter Seats (16-Seater)"],
        horizontal=True,
    )
    safari_mode = "jeep_permit" if scope_label.startswith("Jeep") else "canter_seat"
    unit_label = "Jeep Permits" if safari_mode == "jeep_permit" else "Canter Seats"
    scoped_df = valid_df[valid_df["safari_mode"] == safari_mode].copy()
    if scoped_df.empty:
        st.warning(f"No valid snapshots found for {scope_label}.")
        return

    tab_time, tab_zone_session, tab_weekend, tab_lead, tab_intel = st.tabs(
        [
            "1. Trends Over Time",
            "2. Zone & Session Comparison",
            "3. Weekday vs Weekend",
            "4. Lead-Time Curve (30→1d)",
            "5. Research Intelligence",
        ]
    )

    # --- Tab 1: Trends over time ---
    with tab_time:
        available_zones = sorted(scoped_df["zone_name"].unique())
        tcol1, tcol2, tcol3 = st.columns([1.5, 1.3, 1.0])
        with tcol1:
            chosen_zones = st.multiselect(
                "Zones",
                options=available_zones,
                default=available_zones[: min(4, len(available_zones))],
                key="trend_zones",
            )
        date_counts = scoped_df.groupby("safari_date")["collection_run_id"].nunique()
        multi_obs_dates = sorted(date_counts[date_counts >= 2].index.tolist()) or sorted(
            scoped_df["safari_date"].unique().tolist()
        )
        default_date_idx = min(5, len(multi_obs_dates) - 1)
        with tcol2:
            focus_safari_date = st.selectbox(
                "Track Specific Safari Date Across Runs",
                options=multi_obs_dates,
                index=default_date_idx,
            )
        with tcol3:
            focus_session = st.selectbox(
                "Session",
                options=["morning", "afternoon"],
                index=0,
                format_func=str.title,
                key="trend_session",
            )

        series_df = scoped_df[
            (scoped_df["safari_date"] == focus_safari_date)
            & (scoped_df["session"] == focus_session)
            & (scoped_df["zone_name"].isin(chosen_zones))
        ].sort_values("captured_at")

        if not series_df.empty:
            fig_line = px.line(
                series_df,
                x="captured_at",
                y="available_slots",
                color="zone_name",
                markers=True,
                labels={
                    "captured_at": "Collection Timestamp (IST)",
                    "available_slots": f"Available {unit_label}",
                    "zone_name": "Zone",
                },
                title=(
                    f"How Availability Changed Over Time for Safari Date {focus_safari_date} "
                    f"({focus_session.title()} Session)"
                ),
            )
            st.plotly_chart(_style_fig(fig_line, 380), width="stretch")

        # Window-wide mean availability over collection timestamps
        run_avg = (
            scoped_df[scoped_df["zone_name"].isin(chosen_zones)]
            .groupby(["captured_at", "zone_name"], as_index=False)
            .agg(mean_available=("available_slots", "mean"))
            .sort_values("captured_at")
        )
        if not run_avg.empty:
            run_avg["mean_available"] = run_avg["mean_available"].round(2)
            fig_win = px.line(
                run_avg,
                x="captured_at",
                y="mean_available",
                color="zone_name",
                labels={
                    "captured_at": "Collection Run Timestamp (IST)",
                    "mean_available": f"Mean Available {unit_label} Across Window",
                    "zone_name": "Zone",
                },
                title="Rolling 30-Day Window Average Availability per Zone",
            )
            st.plotly_chart(_style_fig(fig_win, 340), width="stretch")

    # --- Tab 2: Zone & Session comparison ---
    with tab_zone_session:
        sess_df = trends.compute_session_comparison(safari_mode=safari_mode)
        if not sess_df.empty:
            fig_sess = px.bar(
                sess_df,
                x="zone_name",
                y="avg_available",
                color="session",
                barmode="group",
                text="avg_available",
                color_discrete_map={
                    "morning": PALETTE["morning"],
                    "afternoon": PALETTE["afternoon"],
                },
                labels={
                    "zone_name": "Safari Zone",
                    "avg_available": f"Mean Available {unit_label}",
                    "session": "Session",
                },
                title=f"Morning vs Afternoon Average Availability by Zone ({unit_label})",
            )
            fig_sess.update_traces(textposition="outside")
            st.plotly_chart(_style_fig(fig_sess, 370), width="stretch")
            st.dataframe(
                sess_df.rename(
                    columns={
                        "zone_name": "Zone",
                        "session": "Session",
                        "unit_label": "Unit",
                        "avg_available": "Avg Available",
                        "total_available": "Total Available (Window)",
                        "avg_occupied_pct": "Avg Occupied %",
                        "fully_unavailable_count": "Zero-Slot Dates",
                        "dates_count": "Dates Observed",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

    # --- Tab 3: Weekday vs Weekend ---
    with tab_weekend:
        wk_df = trends.compute_weekday_vs_weekend(safari_mode=safari_mode)
        if not wk_df.empty:
            wk_zone = (
                wk_df.groupby(["zone_name", "day_type"], as_index=False)
                .agg(
                    avg_available=("avg_available", "mean"),
                    avg_occupied_pct=("avg_occupied_pct", "mean"),
                )
                .round(2)
            )
            c_wk1, c_wk2 = st.columns(2)
            with c_wk1:
                fig_wk = px.bar(
                    wk_zone,
                    x="zone_name",
                    y="avg_available",
                    color="day_type",
                    barmode="group",
                    color_discrete_map={
                        "Weekday": PALETTE["weekday"],
                        "Weekend": PALETTE["weekend"],
                    },
                    labels={
                        "zone_name": "Safari Zone",
                        "avg_available": f"Avg Available {unit_label}",
                        "day_type": "Day Type",
                    },
                    title="Weekday vs Weekend Mean Available Slots",
                )
                st.plotly_chart(_style_fig(fig_wk, 350), width="stretch")
            with c_wk2:
                if wk_zone["avg_occupied_pct"].notna().any():
                    fig_wko = px.bar(
                        wk_zone,
                        x="zone_name",
                        y="avg_occupied_pct",
                        color="day_type",
                        barmode="group",
                        color_discrete_map={
                            "Weekday": PALETTE["weekday"],
                            "Weekend": PALETTE["weekend"],
                        },
                        labels={
                            "zone_name": "Safari Zone",
                            "avg_occupied_pct": "Avg Occupied %",
                            "day_type": "Day Type",
                        },
                        title="Weekday vs Weekend Validated Occupancy (%)",
                    )
                    st.plotly_chart(_style_fig(fig_wko, 350), width="stretch")
            st.dataframe(
                wk_df.rename(
                    columns={
                        "zone_name": "Zone",
                        "day_type": "Day Type",
                        "session": "Session",
                        "avg_available": "Avg Available",
                        "avg_occupied_pct": "Avg Occupied %",
                        "zero_slot_dates": "Zero-Slot Dates",
                        "dates_observed": "Dates Observed",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

    # --- Tab 4: Lead-Time Availability (30, 20, 15, 10, 5, 1 days before safari) ---
    with tab_lead:
        st.markdown(
            "**Target Lead-Time Milestones:** `30`, `20`, `15`, `10`, `5`, and `1` day(s) before safari date."
        )
        lead_summary = trends.compute_lead_time_summary(
            milestones=DEFAULT_LEAD_TIME_MILESTONES,
            safari_mode=safari_mode,
        )
        observed_milestones = (
            set(lead_summary["lead_time_days"].unique()) if not lead_summary.empty else set()
        )
        if 30 not in observed_milestones and 29 in set(scoped_df["lead_time_days"].unique()):
            st.caption(
                "Note: An inclusive 30-day rolling window starting today (e.g. Dec 1 → Dec 1–30) "
                "spans lead times 0 to 29 days. Set MONITORING_WINDOW_DAYS=31 in `.env` to also "
                "capture exact T+30 day snapshots; full 0–29 day curve is shown below."
            )

        if not lead_summary.empty:
            fig_lead = px.line(
                lead_summary.sort_values("lead_time_days", ascending=False),
                x="lead_time_days",
                y="avg_available_slots",
                color="zone_name",
                markers=True,
                labels={
                    "lead_time_days": "Days Before Safari (Lead Time)",
                    "avg_available_slots": f"Avg Available {unit_label}",
                    "zone_name": "Zone",
                },
                title="Mean Availability at Key Lead-Time Milestones (30, 20, 15, 10, 5, 1 Days)",
            )
            fig_lead.update_xaxes(autorange="reversed")
            st.plotly_chart(_style_fig(fig_lead, 370), width="stretch")

            pivot_lead = lead_summary.pivot(
                index="zone_name", columns="lead_time_days", values="avg_available_slots"
            )
            ordered_cols = [m for m in DEFAULT_LEAD_TIME_MILESTONES if m in pivot_lead.columns]
            pivot_display = pivot_lead[ordered_cols].rename(
                columns={m: f"{m}d before" for m in ordered_cols}
            ).reset_index().rename(columns={"zone_name": "Zone"})
            st.dataframe(pivot_display, width="stretch", hide_index=True)

        # Full continuous lead-time profile (0..30 days)
        full_lead = (
            scoped_df[scoped_df["lead_time_days"] >= 0]
            .groupby(["lead_time_days", "zone_name"], as_index=False)
            .agg(avg_available=("available_slots", "mean"))
            .round(2)
        )
        if not full_lead.empty:
            fig_full_lead = px.line(
                full_lead,
                x="lead_time_days",
                y="avg_available",
                color="zone_name",
                labels={
                    "lead_time_days": "Days Before Safari",
                    "avg_available": f"Avg Available {unit_label}",
                    "zone_name": "Zone",
                },
                title="Continuous Lead-Time Availability Curve Across Full Monitoring Window",
            )
            fig_full_lead.update_xaxes(autorange="reversed")
            st.plotly_chart(_style_fig(fig_full_lead, 340), width="stretch")

    # --- Tab 5: Future-Ready Descriptive Research Intelligence ---
    with tab_intel:
        st.caption(
            "Descriptive historical summaries only — speculative demand predictions are intentionally "
            "withheld until multi-season validated live observations accumulate."
        )
        intel = trends.compute_research_intelligence()

        ic1, ic2 = st.columns(2)
        with ic1:
            st.markdown("#### Fastest-Changing Safari Zones")
            if not intel["fastest_zones"].empty:
                st.dataframe(intel["fastest_zones"], width="stretch", hide_index=True)
            else:
                st.info("Accumulating more observations before ranking zone velocity.")

        with ic2:
            st.markdown("#### Dates Reaching Zero Displayed Availability")
            if not intel["fully_unavailable"].empty:
                st.dataframe(intel["fully_unavailable"], width="stretch", hide_index=True, height=260)
            else:
                st.info("No fully unavailable (0-slot) sessions recorded in current scope.")

        ic3, ic4 = st.columns(2)
        with ic3:
            st.markdown("#### High-Availability Safari Dates (≤ 25% Occupied)")
            if not intel["high_availability_dates"].empty:
                st.dataframe(
                    intel["high_availability_dates"], width="stretch", hide_index=True, height=240
                )
            else:
                st.info("No dates currently under 25% validated mean occupancy.")

        with ic4:
            st.markdown("#### Monthly Comparison Summary")
            if not intel["monthly_summary"].empty:
                st.dataframe(intel["monthly_summary"], width="stretch", hide_index=True, height=240)

        st.markdown("#### Unusual Availability Increases, Drops & Capacity Adjustments")
        if not intel["unusual_movements"].empty:
            u_cols = [
                "observed_at",
                "zone_name",
                "safari_date",
                "session",
                "previous_available",
                "current_available",
                "change_amount",
                "previous_capacity",
                "current_capacity",
                "change_type",
            ]
            st.dataframe(
                intel["unusual_movements"][u_cols], width="stretch", hide_index=True, height=260
            )
        else:
            st.info("No unusual availability jumps or capacity adjustments detected yet.")

    st.download_button(
        label="Download Historical Snapshots (CSV)",
        data=monitor.dataframe_to_csv_bytes(
            scoped_df.drop(columns=["captured_dt"], errors="ignore")
        ),
        file_name=f"corbett_historical_snapshots_{'demo' if is_demo_mode else 'live'}.csv",
        mime="text/csv",
    )


# ==============================================================================
# PAGE 5: COLLECTION MONITORING & ADMIN
# ==============================================================================
def render_collection_monitoring_page(
    *,
    config: AppConfig,
    repo: SafariMonitorRepository,
    trends: TrendAnalyticsService,
    changes: ChangeDetectionService,
    monitor: CollectionMonitoringService,
    is_demo_mode: bool,
) -> None:
    freshness = monitor.get_freshness_status()
    render_top_header(
        page_title="Collection Monitoring, Schedule & CSV Reports",
        page_subtitle=(
            "Audit collection runs, inspect missing dates/zones, review gate/error logs and "
            "diagnostic screenshots, trigger manual live checks, and export CSV reports."
        ),
        is_demo_mode=is_demo_mode,
        freshness=freshness,
    )

    # --- Live Action Center: Record Real Data Now | Playwright Run & Schedule | Setup Checklist ---
    live_backend_ref = create_backend(config.database_url)
    initialize_schema(live_backend_ref, seed_official_zones=True)
    live_repo_ref = SafariMonitorRepository(live_backend_ref, timezone_name=config.timezone_name)
    live_zones = live_repo_ref.list_zones(active_only=True)

    act_tab_auto, act_tab_record, act_tab_setup = st.tabs(
        [
            "Playwright Run & Schedule",
            "Record Real Observation (Form / CSV)",
            "Setup Checklist & Selector Approval",
        ]
    )

    with act_tab_auto:
        readiness_items = check_system_readiness(config, live_zone_count=len(live_zones))
        chromium_ready = readiness_items[2]["ready"]
        selectors_ready = readiness_items[4]["ready"]
        if not chromium_ready:
            st.info(
                "**Cloud Preview Notice:** Automated Playwright collection must run on **your own "
                "computer** because `safari.corbettgov.org` requires real browser location "
                "permission and blocks cloud IPs. Download `corbett-safari-monitor` and run "
                "`setup_and_run.bat` → `2_calibrate_live_portal.bat` → `3_collect_live_data_now.bat` "
                "(or use the **Record Real Observation (Form / CSV)** tab right here now)."
            )
        elif not selectors_ready:
            st.info(
                "**One-Time Setup (No Commands Needed!):** Click **Step 1** below to open "
                "`safari.corbettgov.org` in your real Chrome/Edge. Accept the declaration, click "
                "**Allow** on location, select **1 open safari date** so slots appear, then come "
                "back here and click **Step 2: Capture Page Now**."
            )
            cal_c1, cal_c2, cal_c3 = st.columns([1.2, 1.2, 1.1])
            inspect_script = Path(__file__).resolve().parents[2] / "scripts" / "inspect_portal.py"
            state_file = config.inspection_dir / "calibration_state.json"
            signal_file = config.inspection_dir / "capture_now.signal"
            latest_report = config.inspection_dir / "inspection_latest.json"

            with cal_c1:
                if st.button(
                    "Step 1: Open Corbett Portal (Stays Open)",
                    type="primary",
                    width="stretch",
                    key="btn_open_cal",
                ):
                    signal_file.unlink(missing_ok=True)
                    subprocess.Popen(
                        [sys.executable, str(inspect_script), "--wait-for-signal"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    st.success(
                        "Opening Chrome/Edge now! Accept consent, Allow location, pick 1 open "
                        "date, then click **Step 2**."
                    )
            with cal_c2:
                if st.button(
                    "Step 2: Capture Page Now",
                    width="stretch",
                    key="btn_capture_cal",
                ):
                    config.inspection_dir.mkdir(parents=True, exist_ok=True)
                    signal_file.write_text("capture", encoding="utf-8")
                    import time as _t

                    for _ in range(16):
                        _t.sleep(0.5)
                        if not signal_file.exists():
                            break
                    _t.sleep(1.5)
                    st.success("Captured! Open **Setup Checklist & Selector Approval** tab (or download report).")
            with cal_c3:
                if latest_report.exists():
                    st.download_button(
                        label="Download inspection_latest.json",
                        data=latest_report.read_bytes(),
                        file_name="inspection_latest.json",
                        mime="application/json",
                        width="stretch",
                    )

            if state_file.exists():
                try:
                    st_data = json.loads(state_file.read_text(encoding="utf-8"))
                    st.caption(f"Setup status (`{st_data.get('status')}`): {st_data.get('detail')}")
                except Exception:  # noqa: BLE001
                    pass

        adm_left, adm_right = st.columns([1.35, 1.65])
        with adm_left:
            st.subheader("Manual Live Collection Run")
            st.caption(
                "Starts an immediate read-only Playwright check against `safari.corbettgov.org` "
                "and records audit logs into the **LIVE** database (`data/corbett_monitor.db`). "
                "Stops safely without bypassing if location verification, maintenance, or "
                "network restrictions block access."
            )
            quick_test_2d = st.checkbox(
                "Quick 2-day test run first (verifies automatic date switching in ~15s)",
                value=False,
                key="quick_2day_check",
            )
            if st.button("Start Manual Live Collection Run", type="primary"):
                run_script = Path(__file__).resolve().parents[2] / "scripts" / "run_collector.py"
                cmd = [sys.executable, str(run_script), "--type", "manual"]
                if quick_test_2d:
                    cmd.extend(["--days", "2"])
                with st.spinner(
                    "Running automated read-only collection (if a consent/location prompt opens "
                    "on your screen, click Allow — all dates & zones scan automatically)..."
                ):
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=900,
                        check=False,
                    )
                latest_runs = live_repo_ref.list_collection_runs(limit=1)
                latest = latest_runs[0] if latest_runs else None
                if latest and latest["status"] in {"completed", "partial"}:
                    st.success(
                        f"Live Run #{latest['id']} finished (`{latest['status']}`) for window "
                        f"{latest['date_window_start']} -> {latest['date_window_end']}!"
                    )
                    if proc.stdout.strip():
                        st.code(proc.stdout.strip())
                elif latest:
                    st.warning(
                        f"Live Run #{latest['id']} stopped cleanly with status "
                        f"`{latest['status']}`: {latest.get('error_summary') or proc.stderr[:300]}"
                    )
                else:
                    st.error(proc.stderr.strip() or proc.stdout.strip() or "Run failed to start.")

        with adm_right:
            st.subheader("Configured Twice-Daily Schedule")
            sched_warnings = validate_schedule_times(config)
            for warning in sched_warnings:
                st.warning(warning)
            upcoming = preview_upcoming_runs(config)
            if upcoming:
                st.dataframe(
                    pd.DataFrame(upcoming).rename(
                        columns={
                            "collection_type": "Run Type",
                            "next_run_at": "Next Scheduled Run",
                            "window_start": "Window Start",
                            "window_end": "Window End",
                            "window_days": "Days",
                        }
                    )[["Run Type", "Next Scheduled Run", "Window Start", "Window End", "Days"]],
                    width="stretch",
                    hide_index=True,
                )
            st.caption(
                f"Edit `.env` anytime: `MORNING_COLLECTION_TIME={config.morning_collection_time.strftime('%H:%M')}`, "
                f"`EVENING_COLLECTION_TIME={config.evening_collection_time.strftime('%H:%M')}`, "
                f"`COLLECTION_TIMEZONE={config.timezone_name}`, "
                f"`MONITORING_WINDOW_DAYS={config.monitoring_window_days}`."
            )

    with act_tab_record:
        st.subheader("Record Real Portal Observations Into Live Database")
        st.caption(
            "Works immediately with zero selector configuration: open `https://safari.corbettgov.org/` "
            "in your browser, type the visible numbers (e.g. `18 / 30`, `22`, `Sold Out`, `Closed`), "
            "and leave unchecked cells blank (never treated as zero). Saves to `data/corbett_monitor.db` "
            "and automatically calculates availability changes!"
        )
        rec_col_form, rec_col_csv = st.columns([1.6, 1.1])
        with rec_col_form:
            today_d = now_in_timezone(config.timezone_name).date()
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                entry_date = st.date_input("Safari Date Observed", value=today_d, key="manual_obs_date")
            with fc2:
                entry_run_type = st.selectbox(
                    "Observation Slot",
                    options=["manual", "morning", "evening"],
                    format_func=str.title,
                    key="manual_obs_type",
                )
            with fc3:
                confirm_units = st.checkbox(
                    "Units verified on portal",
                    value=True,
                    help="Keep checked when you confirmed Jeep permits vs Canter seats on screen.",
                    key="manual_obs_verified",
                )

            with st.form("quick_manual_observation_form", clear_on_submit=True):
                st.markdown("**Enter Raw Displayed Values** *(leave blank if not observed)*")
                inputs: list[tuple[str, str, str]] = []
                for z in live_zones:
                    z_name = str(z["zone_name"])
                    unit_hint = str(z["unit_label"])
                    zc1, zc2, zc3 = st.columns([1.1, 1.2, 1.2])
                    zc1.markdown(f"**{z_name}**  \n<small>{unit_hint}</small>", unsafe_allow_html=True)
                    m_txt = zc2.text_input(
                        f"{z_name} Morning",
                        placeholder="e.g. 18 / 30 or Closed",
                        label_visibility="collapsed",
                        key=f"m_in_{z_name}",
                    )
                    a_txt = zc3.text_input(
                        f"{z_name} Afternoon",
                        placeholder="e.g. 12 / 30 or Sold Out",
                        label_visibility="collapsed",
                        key=f"a_in_{z_name}",
                    )
                    inputs.append((z_name, m_txt, a_txt))

                submitted = st.form_submit_button("Save Observation to Live Database", type="primary")
                if submitted:
                    obs_rows = [
                        ManualObservationRow(
                            safari_date=entry_date.isoformat(),
                            zone_name=z_name,
                            morning_raw=m_txt.strip() or None,
                            afternoon_raw=a_txt.strip() or None,
                        )
                        for z_name, m_txt, a_txt in inputs
                        if m_txt.strip() or a_txt.strip()
                    ]
                    try:
                        res = ingest_manual_observations(
                            live_repo_ref,
                            obs_rows,
                            collection_type=entry_run_type,
                            source_section="operator_manual_entry",
                            unit_validated=confirm_units,
                            timezone_name=config.timezone_name,
                        )
                        st.success(
                            f"Saved Live Run #{res.run_id}: {res.valid_snapshots} valid snapshot(s), "
                            f"{res.change_events_recorded} change event(s). Switch the sidebar to "
                            "**Live Database (Real Only)** to view them across all 5 pages!"
                        )
                        for w in res.warnings:
                            st.warning(w)
                    except ValueError as exc:
                        st.error(str(exc))

        with rec_col_csv:
            st.markdown("#### Bulk CSV Observation Import")
            st.caption(
                "Prefer recording a full 7-day or 30-day check in Excel / Google Sheets? "
                "Download the template, fill the visible numbers, and upload it here."
            )
            tpl_bytes = generate_observation_csv_template(
                live_zones,
                window_days=config.monitoring_window_days,
                timezone_name=config.timezone_name,
            )
            st.download_button(
                label=f"Download {config.monitoring_window_days}-Day Blank CSV Template",
                data=tpl_bytes,
                file_name="corbett_observation_template.csv",
                mime="text/csv",
                width="stretch",
            )
            uploaded_csv = st.file_uploader(
                "Upload Filled Observation CSV",
                type=["csv"],
                key="manual_csv_upload",
            )
            if uploaded_csv is not None and st.button("Import CSV Into Live Database"):
                try:
                    parsed_rows = parse_observation_csv(uploaded_csv.getvalue())
                    res = ingest_manual_observations(
                        live_repo_ref,
                        parsed_rows,
                        collection_type="manual",
                        source_section="operator_csv_import",
                        unit_validated=True,
                        timezone_name=config.timezone_name,
                    )
                    st.success(
                        f"Imported Live Run #{res.run_id}: {res.valid_snapshots} valid snapshot(s), "
                        f"{res.change_events_recorded} change event(s) calculated!"
                    )
                    for w in res.warnings[:8]:
                        st.warning(w)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"CSV import failed: {exc}")

    with act_tab_setup:
        st.subheader("System Readiness Checklist")
        checklist = check_system_readiness(config, live_zone_count=len(live_zones))
        chk_df = pd.DataFrame(
            [
                {
                    "Step": item["step"],
                    "Status": f"{'✅' if item['ready'] else '⏳'} {item['status']}",
                    "Details / Exact Action": item["detail"],
                }
                for item in checklist
            ]
        )
        st.dataframe(chk_df, width="stretch", hide_index=True)

        st.markdown("#### One-Click Selector Approval (No Manual JSON Editing)")
        suggested_file = config.inspection_dir / "suggested_selectors.json"
        default_nav: dict[str, Any] = {}
        default_avail: dict[str, Any] = {}
        default_unit: dict[str, Any] = {}
        default_consent: dict[str, Any] = {}

        # Pre-populate from existing verified config if present, else from suggested_selectors.json
        if config.selectors_config_path.exists():
            try:
                existing_cfg = json.loads(config.selectors_config_path.read_text(encoding="utf-8"))
                default_nav = existing_cfg.get("navigation") or {}
                default_avail = existing_cfg.get("availability") or {}
                default_unit = existing_cfg.get("unit_validation") or {}
                default_consent = existing_cfg.get("consent_modals") or {}
            except Exception:  # noqa: BLE001
                pass

        if suggested_file.exists():
            try:
                disc = json.loads(suggested_file.read_text(encoding="utf-8"))
                sug = disc.get("suggested_config") or {}
                if not default_nav:
                    default_nav = sug.get("navigation") or {}
                if not default_avail:
                    default_avail = sug.get("availability") or {}
                if not default_unit:
                    default_unit = sug.get("unit_validation") or {}
                if not default_consent:
                    default_consent = sug.get("consent_modals") or {}
                samples = disc.get("matched_samples") or []
                if samples:
                    st.info(
                        f"Loaded {len(samples)} auto-discovered zone sample(s) from "
                        "`data/inspection/suggested_selectors.json`. Confirm they match what "
                        "you saw on screen before clicking Save:"
                    )
                    st.dataframe(pd.DataFrame(samples), width="stretch", hide_index=True)
            except Exception:  # noqa: BLE001
                pass
        elif not config.selectors_config_path.exists():
            st.caption(
                "Run `2_calibrate_live_portal.bat` (or `python scripts/inspect_portal.py --interactive`) "
                "on your laptop first — it populates these boxes automatically from the live portal."
            )

        with st.form("approve_selectors_form"):
            sc1, sc2 = st.columns(2)
            zone_card_sel = sc1.text_input(
                "Zone Card CSS Selector", value=str(default_nav.get("zone_card_selector", ""))
            )
            zone_name_sel = sc2.text_input(
                "Zone Name CSS Selector", value=str(default_nav.get("zone_name_selector", ""))
            )
            morn_sel = sc1.text_input(
                "Morning Availability CSS Selector",
                value=str(default_avail.get("morning_availability_selector", "")),
            )
            aft_sel = sc2.text_input(
                "Afternoon Availability CSS Selector",
                value=str(default_avail.get("afternoon_availability_selector", "")),
            )
            date_tpl = sc1.text_input(
                "Calendar Date Cell Template ({date}, {dmy}, or {aria_date})",
                value=str(default_nav.get("date_cell_template", "")),
            )
            next_month_sel = sc2.text_input(
                "Calendar Next-Month Arrow Selector (for automatic month change)",
                value=str(default_nav.get("calendar_next_month_selector", "")),
            )
            date_url_tpl = sc1.text_input(
                "OR Direct Date URL Template (optional, uses {date})",
                value=str(default_nav.get("date_url_template", "")),
            )
            unit_meaning = sc2.text_input(
                "Confirmed Slot Meaning on Portal",
                value=str(default_unit.get("jeep_slots_confirmed_meaning") or ""),
                placeholder="e.g. Remaining Jeep permits per shift (Dhikala = Canter seats)",
            )
            if st.form_submit_button("Save & Verify Selectors (`config/selectors.json`)"):
                payload = {
                    "verified": True,
                    "verified_at": format_iso_timestamp(now_in_timezone(config.timezone_name)),
                    "verified_by": "local_operator_dashboard",
                    "portal_url": config.portal_url,
                    "unit_validation": {
                        "jeep_slots_confirmed_meaning": unit_meaning.strip() or None,
                        "canter_slots_confirmed_meaning": (
                            "Canter seats" if unit_meaning.strip() else None
                        ),
                        "capacity_displayed_on_portal": bool(
                            default_unit.get("capacity_displayed_on_portal", False)
                        ),
                    },
                    "consent_modals": {
                        "tourist_instructions_close": str(
                            default_consent.get("tourist_instructions_close", "")
                        ),
                        "important_info_acknowledge": str(
                            default_consent.get("important_info_acknowledge", "")
                        ),
                    },
                    "navigation": {
                        "date_picker_trigger": str(default_nav.get("date_picker_trigger", "")),
                        "date_cell_template": date_tpl.strip(),
                        "calendar_next_month_selector": next_month_sel.strip(),
                        "date_url_template": date_url_tpl.strip(),
                        "date_status_selector": str(default_nav.get("date_status_selector", "")),
                        "zone_card_selector": zone_card_sel.strip(),
                        "zone_name_selector": zone_name_sel.strip(),
                        "zone_id_attribute": str(default_nav.get("zone_id_attribute", "")),
                        "zone_expand_selector": str(default_nav.get("zone_expand_selector", "")),
                        "zone_dropdown_selector": str(
                            default_nav.get("zone_dropdown_selector", "")
                        ),
                        "zone_dropdown_options": list(
                            default_nav.get("zone_dropdown_options") or []
                        ),
                        "zone_url_templates": dict(default_nav.get("zone_url_templates") or {}),
                    },
                    "availability": {
                        "morning_availability_selector": morn_sel.strip(),
                        "morning_capacity_selector": str(
                            default_avail.get("morning_capacity_selector", "")
                        ),
                        "afternoon_availability_selector": aft_sel.strip(),
                        "afternoon_capacity_selector": str(
                            default_avail.get("afternoon_capacity_selector", "")
                        ),
                        "source_section_label": str(
                            default_avail.get("source_section_label", "calendar_zone_availability")
                        ),
                    },
                }
                tmp_check = config.inspection_dir / "_pending_selector_check.json"
                tmp_check.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                is_valid, invalid_reason = load_selector_config(tmp_check).validate_for_collection()
                tmp_check.unlink(missing_ok=True)
                if not is_valid:
                    st.error(f"Cannot enable automation yet: {invalid_reason}")
                else:
                    config.selectors_config_path.parent.mkdir(parents=True, exist_ok=True)
                    config.selectors_config_path.write_text(
                        json.dumps(payload, indent=2), encoding="utf-8"
                    )
                    st.success(
                        f"Saved verified selector config to `{config.selectors_config_path}`! "
                        "Automated 30-day Playwright runs are now enabled."
                    )

    st.divider()

    # --- Run Health KPIs ---
    health = monitor.get_run_health_summary()
    h1, h2, h3, h4, h5, h6 = st.columns(6)
    h1.metric("Total Runs", str(health["total_runs"]))
    h2.metric("Completed", str(health["completed_runs"]))
    h3.metric("Partial", str(health["partial_runs"]))
    h4.metric("Blocked", str(health["blocked_runs"]))
    h5.metric("Failed / Interrupted", str(health["failed_runs"] + health["interrupted_runs"]))
    h6.metric(
        "Last Valid Run",
        freshness["last_success_at"].split(" ")[0] if freshness["has_successful_run"] else "None",
        freshness["status_label"] if freshness["has_successful_run"] else "No observations",
        delta_color="off",
    )

    runs = repo.list_collection_runs(limit=200)
    runs_df = pd.DataFrame(runs) if runs else pd.DataFrame()

    if not runs_df.empty:
        r_left, r_right = st.columns([2.2, 1.0])
        with r_left:
            st.subheader("Collection Run History")
            st.dataframe(
                runs_df[
                    [
                        "id",
                        "started_at",
                        "completed_at",
                        "collection_type",
                        "date_window_start",
                        "date_window_end",
                        "status",
                        "is_demo",
                        "error_summary",
                    ]
                ].rename(
                    columns={
                        "id": "Run ID",
                        "started_at": "Started At",
                        "completed_at": "Completed At",
                        "collection_type": "Type",
                        "date_window_start": "Window Start",
                        "date_window_end": "Window End",
                        "status": "Status",
                        "is_demo": "Demo?",
                        "error_summary": "Notes / Error Summary",
                    }
                ),
                width="stretch",
                hide_index=True,
                height=310,
            )
        with r_right:
            st.subheader("Run Status Breakdown")
            status_counts = runs_df["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Runs"]
            fig_status = px.bar(
                status_counts,
                x="Status",
                y="Runs",
                color="Status",
                text="Runs",
                color_discrete_map={
                    "completed": PALETTE["forest"],
                    "partial": PALETTE["morning"],
                    "blocked": PALETTE["amber"],
                    "failed": PALETTE["reduction"],
                    "interrupted": PALETTE["neutral"],
                },
                title="Runs by Terminal Status",
            )
            fig_status.update_traces(textposition="outside")
            fig_status.update_layout(showlegend=False)
            st.plotly_chart(_style_fig(fig_status, 310), width="stretch")

        # --- Missing Dates & Missing Zones Inspector ---
        st.subheader("Missing Dates & Missing Zones Coverage Audit")
        run_options = {
            f"Run #{r['id']} · {r['collection_type']} · {r['started_at']} ({r['status']})": int(
                r["id"]
            )
            for r in runs
        }
        chosen_label = st.selectbox("Inspect Run Coverage", options=list(run_options.keys()))
        gaps = monitor.detect_run_coverage_gaps(run_options[chosen_label])

        g1, g2, g3 = st.columns(3)
        g1.metric("Completely Missing Dates", str(len(gaps["missing_dates"])))
        g2.metric("Dates With Partial/NULL Cells", str(len(gaps["incomplete_dates"])))
        g3.metric("Missing Zones", str(len(gaps["missing_zones"])))

        if gaps["missing_zones"]:
            st.warning(f"Missing zones in Run #{gaps['run_id']}: {', '.join(gaps['missing_zones'])}")
        if gaps["incomplete_dates"]:
            preview_dates = ", ".join(gaps["incomplete_dates"][:12])
            extra = (
                f" (+{len(gaps['incomplete_dates']) - 12} more)"
                if len(gaps["incomplete_dates"]) > 12
                else ""
            )
            st.info(f"Dates with missing or partial observations: {preview_dates}{extra}")
        if not gaps["missing_zones"] and not gaps["incomplete_dates"]:
            st.success(
                f"Run #{gaps['run_id']} captured complete coverage across all "
                f"{len(gaps['expected_dates'])} monitored dates and all active zones."
            )

        if not gaps["failed_observations"].empty:
            st.markdown("**Non-Success / NULL Observations in Selected Run:**")
            st.dataframe(
                gaps["failed_observations"][
                    [
                        "safari_date",
                        "zone_name",
                        "session",
                        "available_slots",
                        "collection_status",
                        "raw_displayed_value",
                        "error_details",
                        "captured_at",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )
    else:
        st.info("No collection runs have been executed against this database yet.")

    # --- Last Successful Observation per Zone ---
    st.subheader("Last Successful Observation by Zone")
    last_obs_df = monitor.get_last_successful_observation_by_zone()
    if not last_obs_df.empty:
        st.dataframe(
            last_obs_df.rename(
                columns={
                    "zone_name": "Zone",
                    "source_zone_identifier": "Portal Zone ID",
                    "entry_gate": "Entry Gate",
                    "unit_label": "Unit",
                    "last_success_at": "Last Successful Observation",
                    "valid_snapshots": "Valid Snapshots",
                    "issue_snapshots": "Missing / Error Snapshots",
                }
            )[
                [
                    "Zone",
                    "Portal Zone ID",
                    "Entry Gate",
                    "Unit",
                    "Last Successful Observation",
                    "Valid Snapshots",
                    "Issue Snapshots"
                    if "Issue Snapshots" in last_obs_df.columns
                    else "Missing / Error Snapshots",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

    # --- Collection Errors & Diagnostic Screenshots ---
    st.subheader("Collection Errors, Access Gates & Diagnostic Logs")
    errors_only = st.checkbox("Show only warnings, blocks, and errors", value=True)
    logs = repo.list_collection_logs(errors_only=errors_only, limit=300)
    logs_df = pd.DataFrame(logs) if logs else pd.DataFrame()
    if not logs_df.empty:
        st.dataframe(
            logs_df[
                [
                    "id",
                    "collection_run_id",
                    "logged_at",
                    "page_or_zone",
                    "status",
                    "error_message",
                    "screenshot_path",
                ]
            ],
            width="stretch",
            hide_index=True,
            height=260,
        )
        # Render diagnostic screenshot preview if any saved file exists
        shot_rows = [
            row
            for row in logs
            if row.get("screenshot_path") and Path(str(row["screenshot_path"])).exists()
        ]
        if shot_rows:
            with st.expander(f"View Diagnostic Screenshots ({len(shot_rows)} available)"):
                selected_shot = st.selectbox(
                    "Select Screenshot",
                    options=[str(r["screenshot_path"]) for r in shot_rows],
                )
                st.image(selected_shot, caption=selected_shot)
    else:
        st.caption("No matching diagnostic log entries.")

    # --- Administrator CSV Export Center ---
    st.divider()
    st.subheader("Administrator CSV Report Downloads")
    tag = "demo" if is_demo_mode else "live"
    exp1, exp2, exp3, exp4 = st.columns(4)

    all_snaps = trends.get_all_snapshots_dataframe(valid_only=False).drop(
        columns=["captured_dt"], errors="ignore"
    )
    all_chg = changes.get_change_events_dataframe().drop(columns=["observed_dt"], errors="ignore")
    all_logs_df = pd.DataFrame(repo.list_collection_logs(errors_only=False, limit=5000))

    with exp1:
        st.download_button(
            label="Snapshots CSV",
            data=monitor.dataframe_to_csv_bytes(all_snaps),
            file_name=f"corbett_snapshots_{tag}.csv",
            mime="text/csv",
            disabled=all_snaps.empty,
            width="stretch",
        )
    with exp2:
        st.download_button(
            label="Change Events CSV",
            data=monitor.dataframe_to_csv_bytes(all_chg),
            file_name=f"corbett_change_events_{tag}.csv",
            mime="text/csv",
            disabled=all_chg.empty,
            width="stretch",
        )
    with exp3:
        st.download_button(
            label="Collection Runs CSV",
            data=monitor.dataframe_to_csv_bytes(runs_df),
            file_name=f"corbett_collection_runs_{tag}.csv",
            mime="text/csv",
            disabled=runs_df.empty,
            width="stretch",
        )
    with exp4:
        st.download_button(
            label="Collection Logs CSV",
            data=monitor.dataframe_to_csv_bytes(all_logs_df),
            file_name=f"corbett_collection_logs_{tag}.csv",
            mime="text/csv",
            disabled=all_logs_df.empty,
            width="stretch",
        )
