"""ServiceNow ticket export -> work_items.

Ticket-shaped delivery: no epics, no story points, a `sys_id` key, and a state
vocabulary of its own. Several programs can share one export, so the program is
resolved per row from the assignment group rather than from the filename.
"""
from __future__ import annotations

import pandas as pd

from common.adapters.base import extract_numeric, finalize, read_csv_robust

SOURCE_SYSTEM = "ServiceNow"

#: ServiceNow states mapped onto the shared taxonomy. "Pending Vendor" and
#: "Pending Customer" are Blocked, not In Progress: the ticket is holding a slot
#: while waiting on somebody outside the team, which is the thing a manager
#: needs to see rather than have averaged into general work-in-progress.
STATE_CATEGORY = {
    "New": "To Do",
    "Assigned": "To Do",
    "Work in Progress": "In Progress",
    "In Review": "In Progress",
    "Pending Vendor": "Blocked",
    "Pending Customer": "Blocked",
    "On Hold": "Blocked",
    "Resolved": "Done",
    "Closed Complete": "Done",
    "Closed Incomplete": "Cancelled",
    "Cancelled": "Cancelled",
}

COLUMN_MAP = {
    "sys_id": "item_key",
    "short_description": "title",
    "u_program": "program_name",
    "u_workstream": "workstream",
    "u_business_area": "domain",
    "assigned_to": "owner",
    "u_state": "status_raw",
    "priority": "priority",
    "opened_at": "created",
    "work_start": "started",
    "due_date": "due_date",
    "closed_at": "completed",
    "sys_updated_on": "updated",
    "u_effort_hours": "effort_hours",
    "assignment_group": "assignment_group",
}


def parse(path, resolver=None):
    """Returns (work_items, detail). `resolver` maps each row's assignment
    group to a program; without one every row lands unattached."""
    raw = read_csv_robust(path, dtype="string", keep_default_na=True, low_memory=False)
    raw.columns = [str(c).strip() for c in raw.columns]

    detail = pd.DataFrame(index=raw.index)
    for source_col, dest_col in COLUMN_MAP.items():
        detail[dest_col] = raw.get(source_col)

    for col in ("created", "started", "due_date", "completed", "updated"):
        detail[col] = pd.to_datetime(detail[col], errors="coerce")
    detail["effort_hours"] = extract_numeric(detail["effort_hours"])
    detail["status_category"] = detail["status_raw"].map(STATE_CATEGORY)

    source_name = getattr(path, "name", str(path))
    detail["source_file"] = source_name
    if resolver is not None:
        detail["program_id"] = resolver.by_assignment_group(detail["assignment_group"]).values
    else:
        detail["program_id"] = pd.NA

    work = detail.drop(columns=["assignment_group", "program_name"], errors="ignore").copy()
    work["item_type"] = "Ticket"
    work["is_leaf"] = True
    return finalize(work, SOURCE_SYSTEM, source_name), detail
