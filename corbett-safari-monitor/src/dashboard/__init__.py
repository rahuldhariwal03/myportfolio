"""Streamlit dashboard UI components and page renderers."""

from src.dashboard.pages import (
    render_collection_monitoring_page,
    render_daily_changes_page,
    render_historical_trends_page,
    render_overview_page,
    render_zone_availability_page,
)
from src.dashboard.theme import inject_custom_css

__all__ = [
    "inject_custom_css",
    "render_collection_monitoring_page",
    "render_daily_changes_page",
    "render_historical_trends_page",
    "render_overview_page",
    "render_zone_availability_page",
]
