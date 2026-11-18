"""Database schema, constraints, indexes, immutability triggers, and official zones.

Contains both SQLite DDL (default) and PostgreSQL/Supabase-compatible DDL so the
project can migrate cleanly as historical snapshot volume grows.
"""

from __future__ import annotations

from src.database.backend import DatabaseBackend

# Official zones verified during Phase 1 inspection of https://corbettgov.org/
# and https://safari.corbettgov.org/.
# Note: Only `DhikalaZone` was directly confirmed in an official portal redirect
# (`booking.corbettgov.org/canter -> safari.corbettgov.org/?eventName=DhikalaZone`).
# All other `source_zone_identifier` values remain NULL until verified post-gate.
OFFICIAL_CORBETT_ZONES: tuple[dict[str, str | None], ...] = (
    {
        "zone_name": "Bijrani",
        "source_zone_identifier": None,
        "entry_gate": "Amdanda",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "15 Oct - 30 June",
    },
    {
        "zone_name": "Jhirna",
        "source_zone_identifier": None,
        "entry_gate": "Dhela",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "Throughout year",
    },
    {
        "zone_name": "Dhela",
        "source_zone_identifier": None,
        "entry_gate": "Dhela",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "Throughout year",
    },
    {
        "zone_name": "Garjia",
        "source_zone_identifier": None,
        "entry_gate": "Garjiya",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "15 Oct - 30 June (year-round weather permitting)",
    },
    {
        "zone_name": "Durgadevi",
        "source_zone_identifier": None,
        "entry_gate": "Durgadevi",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "15 Nov - 15 June",
    },
    {
        "zone_name": "Sonanadi",
        "source_zone_identifier": None,
        "entry_gate": "Vatanvasa",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "15 Nov - 15 June",
    },
    {
        "zone_name": "Pakhro",
        "source_zone_identifier": None,
        "entry_gate": "Pakhro",
        "safari_mode": "jeep_permit",
        "unit_label": "Jeep permits",
        "operating_season": "15 Nov - 15 June",
    },
    {
        "zone_name": "Dhikala",
        "source_zone_identifier": "DhikalaZone",
        "entry_gate": "Dhangari",
        "safari_mode": "canter_seat",
        "unit_label": "Canter seats",
        "operating_season": "15 Nov - 15 June",
    },
)

SQLITE_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS collection_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    collection_type   TEXT NOT NULL CHECK (
        collection_type IN ('morning', 'evening', 'manual', 'demo_morning', 'demo_evening', 'demo_manual')
    ),
    date_window_start TEXT NOT NULL,
    date_window_end   TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'partial', 'blocked', 'failed', 'interrupted')
    ),
    error_summary     TEXT,
    is_demo           INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    source_url        TEXT
);

CREATE TABLE IF NOT EXISTS safari_dates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    safari_date      TEXT NOT NULL UNIQUE,
    weekday          TEXT NOT NULL,
    is_weekend       INTEGER NOT NULL CHECK (is_weekend IN (0, 1)),
    operating_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        operating_status IN ('open', 'partial', 'closed', 'window_not_open', 'paused', 'unknown')
    ),
    last_observed_at TEXT
);

CREATE TABLE IF NOT EXISTS zones (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_name              TEXT NOT NULL UNIQUE,
    source_zone_identifier TEXT UNIQUE,
    entry_gate             TEXT,
    safari_mode            TEXT NOT NULL DEFAULT 'jeep_permit' CHECK (
        safari_mode IN ('jeep_permit', 'canter_seat', 'unknown')
    ),
    unit_label             TEXT NOT NULL DEFAULT 'Jeep permits',
    operating_season       TEXT,
    is_active              INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS availability_snapshots (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_run_id     INTEGER NOT NULL REFERENCES collection_runs(id),
    safari_date           TEXT NOT NULL REFERENCES safari_dates(safari_date),
    zone_id               INTEGER NOT NULL REFERENCES zones(id),
    session               TEXT NOT NULL CHECK (session IN ('morning', 'afternoon')),
    available_slots       INTEGER CHECK (available_slots IS NULL OR available_slots >= 0),
    total_capacity        INTEGER CHECK (total_capacity IS NULL OR total_capacity > 0),
    raw_displayed_value   TEXT,
    raw_capacity_value    TEXT,
    collection_status     TEXT NOT NULL CHECK (
        collection_status IN (
            'success',
            'zone_closed',
            'window_not_open',
            'portal_paused',
            'blocked',
            'missing',
            'parse_error',
            'error'
        )
    ),
    confidence            TEXT NOT NULL CHECK (
        confidence IN ('verified', 'unverified', 'low', 'not_applicable')
    ),
    source_section        TEXT,
    error_details         TEXT,
    date_operating_status TEXT,
    captured_at           TEXT NOT NULL,
    CHECK (
        total_capacity IS NULL
        OR available_slots IS NULL
        OR available_slots <= total_capacity
    ),
    UNIQUE (collection_run_id, safari_date, zone_id, session)
);

CREATE TABLE IF NOT EXISTS change_events (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_run_id      INTEGER NOT NULL REFERENCES collection_runs(id),
    previous_snapshot_id   INTEGER NOT NULL REFERENCES availability_snapshots(id),
    current_snapshot_id    INTEGER NOT NULL UNIQUE REFERENCES availability_snapshots(id),
    safari_date            TEXT NOT NULL REFERENCES safari_dates(safari_date),
    zone_id                INTEGER NOT NULL REFERENCES zones(id),
    session                TEXT NOT NULL CHECK (session IN ('morning', 'afternoon')),
    previous_available     INTEGER NOT NULL CHECK (previous_available >= 0),
    current_available      INTEGER NOT NULL CHECK (current_available >= 0),
    change_amount          INTEGER NOT NULL,
    availability_reduction INTEGER NOT NULL CHECK (availability_reduction >= 0),
    availability_increase  INTEGER NOT NULL CHECK (availability_increase >= 0),
    previous_capacity      INTEGER CHECK (previous_capacity IS NULL OR previous_capacity > 0),
    current_capacity       INTEGER CHECK (current_capacity IS NULL OR current_capacity > 0),
    capacity_occupied_pct  REAL CHECK (
        capacity_occupied_pct IS NULL
        OR (capacity_occupied_pct >= 0.0 AND capacity_occupied_pct <= 100.0)
    ),
    change_type            TEXT NOT NULL CHECK (
        change_type IN (
            'reduction',
            'increase',
            'no_change',
            'capacity_changed_reduction',
            'capacity_changed_increase',
            'capacity_changed_no_slot_delta'
        )
    ),
    previous_captured_at   TEXT NOT NULL,
    observed_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_run_id INTEGER NOT NULL REFERENCES collection_runs(id),
    page_or_zone      TEXT NOT NULL,
    status            TEXT NOT NULL,
    error_message     TEXT,
    screenshot_path   TEXT,
    logged_at         TEXT NOT NULL
);

-- Indexes optimised for snapshot lookup, change calculations, trends & future read-only API
CREATE INDEX IF NOT EXISTS idx_runs_status_started
    ON collection_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_safari_dates_date
    ON safari_dates (safari_date);

CREATE INDEX IF NOT EXISTS idx_snapshots_series_lookup
    ON availability_snapshots (safari_date, zone_id, session, captured_at, id);

CREATE INDEX IF NOT EXISTS idx_snapshots_run
    ON availability_snapshots (collection_run_id);

CREATE INDEX IF NOT EXISTS idx_snapshots_captured
    ON availability_snapshots (captured_at);

CREATE INDEX IF NOT EXISTS idx_changes_observed
    ON change_events (observed_at, safari_date, zone_id, session);

CREATE INDEX IF NOT EXISTS idx_changes_safari_date_zone
    ON change_events (safari_date, zone_id, session);

CREATE INDEX IF NOT EXISTS idx_logs_run
    ON collection_logs (collection_run_id, logged_at);

-- Immutability triggers: historical snapshots and change events MUST NEVER be overwritten or deleted
CREATE TRIGGER IF NOT EXISTS trg_availability_snapshots_no_update
BEFORE UPDATE ON availability_snapshots
BEGIN
    SELECT RAISE(ABORT, 'Historical availability_snapshots are immutable and cannot be updated');
END;

CREATE TRIGGER IF NOT EXISTS trg_availability_snapshots_no_delete
BEFORE DELETE ON availability_snapshots
BEGIN
    SELECT RAISE(ABORT, 'Historical availability_snapshots are immutable and cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_change_events_no_update
BEFORE UPDATE ON change_events
BEGIN
    SELECT RAISE(ABORT, 'Historical change_events are immutable and cannot be updated');
END;

CREATE TRIGGER IF NOT EXISTS trg_change_events_no_delete
BEFORE DELETE ON change_events
BEGIN
    SELECT RAISE(ABORT, 'Historical change_events are immutable and cannot be deleted');
END;
"""

POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS collection_runs (
    id                BIGSERIAL PRIMARY KEY,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    collection_type   TEXT NOT NULL CHECK (
        collection_type IN ('morning', 'evening', 'manual', 'demo_morning', 'demo_evening', 'demo_manual')
    ),
    date_window_start TEXT NOT NULL,
    date_window_end   TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (
        status IN ('running', 'completed', 'partial', 'blocked', 'failed', 'interrupted')
    ),
    error_summary     TEXT,
    is_demo           INTEGER NOT NULL DEFAULT 0 CHECK (is_demo IN (0, 1)),
    source_url        TEXT
);

CREATE TABLE IF NOT EXISTS safari_dates (
    id               BIGSERIAL PRIMARY KEY,
    safari_date      TEXT NOT NULL UNIQUE,
    weekday          TEXT NOT NULL,
    is_weekend       INTEGER NOT NULL CHECK (is_weekend IN (0, 1)),
    operating_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        operating_status IN ('open', 'partial', 'closed', 'window_not_open', 'paused', 'unknown')
    ),
    last_observed_at TEXT
);

CREATE TABLE IF NOT EXISTS zones (
    id                     BIGSERIAL PRIMARY KEY,
    zone_name              TEXT NOT NULL UNIQUE,
    source_zone_identifier TEXT UNIQUE,
    entry_gate             TEXT,
    safari_mode            TEXT NOT NULL DEFAULT 'jeep_permit' CHECK (
        safari_mode IN ('jeep_permit', 'canter_seat', 'unknown')
    ),
    unit_label             TEXT NOT NULL DEFAULT 'Jeep permits',
    operating_season       TEXT,
    is_active              INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS availability_snapshots (
    id                    BIGSERIAL PRIMARY KEY,
    collection_run_id     BIGINT NOT NULL REFERENCES collection_runs(id),
    safari_date           TEXT NOT NULL REFERENCES safari_dates(safari_date),
    zone_id               BIGINT NOT NULL REFERENCES zones(id),
    session               TEXT NOT NULL CHECK (session IN ('morning', 'afternoon')),
    available_slots       INTEGER CHECK (available_slots IS NULL OR available_slots >= 0),
    total_capacity        INTEGER CHECK (total_capacity IS NULL OR total_capacity > 0),
    raw_displayed_value   TEXT,
    raw_capacity_value    TEXT,
    collection_status     TEXT NOT NULL CHECK (
        collection_status IN (
            'success', 'zone_closed', 'window_not_open', 'portal_paused',
            'blocked', 'missing', 'parse_error', 'error'
        )
    ),
    confidence            TEXT NOT NULL CHECK (
        confidence IN ('verified', 'unverified', 'low', 'not_applicable')
    ),
    source_section        TEXT,
    error_details         TEXT,
    date_operating_status TEXT,
    captured_at           TEXT NOT NULL,
    CHECK (
        total_capacity IS NULL
        OR available_slots IS NULL
        OR available_slots <= total_capacity
    ),
    UNIQUE (collection_run_id, safari_date, zone_id, session)
);

CREATE TABLE IF NOT EXISTS change_events (
    id                     BIGSERIAL PRIMARY KEY,
    collection_run_id      BIGINT NOT NULL REFERENCES collection_runs(id),
    previous_snapshot_id   BIGINT NOT NULL REFERENCES availability_snapshots(id),
    current_snapshot_id    BIGINT NOT NULL UNIQUE REFERENCES availability_snapshots(id),
    safari_date            TEXT NOT NULL REFERENCES safari_dates(safari_date),
    zone_id                BIGINT NOT NULL REFERENCES zones(id),
    session                TEXT NOT NULL CHECK (session IN ('morning', 'afternoon')),
    previous_available     INTEGER NOT NULL CHECK (previous_available >= 0),
    current_available      INTEGER NOT NULL CHECK (current_available >= 0),
    change_amount          INTEGER NOT NULL,
    availability_reduction INTEGER NOT NULL CHECK (availability_reduction >= 0),
    availability_increase  INTEGER NOT NULL CHECK (availability_increase >= 0),
    previous_capacity      INTEGER CHECK (previous_capacity IS NULL OR previous_capacity > 0),
    current_capacity       INTEGER CHECK (current_capacity IS NULL OR current_capacity > 0),
    capacity_occupied_pct  DOUBLE PRECISION CHECK (
        capacity_occupied_pct IS NULL
        OR (capacity_occupied_pct >= 0.0 AND capacity_occupied_pct <= 100.0)
    ),
    change_type            TEXT NOT NULL,
    previous_captured_at   TEXT NOT NULL,
    observed_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_logs (
    id                BIGSERIAL PRIMARY KEY,
    collection_run_id BIGINT NOT NULL REFERENCES collection_runs(id),
    page_or_zone      TEXT NOT NULL,
    status            TEXT NOT NULL,
    error_message     TEXT,
    screenshot_path   TEXT,
    logged_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_status_started ON collection_runs (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_series_lookup ON availability_snapshots (safari_date, zone_id, session, captured_at, id);
CREATE INDEX IF NOT EXISTS idx_snapshots_run ON availability_snapshots (collection_run_id);
CREATE INDEX IF NOT EXISTS idx_changes_observed ON change_events (observed_at, safari_date, zone_id, session);
CREATE INDEX IF NOT EXISTS idx_logs_run ON collection_logs (collection_run_id, logged_at);
"""


def initialize_schema(backend: DatabaseBackend, seed_official_zones: bool = True) -> None:
    """Create all tables, constraints, indexes, triggers, and optional reference zones."""
    if backend.dialect == "sqlite":
        backend.execute_script(SQLITE_SCHEMA_SQL)
    elif backend.dialect == "postgresql":
        backend.execute_script(POSTGRES_SCHEMA_SQL)
    else:
        raise ValueError(f"Unsupported backend dialect: {backend.dialect!r}")

    if seed_official_zones:
        seed_zones(backend)


def seed_zones(backend: DatabaseBackend) -> int:
    """Idempotently register the 8 official Corbett Tiger Reserve safari zones."""
    inserted = 0
    for zone in OFFICIAL_CORBETT_ZONES:
        existing = backend.fetch_one(
            "SELECT id FROM zones WHERE zone_name = ?",
            (zone["zone_name"],),
        )
        if existing is None:
            backend.insert_returning_id(
                """
                INSERT INTO zones (
                    zone_name, source_zone_identifier, entry_gate,
                    safari_mode, unit_label, operating_season, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    zone["zone_name"],
                    zone["source_zone_identifier"],
                    zone["entry_gate"],
                    zone["safari_mode"],
                    zone["unit_label"],
                    zone["operating_season"],
                ),
            )
            inserted += 1
    return inserted
