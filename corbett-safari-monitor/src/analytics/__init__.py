"""Analytics package: change detection, trend analysis, and collection health monitoring."""

from src.analytics.change_detector import (
    ChangeComputation,
    ChangeDetectionService,
    calculate_slot_change,
    compute_capacity_occupied_pct,
)
from src.analytics.monitoring import CollectionMonitoringService
from src.analytics.trends import DEFAULT_LEAD_TIME_MILESTONES, TrendAnalyticsService

__all__ = [
    "ChangeComputation",
    "ChangeDetectionService",
    "CollectionMonitoringService",
    "DEFAULT_LEAD_TIME_MILESTONES",
    "TrendAnalyticsService",
    "calculate_slot_change",
    "compute_capacity_occupied_pct",
]
