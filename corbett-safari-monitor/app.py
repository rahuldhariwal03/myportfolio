"""Streamlit entry point for the Corbett Safari Availability Monitoring & Intelligence System.

Run locally with:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.analytics import (
    ChangeDetectionService,
    CollectionMonitoringService,
    TrendAnalyticsService,
)
from src.config import load_config
from src.dashboard import (
    inject_custom_css,
    render_collection_monitoring_page,
    render_daily_changes_page,
    render_historical_trends_page,
    render_overview_page,
    render_zone_availability_page,
)
from src.database import SafariMonitorRepository, create_backend, initialize_schema
from src.date_window import calculate_rolling_window, now_in_timezone


def _sqlite_file_exists(database_url: str) -> bool:
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return True
    return Path(database_url[len("sqlite:///") :]).exists()


def main() -> None:
    st.set_page_config(
        page_title="Corbett Safari Availability Monitor",
        page_icon="🐅",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_custom_css()

    config = load_config()
    config.ensure_directories()

    # Ensure live database schema + official zones always exist (with zero fake rows)
    live_backend = create_backend(config.database_url)
    initialize_schema(live_backend, seed_official_zones=True)
    live_repo = SafariMonitorRepository(live_backend, timezone_name=config.timezone_name)
    live_counts = live_repo.get_database_summary()

    demo_exists = _sqlite_file_exists(config.demo_database_url)

    with st.sidebar:
        st.markdown("### Corbett Safari Monitor")
        st.caption("Private Read-Only Availability Intelligence")
        st.divider()

        page = st.radio(
            "Navigation",
            options=[
                "1. Overview",
                "2. Zone-Wise Availability",
                "3. Daily Changes",
                "4. Historical Trends",
                "5. Collection Monitoring",
            ],
            index=0,
        )

        st.divider()
        st.markdown("#### Data Source")
        db_options = ["Live Database (Real Only)"]
        if demo_exists:
            db_options.append("Demo / Sample Test Data [DEMO]")

        # If live DB has 0 snapshots and isolated demo DB exists, default to Demo
        # with an unmistakable DEMO banner while keeping Live DB 1 click away.
        default_idx = 1 if (live_counts["availability_snapshots"] == 0 and demo_exists) else 0
        chosen_source = st.radio(
            "Select Database",
            options=db_options,
            index=default_idx,
            help=(
                "Live observations and demonstration sample records are stored in completely "
                "separate SQLite files so synthetic data never contaminates live research."
            ),
        )
        is_demo_mode = chosen_source.endswith("[DEMO]")

        st.divider()
        now_ist = now_in_timezone(config.timezone_name)
        win = calculate_rolling_window(
            now_ist,
            window_days=config.monitoring_window_days,
            timezone_name=config.timezone_name,
        )
        st.markdown("#### Active Configuration")
        st.caption(
            f"**IST Clock:** {now_ist.strftime('%Y-%m-%d %H:%M %Z')}  \n"
            f"**Rolling Window:** {win.start_date} → {win.end_date} ({win.window_days}d)  \n"
            f"**Schedule:** {config.morning_collection_time.strftime('%H:%M')} & "
            f"{config.evening_collection_time.strftime('%H:%M')} {config.timezone_name}  \n"
            f"**Mode:** Strictly Read-Only"
        )

    active_url = config.demo_database_url if is_demo_mode else config.database_url
    active_backend = create_backend(active_url)
    initialize_schema(active_backend, seed_official_zones=True)
    active_repo = SafariMonitorRepository(active_backend, timezone_name=config.timezone_name)

    trends = TrendAnalyticsService(active_repo, timezone_name=config.timezone_name)
    changes = ChangeDetectionService(active_repo, timezone_name=config.timezone_name)
    monitor = CollectionMonitoringService(
        active_repo,
        timezone_name=config.timezone_name,
        stale_threshold_hours=config.stale_data_threshold_hours,
    )

    if page.startswith("1."):
        render_overview_page(
            config=config,
            repo=active_repo,
            trends=trends,
            changes=changes,
            monitor=monitor,
            is_demo_mode=is_demo_mode,
        )
    elif page.startswith("2."):
        render_zone_availability_page(
            repo=active_repo,
            trends=trends,
            monitor=monitor,
            is_demo_mode=is_demo_mode,
        )
    elif page.startswith("3."):
        render_daily_changes_page(
            changes=changes,
            monitor=monitor,
            is_demo_mode=is_demo_mode,
        )
    elif page.startswith("4."):
        render_historical_trends_page(
            trends=trends,
            monitor=monitor,
            is_demo_mode=is_demo_mode,
        )
    else:
        render_collection_monitoring_page(
            config=config,
            repo=active_repo,
            trends=trends,
            changes=changes,
            monitor=monitor,
            is_demo_mode=is_demo_mode,
        )


if __name__ == "__main__":
    main()
