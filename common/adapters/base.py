"""The one contract every source adapter maps onto.

Each program in this portfolio arrives from a different tool - Jira, ServiceNow,
an Excel PM tracker, a validated-system export, a weekly status report - with its
own columns and its own vocabulary for "done". An adapter's whole job is to turn
one of those shapes into `WORK_ITEM_COLUMNS` rows so that every metric in
common/kpi.py can be computed once, over one table, regardless of origin.

Adding a program on a new tool means writing one adapter here. It means changing
nothing in kpi.py, charts.py, or any page.
"""
from __future__ import annotations

import re

import pandas as pd

# --------------------------------------------------------------- contract ---
WORK_ITEM_COLUMNS = [
    "program_id",       # FK into the programs registry
    "item_key",         # stable id within its source
    "title",
    "item_type",        # Story / Task / Milestone / Ticket / ...
    "workstream",       # epic, phase, or WBS parent - the mid-level grouping
    "domain",           # business domain this work serves
    "owner",
    "status_raw",       # the source system's own word, kept for drill-downs
    "status_category",  # normalized - see STATUS_CATEGORIES
    "priority",
    "created",
    "started",
    "due_date",
    "completed",
    "updated",
    "effort_hours",
    "is_leaf",          # False for parents (epics/initiatives) so roll-ups don't double count
    "source_system",
    "source_file",
]

DATE_FIELDS = ["created", "started", "due_date", "completed", "updated"]

# ---------------------------------------------------------------- statuses ---
# Blocked and Cancelled are first-class here on purpose. Folding "Blocked" into
# In Progress hides the most actionable state in the dataset, and folding
# "Descoped"/"Won't Do" into Done inflates every completion percentage by
# counting abandoned work as delivered.
STATUS_CATEGORIES = ["To Do", "In Progress", "Blocked", "Done", "Cancelled", "Unknown"]

#: Used when a source simply did not record a status. Distinct from "To Do":
#: 146 of 149 agents on the real board had a blank Status, and backfilling that
#: to "Not Started" reported missing data as a deliberate decision.
UNKNOWN_CATEGORY = "Unknown"

#: Categories that represent work no longer in flight but never delivered.
CANCELLED_CATEGORY = "Cancelled"
#: Categories that count as delivered.
DONE_CATEGORY = "Done"
#: Categories still consuming capacity.
OPEN_CATEGORIES = ["To Do", "In Progress", "Blocked"]

# Matched case-insensitively against a source's own status string, most specific
# first. Anything unmatched falls back to the source's own status *category*
# column when it has one, else "To Do".
_STATUS_PATTERNS: list[tuple[str, str]] = [
    (r"^(?:descoped|de-scoped|cancell?ed|won'?t do|withdrawn|rejected|abandoned|dropped|duplicate)", "Cancelled"),
    (r"^(?:blocked|on[- ]?hold|on hold|impediment|waiting on vendor|stalled)", "Blocked"),
    (r"(?:deployment completed|deployed|closed|complete|completed|done|live|released|resolved|signed[- ]off)", "Done"),
    (r"(?:in progress|in-progress|development|\bwip\b|build|executing|\bsit\b|\buat\b|testing|review|analysis|hypercare|scoping|ready for)", "In Progress"),
    (r"^(?:new|to do|todo|open|backlog|not started|triage|planned|queued|draft|idea|proposed|concept|candidate|requested|intake)", "To Do"),
]


def normalize_status(raw: pd.Series, fallback: pd.Series | None = None) -> pd.Series:
    """Map a source system's status vocabulary onto STATUS_CATEGORIES.

    `fallback` is an optional per-row default (e.g. Jira's own Status Category)
    used where no pattern matches, so a source that already carries a sane
    category isn't thrown away just because its status wording is unusual.
    """
    s = raw.astype("string").str.strip()
    out = pd.Series(pd.NA, index=s.index, dtype="object")
    lowered = s.str.lower()
    for pattern, category in _STATUS_PATTERNS:
        hit = out.isna() & lowered.str.contains(pattern, regex=True, na=False)
        out.loc[hit] = category
    if fallback is not None:
        fb = fallback.astype("string").str.strip()
        # A fallback of "Done" must not resurrect work the patterns called Cancelled.
        out = out.where(out.notna(), fb.where(fb.isin(STATUS_CATEGORIES)))
    # A blank status stays unknown rather than being guessed into a bucket.
    out = out.where(s.notna() & (s.str.len() > 0), pd.NA)
    return out.astype("object")


def empty_work_items() -> pd.DataFrame:
    """A correctly-typed empty frame, so callers can concat unconditionally."""
    return pd.DataFrame({c: pd.Series(dtype="object") for c in WORK_ITEM_COLUMNS})


def finalize(df: pd.DataFrame, source_system: str, source_file: str) -> pd.DataFrame:
    """Every adapter's last line. Fills in any column it didn't set, coerces the
    date fields, and returns the columns in contract order - so a partial
    adapter (a status report with no work items, say) is still a valid citizen."""
    out = df.copy()
    out["source_system"] = source_system
    out["source_file"] = source_file
    for col in WORK_ITEM_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    for col in DATE_FIELDS:
        out[col] = pd.to_datetime(out[col], errors="coerce")
    if out["is_leaf"].isna().all():
        out["is_leaf"] = True
    out["is_leaf"] = out["is_leaf"].fillna(True).astype(bool)
    out["status_category"] = out["status_category"].fillna(UNKNOWN_CATEGORY)
    return out[WORK_ITEM_COLUMNS]


def slugify(value: str) -> str:
    """Program display name -> program_id. Stable and reversible enough that a
    registry row can be matched by name when an explicit id isn't supplied."""
    text = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower())
    return text.strip("-") or "unknown"


# ------------------------------------------------------- shared CSV helpers ---
# These live here (rather than in etl.py) because every adapter needs them and
# etl.py imports the adapters, not the other way round.
JIRA_DATE_FORMAT = "%d/%b/%y %I:%M %p"


def read_csv_robust(path, **kwargs) -> pd.DataFrame:
    """Exports from Excel/Jira often mix Windows-1252 bytes (curly quotes, em
    dashes) into an otherwise UTF-8 file. Try UTF-8, fall back to cp1252, so a
    stray smart-quote never hard-crashes ingestion."""
    try:
        return pd.read_csv(path, encoding="utf-8-sig", **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp1252", **kwargs)


def coalesce_group(df: pd.DataFrame, base_name: str) -> pd.Series:
    """Collapse `name`, `name.1`, `name.2`, ... into one Series holding the
    first non-blank value per row. Jira's CSV export repeats a header once per
    multi-value occurrence, which pandas de-dupes by suffixing."""
    pattern = re.compile(rf"^{re.escape(base_name)}(\.\d+)?$")
    cols = [c for c in df.columns if pattern.match(c)]
    if not cols:
        return pd.Series([pd.NA] * len(df), index=df.index)
    sub = df[cols].replace(r"^\s*$", pd.NA, regex=True)
    return sub.bfill(axis=1).iloc[:, 0]


def coalesce_candidates(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """Like coalesce_group but across several *different* base field names,
    taking whichever is populated first, in priority order."""
    result = pd.Series([pd.NA] * len(df), index=df.index)
    for name in candidates:
        result = result.where(result.notna(), coalesce_group(df, name))
    return result


def parse_jira_datetime(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    parsed = pd.to_datetime(s, format=JIRA_DATE_FORMAT, errors="coerce")
    remaining = parsed.isna() & s.notna() & (s != "")
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(s[remaining], errors="coerce")
    return parsed


def extract_numeric(series: pd.Series) -> pd.Series:
    """Best-effort numeric extraction from messy free-text estimate fields like
    '700 Hrs', '$30000 fixed bid', '24K', '58500$'. First number wins; a
    trailing K means *1000. Unparseable text -> NaN, never an exception."""
    s = series.astype("string").str.strip()
    match = s.str.extract(r"(?i)(\d[\d,]*\.?\d*)\s*(k)?")
    numbers = pd.to_numeric(match[0].str.replace(",", "", regex=False), errors="coerce")
    return numbers.where(~match[1].notna(), numbers * 1000)
