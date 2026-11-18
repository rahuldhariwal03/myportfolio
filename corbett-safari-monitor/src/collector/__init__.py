"""Collector package: compliance gate inspection, raw value parsing, selector contract,
DOM selector discovery, manual/CSV ingestion, readiness checks, and Playwright collector.
"""

from src.collector.compliance import (
    HUMAN_RESOLVABLE_GATE_TYPES,
    AccessGateFinding,
    ReadOnlyGuard,
    ReadOnlyViolationError,
    extract_visible_text_from_html,
    first_blocking_gate,
    inspect_visible_gates,
)
from src.collector.dom_discovery import discover_candidate_selectors
from src.collector.manual_ingest import (
    ManualIngestResult,
    ManualObservationRow,
    generate_observation_csv_template,
    ingest_manual_observations,
    parse_observation_csv,
)
from src.collector.parser import (
    ParsedAvailability,
    aggregate_date_operating_status,
    normalize_zone_name,
    parse_availability_text,
    parse_capacity_text,
)
from src.collector.playwright_collector import (
    BrowserDriver,
    CollectionRunResult,
    CollectorBusyError,
    PageInspectionState,
    PlaywrightBrowserDriver,
    RawZoneCard,
    SafariAvailabilityCollector,
)
from src.collector.readiness import check_system_readiness
from src.collector.selectors import (
    SelectorConfig,
    format_date_template,
    load_selector_config,
)

__all__ = [
    "AccessGateFinding",
    "BrowserDriver",
    "CollectionRunResult",
    "CollectorBusyError",
    "HUMAN_RESOLVABLE_GATE_TYPES",
    "ManualIngestResult",
    "ManualObservationRow",
    "PageInspectionState",
    "ParsedAvailability",
    "PlaywrightBrowserDriver",
    "RawZoneCard",
    "ReadOnlyGuard",
    "ReadOnlyViolationError",
    "SafariAvailabilityCollector",
    "SelectorConfig",
    "aggregate_date_operating_status",
    "check_system_readiness",
    "discover_candidate_selectors",
    "extract_visible_text_from_html",
    "first_blocking_gate",
    "format_date_template",
    "generate_observation_csv_template",
    "ingest_manual_observations",
    "inspect_visible_gates",
    "load_selector_config",
    "normalize_zone_name",
    "parse_availability_text",
    "parse_capacity_text",
    "parse_observation_csv",
]
