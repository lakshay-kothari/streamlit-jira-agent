"""Milestone-shaped sources -> work_items.

Three of the tools in this portfolio do not track tickets at all. They track a
few dozen dated commitments, which is exactly what a program manager reports on:

* **Excel PM tracker** - milestones with a RAG flag and a typed % complete.
* **Weekly status report** - one row per workstream per reporting week.
* **Smartsheet plan** - an indented WBS with predecessors and roll-up rows.

They share a shape (a named, dated, owned commitment) so they share an adapter,
parameterized by column map and status vocabulary. That keeps the "one adapter
per tool" promise without three near-identical files.

Two things matter for metrics downstream. Roll-up/summary rows are marked
`is_leaf = False` so a parent and its children are never counted as separate
scope. And a typed "% Complete" is kept only as `reported_pct` on the detail
frame - never as the progress number shown on screen, which is always derived
from item status.
"""
from __future__ import annotations

import pandas as pd

from common.adapters.base import extract_numeric, finalize, read_csv_robust

# --------------------------------------------------------------- vocabularies ---
EXCEL_TRACKER_STATUS = {
    "Not Started": "To Do",
    "In Progress": "In Progress",
    "At Risk": "In Progress",
    "Blocked": "Blocked",
    "Complete": "Done",
    "Deferred": "Cancelled",
    "Descoped": "Cancelled",
}

STATUS_REPORT_STATUS = {
    "Not Started": "To Do",
    "In Progress": "In Progress",
    "Slipped": "Blocked",
    "Complete": "Done",
    "Dropped": "Cancelled",
}

SMARTSHEET_STATUS = {
    "Not Started": "To Do",
    "In Progress": "In Progress",
    "On Hold": "Blocked",
    "Complete": "Done",
    "Cancelled": "Cancelled",
}

TRACKWISE_STATUS = {
    "Draft": "To Do",
    "Under Review": "In Progress",
    "Approved": "In Progress",
    "Verification": "In Progress",
    "Awaiting QA Sign-off": "Blocked",
    "Closed": "Done",
    "Voided": "Cancelled",
}


class MilestoneSpec:
    """How one tool names the fields of the shared milestone shape."""

    def __init__(self, source_system, columns, statuses, item_type,
                 program_column="Program", summary_column=None):
        self.source_system = source_system
        self.columns = columns
        self.statuses = statuses
        self.item_type = item_type
        self.program_column = program_column
        self.summary_column = summary_column


EXCEL_TRACKER = MilestoneSpec(
    source_system="Excel PM Tracker",
    columns={"Milestone ID": "item_key", "Milestone": "title", "Workstream": "workstream",
             "Business Area": "domain", "Owner": "owner", "Status": "status_raw",
             "Baseline Finish": "due_date", "Actual Finish": "completed",
             "Baseline Start": "created", "Actual Start": "started",
             "Last Reviewed": "updated", "Effort (hrs)": "effort_hours",
             "% Complete": "reported_pct", "RAG": "rag"},
    statuses=EXCEL_TRACKER_STATUS,
    item_type="Milestone",
)

STATUS_REPORT = MilestoneSpec(
    source_system="Status Report",
    columns={"Ref": "item_key", "Deliverable": "title", "Workstream": "workstream",
             "Region": "domain", "Accountable": "owner", "Status": "status_raw",
             "Committed Date": "due_date", "Delivered Date": "completed",
             "Started": "created", "Report Week": "updated",
             "RAG": "rag", "Commentary": "commentary"},
    statuses=STATUS_REPORT_STATUS,
    item_type="Deliverable",
)

SMARTSHEET = MilestoneSpec(
    source_system="Smartsheet",
    columns={"Row ID": "item_key", "Task Name": "title", "Phase": "workstream",
             "Function": "domain", "Assigned To": "owner", "Status": "status_raw",
             "Finish": "due_date", "Completed On": "completed", "Start": "created",
             "Modified": "updated", "Duration (hrs)": "effort_hours",
             "% Complete": "reported_pct", "Predecessors": "predecessors",
             "Outline Level": "outline_level"},
    statuses=SMARTSHEET_STATUS,
    item_type="Task",
)

TRACKWISE = MilestoneSpec(
    source_system="TrackWise",
    columns={"Record ID": "item_key", "Title": "title", "Phase": "workstream",
             "Site": "domain", "Record Owner": "owner", "Record State": "status_raw",
             "Target Close": "due_date", "Actual Close": "completed",
             "Opened": "created", "Last Action": "updated",
             "Effort (hrs)": "effort_hours", "Gate": "gate"},
    statuses=TRACKWISE_STATUS,
    item_type="Quality Record",
)

DATE_FIELDS = ("created", "started", "due_date", "completed", "updated")


def _read(path) -> pd.DataFrame:
    if str(path).lower().endswith((".xlsx", ".xlsm")):
        return pd.read_excel(path, dtype="string")
    return read_csv_robust(path, dtype="string", keep_default_na=True, low_memory=False)


def parse(path, spec: MilestoneSpec, resolver=None):
    """Returns (work_items, detail)."""
    raw = _read(path)
    raw.columns = [str(c).strip() for c in raw.columns]

    detail = pd.DataFrame(index=raw.index)
    for source_col, dest_col in spec.columns.items():
        detail[dest_col] = raw.get(source_col)
    detail["program_name"] = raw.get(spec.program_column)

    for col in DATE_FIELDS:
        if col in detail.columns:
            detail[col] = pd.to_datetime(detail[col], errors="coerce")
    if "effort_hours" in detail.columns:
        detail["effort_hours"] = extract_numeric(detail["effort_hours"])
    if "reported_pct" in detail.columns:
        detail["reported_pct"] = pd.to_numeric(detail["reported_pct"], errors="coerce")

    detail["status_category"] = detail["status_raw"].map(spec.statuses)

    source_name = getattr(path, "name", str(path))
    detail["source_file"] = source_name
    if resolver is not None:
        detail["program_id"] = [resolver.by_name(n) for n in detail["program_name"]]
    else:
        detail["program_id"] = pd.NA

    # A Smartsheet plan carries summary rows (outline level 1) whose dates and
    # status merely roll up their children. Counting both would double the scope.
    if "outline_level" in detail.columns:
        level = pd.to_numeric(detail["outline_level"], errors="coerce")
        is_leaf = level >= level.max() if level.notna().any() else True
    else:
        is_leaf = True

    work = detail.copy()
    work["item_type"] = spec.item_type
    work["is_leaf"] = is_leaf
    return finalize(work, spec.source_system, source_name), detail
