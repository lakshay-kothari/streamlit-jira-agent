"""Unified data access: reads live Snowflake tables when a connection is
available (SiS deployment, or `st.secrets["connections"]["snowflake"]` locally),
otherwise the local SQLite database built by common/etl.py.

Note `get_strategic_initiatives()`: it is a *filter over programs*, not its own
table. That is the whole point of the portfolio model - a strategic initiative
is a program with `is_strategic` set, so the two can never disagree or double
count the same work.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from common import cortex
from common.config import (
    SQLITE_PATH,
    TABLE_BOARD_ITEMS,
    TABLE_DEMANDS,
    TABLE_ISSUES,
    TABLE_PROGRAMS,
    TABLE_PROGRAMS_META,
    TABLE_SNAPSHOTS,
    TABLE_WORK_ITEMS,
)

DATE_COLUMNS = {
    TABLE_ISSUES: ["created", "updated", "resolved", "due_date"],
    TABLE_DEMANDS: ["created", "go_live_date", "cancellation_date", "development_start_date",
                    "estimation_approval_date"],
    TABLE_BOARD_ITEMS: ["created", "updated", "eta", "went_live"],
    TABLE_WORK_ITEMS: ["created", "started", "due_date", "completed", "updated"],
    TABLE_PROGRAMS: ["start_date", "target_date"],
    TABLE_SNAPSHOTS: ["snapshot_date"],
}

BOOL_COLUMNS = {
    TABLE_PROGRAMS: ["is_strategic"],
    TABLE_WORK_ITEMS: ["is_leaf"],
}


def _read_sqlite_table(name: str) -> pd.DataFrame:
    if not SQLITE_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        return pd.read_sql(f"SELECT * FROM {name}", conn)
    except (pd.errors.DatabaseError, sqlite3.OperationalError):
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_table(name: str, database: str | None = None, schema: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame()
    if database and schema and cortex.cortex_available():
        try:
            df = cortex.run_sql(f"SELECT * FROM {database}.{schema}.{name.upper()}")
            df.columns = [c.lower() for c in df.columns]
        except Exception:
            df = pd.DataFrame()
    if df.empty:
        df = _read_sqlite_table(name)

    for col in DATE_COLUMNS.get(name, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    # SQLite has no boolean type, so a round-trip returns 0/1 integers.
    for col in BOOL_COLUMNS.get(name, []):
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(bool)
    return df


def _get(name: str) -> pd.DataFrame:
    from common.config import SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA

    return get_table(name, SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA)


def get_programs() -> pd.DataFrame:
    """The registry: every program, strategic or not."""
    return _get(TABLE_PROGRAMS)


def get_work_items() -> pd.DataFrame:
    """The cross-program spine - one normalized row per unit of work."""
    return _get(TABLE_WORK_ITEMS)


def get_issues() -> pd.DataFrame:
    return _get(TABLE_ISSUES)


def get_board_items() -> pd.DataFrame:
    return _get(TABLE_BOARD_ITEMS)


def get_demands() -> pd.DataFrame:
    return _get(TABLE_DEMANDS)


def get_snapshots() -> pd.DataFrame:
    return _get(TABLE_SNAPSHOTS)


def get_programs_meta() -> pd.DataFrame:
    return _get(TABLE_PROGRAMS_META)


def get_strategic_initiatives() -> pd.DataFrame:
    """Strategic initiatives are the `is_strategic` subset of programs - never a
    separate list. Filtering here (rather than reading another table) is what
    guarantees the initiative count can never exceed the program count."""
    programs = get_programs()
    if programs.empty or "is_strategic" not in programs.columns:
        return programs
    return programs[programs["is_strategic"]].reset_index(drop=True)


def data_source_label() -> str:
    return "Live Snowflake tables" if cortex.cortex_available() else "Local demo data (SQLite)"
