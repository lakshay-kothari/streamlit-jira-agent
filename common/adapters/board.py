"""AI/BI tracker board (agents / data products) -> work_items.

One row per agent being built. Sub-domain, not Domain, is the meaningful axis
here: the real board has 145 of 149 rows tagged simply "Business", while
Sub-domain spreads across GOSC, Commercial, Manufacturing, Regulatory and the
rest. So `domain` on the contract is fed from Sub-domain, and the coarse
Domain column is kept on the detail frame for reference.

A blank Status is left blank on purpose. The previous behaviour backfilled it to
"Not Started", which made 146 of 149 agents look deliberately parked when in
truth nobody had filled the field in - reporting missing data as a status.
"""
from __future__ import annotations

import pandas as pd

from common.adapters.base import finalize, normalize_status, read_csv_robust

SOURCE_SYSTEM = "AI/BI Board"

#: Board statuses in rollout order, for the funnel chart on the Agents page.
ROLLOUT_STAGES = ["Idea", "Scoping", "WIP", "UAT", "Live", "On Hold"]


def _blank_to_na(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace(r"^\s*$", pd.NA, regex=True)


def parse(path, program_id: str):
    """Returns (work_items, board_detail)."""
    raw = read_csv_robust(path, dtype="string", keep_default_na=True, low_memory=False)
    raw.columns = [str(c).strip() for c in raw.columns]

    name_col = next(
        (c for c in raw.columns if "agents" in c.lower() and "data product" in c.lower()),
        raw.columns[0] if len(raw.columns) else "name",
    )

    detail = pd.DataFrame(index=raw.index)
    detail["item_key"] = raw.get("SNo", pd.Series(range(1, len(raw) + 1), dtype="string")).astype("string")
    detail["name"] = raw.get(name_col)
    detail["description"] = raw.get("Description")
    detail["owner"] = _blank_to_na(raw.get("Architects", pd.Series(dtype="string")))
    detail["domain"] = raw.get("Domain")
    detail["sub_domain"] = raw.get("Sub-Domain")
    detail["status"] = _blank_to_na(raw.get("Status", pd.Series(dtype="string")))
    detail["origin"] = _blank_to_na(raw.get("Origin", pd.Series(dtype="string")))
    detail["demand_intake_number"] = _blank_to_na(
        raw.get("Demand Intake Number", pd.Series(dtype="string")))
    detail["platform"] = _blank_to_na(raw.get("Platform", pd.Series(dtype="string")))
    detail["link"] = raw.get("Link")
    detail["comment"] = raw.get("Comment")
    detail["eta"] = pd.to_datetime(raw.get("ETA"), errors="coerce", format="mixed")
    detail["created"] = pd.to_datetime(raw.get("Created"), errors="coerce", format="mixed")
    detail["updated"] = pd.to_datetime(raw.get("Last Updated"), errors="coerce", format="mixed")
    detail["went_live"] = pd.to_datetime(raw.get("Go Live Date"), errors="coerce", format="mixed")

    detail["program_id"] = program_id
    source_name = getattr(path, "name", str(path))
    detail["source_file"] = source_name
    detail["program_name"] = getattr(path, "stem", source_name)

    work = pd.DataFrame({
        "program_id": program_id,
        "item_key": detail["item_key"],
        "title": detail["name"],
        "item_type": "Agent",
        # The board is grouped by sub-domain in practice; the Domain column is
        # too coarse to segment anything (145 of 149 rows say "Business").
        "workstream": detail["domain"],
        "domain": detail["sub_domain"],
        "owner": detail["owner"],
        "status_raw": detail["status"],
        "status_category": normalize_status(detail["status"]),
        "created": detail["created"],
        "due_date": detail["eta"],
        "completed": detail["went_live"],
        "updated": detail["updated"],
        "is_leaf": True,
    })
    # An agent with no status recorded is unknown, not "To Do" - keep the
    # distinction so the coverage panel can report it honestly.
    work.loc[detail["status"].isna(), "status_category"] = pd.NA
    return finalize(work, SOURCE_SYSTEM, source_name), detail
