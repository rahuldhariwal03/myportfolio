"""Modular database backend abstraction.

Uses SQLite by default for zero-cost local setup, while isolating connection
management, parameter styles, and dialect identifiers behind `DatabaseBackend`
so migrating to PostgreSQL or Supabase later only requires changing
`DATABASE_URL` and installing `psycopg[binary]`.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


class DatabaseBackend(ABC):
    """Abstract interface implemented by SQLite and PostgreSQL/Supabase adapters."""

    dialect: str
    database_url: str

    @abstractmethod
    @contextmanager
    def connection(self) -> Iterator[Any]:
        """Yield a database connection (commits at outermost boundary, rolls back on error)."""

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Group multiple repository operations inside a single atomic transaction."""
        with self.connection() as conn:
            yield conn

    @abstractmethod
    def execute_script(self, sql_script: str) -> None:
        """Execute a multi-statement DDL initialization script."""

    @abstractmethod
    def fetch_all(self, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Execute a SELECT query using `?` placeholders and return rows as dicts."""

    @abstractmethod
    def fetch_one(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        """Execute a SELECT query using `?` placeholders and return one dict or None."""

    @abstractmethod
    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        """Execute a write statement and return affected row count."""

    @abstractmethod
    def insert_returning_id(self, query: str, params: Sequence[Any] = ()) -> int:
        """Execute an INSERT statement and return the generated integer primary key."""


class SQLiteBackend(DatabaseBackend):
    """Local SQLite backend with foreign keys and WAL concurrency enabled."""

    dialect = "sqlite"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        if database_url == "sqlite:///:memory:":
            self.db_path_str = ":memory:"
            self._shared_memory_conn: sqlite3.Connection | None = self._open_raw_connection()
        elif database_url.startswith("sqlite:///"):
            file_path = Path(database_url[len("sqlite:///") :])
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path_str = str(file_path)
            self._shared_memory_conn = None
        else:
            raise ValueError(f"Invalid SQLite DATABASE_URL: {database_url!r}")

        self._active_conn: sqlite3.Connection | None = None
        self._tx_depth: int = 0

    def _open_raw_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path_str, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path_str != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @property
    def file_path(self) -> Path | None:
        if self.db_path_str == ":memory:":
            return None
        return Path(self.db_path_str)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self._shared_memory_conn is not None:
            conn = self._shared_memory_conn
            self._tx_depth += 1
            try:
                yield conn
                if self._tx_depth == 1:
                    conn.commit()
            except Exception:
                if self._tx_depth == 1:
                    conn.rollback()
                raise
            finally:
                self._tx_depth -= 1
            return

        if self._active_conn is not None:
            self._tx_depth += 1
            try:
                yield self._active_conn
            finally:
                self._tx_depth -= 1
            return

        conn = self._open_raw_connection()
        self._active_conn = conn
        self._tx_depth = 1
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._tx_depth = 0
            self._active_conn = None
            conn.close()

    def execute_script(self, sql_script: str) -> None:
        with self.connection() as conn:
            conn.executescript(sql_script)
            conn.execute("PRAGMA foreign_keys = ON;")

    def fetch_all(self, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def fetch_one(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.connection() as conn:
            cur = conn.execute(query, tuple(params))
            row = cur.fetchone()
            return dict(row) if row is not None else None

    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        with self.connection() as conn:
            cur = conn.execute(query, tuple(params))
            return cur.rowcount

    def insert_returning_id(self, query: str, params: Sequence[Any] = ()) -> int:
        with self.connection() as conn:
            cur = conn.execute(query, tuple(params))
            if cur.lastrowid is None:
                raise RuntimeError("INSERT did not return a primary key ID")
            return int(cur.lastrowid)

    def close(self) -> None:
        if self._shared_memory_conn is not None:
            self._shared_memory_conn.close()
            self._shared_memory_conn = None


class PostgresBackend(DatabaseBackend):
    """PostgreSQL / Supabase backend adapter (activated when DATABASE_URL is postgresql://).

    Translates standard `?` parameter markers to `%s` and uses `RETURNING id`
    so higher-level repository queries stay portable across SQLite and Postgres.
    Requires `pip install psycopg[binary]`.
    """

    dialect = "postgresql"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        try:
            import psycopg  # type: ignore[import-not-found]
            from psycopg.rows import dict_row  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL/Supabase backend requires psycopg. "
                "Install it with: pip install 'psycopg[binary]>=3.2.0'"
            ) from exc
        self._psycopg = psycopg
        self._dict_row = dict_row

    @staticmethod
    def _translate_placeholders(query: str) -> str:
        return query.replace("?", "%s")

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = self._psycopg.connect(self.database_url, row_factory=self._dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute_script(self, sql_script: str) -> None:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_script)

    def fetch_all(self, query: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(self._translate_placeholders(query), tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def fetch_one(self, query: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(self._translate_placeholders(query), tuple(params))
                row = cur.fetchone()
                return dict(row) if row is not None else None

    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(self._translate_placeholders(query), tuple(params))
                return cur.rowcount

    def insert_returning_id(self, query: str, params: Sequence[Any] = ()) -> int:
        pg_query = self._translate_placeholders(query).rstrip().rstrip(";") + " RETURNING id;"
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(pg_query, tuple(params))
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("INSERT RETURNING id returned no row")
                return int(row["id"])


def create_backend(database_url: str) -> DatabaseBackend:
    """Factory returning the matching backend for `database_url`."""
    cleaned = database_url.strip()
    if cleaned.startswith("sqlite:///"):
        return SQLiteBackend(cleaned)
    if cleaned.startswith(("postgresql://", "postgres://")):
        return PostgresBackend(cleaned)
    raise ValueError(
        f"Unsupported DATABASE_URL scheme: {cleaned!r}. "
        "Expected 'sqlite:///...' or 'postgresql://...'."
    )
