"""
Snowflake connectivity via `st.connection("snowflake")` + Cortex COMPLETE wrapper.

`st.connection("snowflake")` is Streamlit's official, unified Snowflake
connection: it transparently uses the active Snowpark session when running as
Streamlit-in-Snowflake, or falls back to credentials in
`st.secrets["connections"]["snowflake"]` locally - no manual mode-detection
needed (see the snowflake-connection reference in the developing-with-streamlit
skill). If neither is configured, every function here degrades gracefully so
the app stays fully usable in local demo mode.

All SQL is parameter-bound (never f-string interpolated) to avoid SQL
injection through free-text prompts typed by users in the chat page.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common.config import DEFAULT_CORTEX_MODEL


@st.cache_resource(show_spinner=False)
def _connection():
    try:
        return st.connection("snowflake")
    except Exception:
        return None


def run_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    conn = _connection()
    if conn is None:
        raise ConnectionError("No Snowflake connection available.")
    return conn.query(sql, params=params or {}, ttl=0)


@st.cache_resource(show_spinner=False)
def connection_status() -> dict:
    conn = _connection()
    if conn is None:
        return {"connected": False, "mode": "local demo (no Snowflake connection configured)"}
    try:
        conn.query("SELECT 1 AS OK", ttl=0)
        return {"connected": True, "mode": "Snowflake"}
    except Exception as exc:
        return {"connected": False, "mode": f"local demo (connection failed: {exc})"}


def cortex_available() -> bool:
    return connection_status()["connected"]


def cortex_complete(prompt: str, model: str = DEFAULT_CORTEX_MODEL) -> str | None:
    """Returns the model's text response, or None if no Snowflake connection is
    reachable (caller should fall back to a local summary in that case)."""
    if not cortex_available():
        return None
    try:
        df = run_sql(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(:model, :prompt) AS RESPONSE",
            {"model": model, "prompt": prompt},
        )
        return None if df.empty else str(df.iloc[0]["RESPONSE"])
    except Exception:
        return None
