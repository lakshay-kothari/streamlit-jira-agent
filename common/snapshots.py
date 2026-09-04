"""Historical values, so a metric can carry a trend instead of floating free.

Two mechanisms, and the distinction matters for honesty:

**Rewind** - `created` and `completed` are recorded per item, so the state of the
portfolio at any past date is *derivable*. Completion percentage, throughput and
open backlog can therefore be shown as real history from day one, for the real
program as well as the generated ones. Nothing is invented.

**Snapshot** - some things cannot be rewound. Nothing in the data says whether an
item was blocked last Tuesday, only that it is blocked now. Those metrics get a
row appended per build, and their delta is simply unavailable until a second
build exists. The UI shows an em dash rather than a made-up arrow.

A metric that cannot honestly show a trend shows no trend.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from common.config import SQLITE_PATH, TABLE_SNAPSHOTS

#: Metrics whose past values are recoverable from the item dates themselves.
REWINDABLE = {"pct_complete", "throughput", "open_items", "completed_items", "created_items"}


def rewind(work_items: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """The work items as they stood on `as_of`.

    An item created after that date did not exist; an item completed after it
    was still open. Status categories that cannot be rewound (Blocked vs In
    Progress) collapse to "In Progress", which is why blocked counts are
    snapshot-based rather than rewound.
    """
    if work_items.empty:
        return work_items
    df = work_items[work_items["created"].notna() & (work_items["created"] <= as_of)].copy()
    if df.empty:
        return df
    finished = df["completed"].notna() & (df["completed"] <= as_of)
    df["status_category"] = df["status_category"].where(
        finished, df["status_category"].map(lambda c: c if c in ("Cancelled",) else "In Progress"))
    df.loc[~finished & (df["status_category"] == "Cancelled"), "status_category"] = "In Progress"
    df["completed"] = df["completed"].where(finished)
    return df


def weekly_history(work_items: pd.DataFrame, weeks: int = 26,
                   as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per week: created-to-date, completed-to-date, open, % complete.

    This is the series behind every trend line and every "vs N weeks ago"
    delta - all of it derived, none of it stored.
    """
    columns = ["week", "created_to_date", "completed_to_date", "open_items",
               "pct_complete", "completed_in_week"]
    if work_items.empty or work_items["created"].isna().all():
        return pd.DataFrame(columns=columns)

    end = (as_of or pd.Timestamp.now()).normalize()
    start = end - pd.Timedelta(weeks=weeks)
    marks = pd.date_range(start=start, end=end, freq="W-MON")
    if len(marks) == 0:
        return pd.DataFrame(columns=columns)

    created = work_items["created"]
    completed = work_items["completed"]
    cancelled = work_items["status_category"] == "Cancelled"

    rows = []
    previous_completed = None
    for mark in marks:
        created_to_date = int((created <= mark).sum())
        completed_to_date = int((completed.notna() & (completed <= mark) & ~cancelled).sum())
        cancelled_to_date = int((completed.notna() & (completed <= mark) & cancelled).sum())
        # Cancelled work is removed from the denominator, never counted as done.
        denominator = created_to_date - cancelled_to_date
        rows.append({
            "week": mark,
            "created_to_date": created_to_date,
            "completed_to_date": completed_to_date,
            "open_items": max(created_to_date - completed_to_date - cancelled_to_date, 0),
            "pct_complete": round(100 * completed_to_date / denominator, 1) if denominator else 0.0,
            "completed_in_week": (completed_to_date - previous_completed
                                  if previous_completed is not None else 0),
        })
        previous_completed = completed_to_date
    return pd.DataFrame(rows)


def value_weeks_ago(history: pd.DataFrame, column: str, weeks: int = 4):
    """The value of `column` roughly `weeks` ago, or None when the series does
    not reach back that far - which is a real answer, not a zero."""
    if history.empty or column not in history.columns or len(history) <= weeks:
        return None
    return history.iloc[-(weeks + 1)][column]


def throughput(work_items: pd.DataFrame, days: int = 28,
               as_of: pd.Timestamp | None = None) -> float:
    """Items genuinely delivered per week over the trailing window. Cancelled
    work is excluded - abandoning scope is not throughput."""
    if work_items.empty:
        return 0.0
    end = as_of or pd.Timestamp.now()
    window_start = end - pd.Timedelta(days=days)
    delivered = work_items[
        (work_items["status_category"] == "Done")
        & work_items["completed"].notna()
        & (work_items["completed"] > window_start)
        & (work_items["completed"] <= end)
    ]
    return round(len(delivered) / (days / 7.0), 1)


# --------------------------------------------------------------- persistence ---
SNAPSHOT_COLUMNS = ["snapshot_date", "program_id", "metric_key", "value"]


def append(rows: pd.DataFrame, db_path: Path = SQLITE_PATH) -> int:
    """Append today's values for the metrics that cannot be rewound. Re-running
    a build on the same day replaces that day rather than duplicating it."""
    if rows.empty:
        return 0
    rows = rows[SNAPSHOT_COLUMNS].copy()
    rows["snapshot_date"] = pd.to_datetime(rows["snapshot_date"]).dt.strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    try:
        try:
            existing = pd.read_sql(f"SELECT * FROM {TABLE_SNAPSHOTS}", conn)
        except (pd.errors.DatabaseError, sqlite3.OperationalError):
            existing = pd.DataFrame(columns=SNAPSHOT_COLUMNS)
        today = rows["snapshot_date"].iloc[0]
        if not existing.empty:
            existing = existing[existing["snapshot_date"] != today]
        combined = pd.concat([existing, rows], ignore_index=True)
        combined.to_sql(TABLE_SNAPSHOTS, conn, if_exists="replace", index=False)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def previous_value(snapshots: pd.DataFrame, program_id: str, metric_key: str, days: int = 7):
    """The most recent stored value at least `days` old, or None when there is
    no history yet."""
    if snapshots.empty:
        return None
    match = snapshots[(snapshots["program_id"] == program_id)
                      & (snapshots["metric_key"] == metric_key)]
    if match.empty:
        return None
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
    older = match[pd.to_datetime(match["snapshot_date"]) <= cutoff]
    if older.empty:
        return None
    return float(older.sort_values("snapshot_date").iloc[-1]["value"])
