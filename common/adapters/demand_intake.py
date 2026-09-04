"""Demand intake export (.xlsx or .csv) -> work_items.

The intake queue has its own workflow vocabulary, so it maps statuses
explicitly rather than leaning on the generic pattern matcher - "Triage
Complete" means the demand is ready to start, not finished, and a pattern that
keys on the word "Complete" would file it as delivered.

This is also the richest source in the app for *flow* metrics: it carries four
real stage timestamps (created, estimation approved, development start, go
live), which is what makes stage cycle time and bottleneck analysis possible.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.adapters.base import extract_numeric, finalize, read_csv_robust

SOURCE_SYSTEM = "Demand Intake"

#: The intake workflow, mapped onto the shared taxonomy. On-Hold becomes
#: Blocked (it is work consuming a slot but not moving), and Cancelled stays
#: its own terminal state rather than being counted as delivered.
DEMAND_STATUS_CATEGORY = {
    "New": "To Do",
    "Triage Complete": "To Do",
    "Requirement Gathering": "In Progress",
    "Awaiting for Requirement": "In Progress",
    "Estimating": "In Progress",
    "Awaiting Requestor Approval": "In Progress",
    "Awaiting Investment Council Approval": "In Progress",
    "Waiting for SOW Approval": "In Progress",
    "Ready for Development": "To Do",
    "Executing Work": "In Progress",
    "On-Hold": "Blocked",
    "Execution Complete": "Done",
    "Cancelled": "Cancelled",
}

#: Ordered intake pipeline stages: (label, start column, end column, SLA key).
#: Drives the stage cycle-time and bottleneck views on the Demands page.
PIPELINE_STAGES = [
    ("Intake to estimate", "created", "estimation_approval_date", "demand_triage_days"),
    ("Estimate to start", "estimation_approval_date", "development_start_date", "demand_resourcing_days"),
    ("Start to go-live", "development_start_date", "go_live_date", "demand_delivery_days"),
]

DATE_COLUMNS = [
    ("Created", "created"),
    ("Go Live Date", "go_live_date"),
    ("Cancellation Date", "cancellation_date"),
    ("Development Start Date", "development_start_date"),
    ("Estimation Approval Date", "estimation_approval_date"),
]


def _read(path: Path) -> pd.DataFrame:
    if str(path).lower().endswith((".xlsx", ".xlsm")):
        return pd.read_excel(path)
    return read_csv_robust(path)


def parse(path, program_id: str):
    """Returns (work_items, demands_detail)."""
    raw = _read(Path(path))
    raw.columns = [str(c).strip() for c in raw.columns]

    detail = pd.DataFrame(index=raw.index)
    detail["demand_key"] = raw.get("ID", pd.Series(range(1, len(raw) + 1))).astype("string")
    detail["request_number"] = raw.get("Request Number")
    detail["title"] = raw.get("Title")
    detail["description"] = raw.get("Description")
    detail["requestor"] = raw.get("Requestor")
    detail["request_type"] = raw.get("Request Type")
    detail["status"] = raw.get("Status")
    detail["status_category"] = detail["status"].map(DEMAND_STATUS_CATEGORY)
    detail["assignment_group"] = raw.get("Assignment Group")
    detail["team_required"] = raw.get("Team(s) Required")
    detail["solution_architect"] = raw.get("Solution Architect")
    detail["manager"] = raw.get("Manager")
    detail["vp_leader"] = raw.get("VP Leader")
    detail["ic_approval_status"] = raw.get("IC Approval Status")
    detail["resource_status"] = raw.get("Resource Status")
    detail["delay_type"] = raw.get("Delay Type")
    detail["project_status"] = raw.get("Project Status")
    detail["release"] = raw.get("Release")

    for src, dest in DATE_COLUMNS:
        detail[dest] = pd.to_datetime(raw.get(src), errors="coerce")

    detail["hours_estimate"] = extract_numeric(raw.get("Hours Estimate", pd.Series(dtype="string")))
    detail["cost_estimate_usd"] = extract_numeric(raw.get("Cost Estimate", pd.Series(dtype="string")))

    source_name = getattr(path, "name", str(path))
    detail["program_id"] = program_id
    detail["source_file"] = source_name
    detail["program_name"] = Path(source_name).stem

    work = pd.DataFrame({
        "program_id": program_id,
        "item_key": detail["demand_key"],
        "title": detail["title"],
        "item_type": "Demand",
        "workstream": detail["request_type"],
        "domain": detail["assignment_group"],
        "owner": detail["solution_architect"],
        "status_raw": detail["status"],
        "status_category": detail["status_category"],
        "created": detail["created"],
        "started": detail["development_start_date"],
        "completed": detail["go_live_date"],
        "effort_hours": detail["hours_estimate"],
        "is_leaf": True,
    })
    # A demand has no due date to be overdue against - its ageing is measured
    # from intake, which is why the page ranks by age rather than by lateness.
    return finalize(work, SOURCE_SYSTEM, source_name), detail
