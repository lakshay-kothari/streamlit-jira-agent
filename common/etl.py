"""Source discovery and loading for the Program Command Center.

This module now only *finds* files and decides which adapter owns each one.
The actual column mapping lives in `common/adapters/` - one adapter per source
shape - because every program in this portfolio arrives from a different tool
(Jira, ServiceNow, an Excel PM tracker, a validated-system export, a weekly
status report) with its own columns and its own words for "done".

Everything lands in two places:

* `programs`   - the registry: one row per program, `is_strategic` a facet of it.
* `work_items` - one normalized row per unit of work, whatever its origin, so
                 every metric in common/kpi.py is computed once over one table.

The source-specific tables (`issues`, `board_items`, `demands`) are still
written, because the pages use their native fields for drill-downs.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from common.adapters import board, demand_intake, jira, milestone_sources, registry, servicenow
from common.adapters.base import WORK_ITEM_COLUMNS, empty_work_items, read_csv_robust
from common.adapters.registry import UNATTACHED
from common.config import (
    GENERATED_DIR,
    RAW_DIR,
    SQLITE_PATH,
    TABLE_BOARD_ITEMS,
    TABLE_DEMANDS,
    TABLE_GENERIC_ITEMS,
    TABLE_ISSUES,
    TABLE_PROGRAMS,
    TABLE_PROGRAMS_META,
    TABLE_WORK_ITEMS,
)

# --------------------------------------------------------------- detection ---


def _is_jira_export(columns: list) -> bool:
    return "Issue key" in columns


def _is_board_export(columns: list) -> bool:
    lower = {c.strip().lower() for c in columns}
    return len({"architects", "sub-domain", "domain", "agents/data products"} & lower) >= 2


def _is_demands_export(columns: list) -> bool:
    lower = {c.strip().lower() for c in columns}
    return len({"requestor", "request type", "ic approval status", "resource status"} & lower) >= 3


def _is_strategic_export(columns: list) -> bool:
    lower = {c.strip().lower() for c in columns}
    return len({"executive sponsor", "phase", "health", "target quarter"} & lower) >= 3


def _is_servicenow_export(columns: list) -> bool:
    lower = {c.strip().lower() for c in columns}
    return len({"sys_id", "u_state", "assignment_group"} & lower) >= 2


#: Milestone-shaped sources, in detection order. Each entry is the set of
#: columns that uniquely identifies the tool, plus the spec that maps it.
MILESTONE_SIGNATURES = [
    ({"milestone id", "baseline finish", "rag"}, milestone_sources.EXCEL_TRACKER),
    ({"record id", "record state", "gate"}, milestone_sources.TRACKWISE),
    ({"row id", "outline level", "predecessors"}, milestone_sources.SMARTSHEET),
    ({"ref", "deliverable", "committed date"}, milestone_sources.STATUS_REPORT),
]


def _milestone_spec(columns: list):
    lower = {c.strip().lower() for c in columns}
    for signature, spec in MILESTONE_SIGNATURES:
        if len(signature & lower) >= 2:
            return spec
    return None


def _is_registry(path: Path) -> bool:
    return path.name in registry.REGISTRY_FILENAMES


def _columns_of(path: Path) -> list:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return list(pd.read_excel(path, nrows=0).columns)
    return list(read_csv_robust(path, nrows=0, dtype="string").columns)


# ------------------------------------------------- strategic CSV -> registry ---
def strategic_csv_to_registry_rows(path: Path) -> pd.DataFrame:
    """The PMO's Strategic Initiatives export becomes *registry rows*, not its
    own table. An initiative is a program with `is_strategic` set - modelling it
    separately is what let the two pages double count the same work.

    The file's hand-typed `% Complete` is deliberately dropped: progress is
    derived from the linked delivery work instead, so the number on screen can
    always be traced back to something.
    """
    raw = read_csv_robust(path)
    raw.columns = [str(c).strip() for c in raw.columns]
    out = pd.DataFrame(index=raw.index)
    out["program_id"] = raw.get("Initiative").map(
        lambda v: registry.slugify(v) if pd.notna(v) else None)
    out["name"] = raw.get("Initiative")
    out["is_strategic"] = "true"
    out["parent_program_id"] = pd.NA
    out["portfolio"] = "Strategic Portfolio"
    out["domain"] = raw.get("Domain")
    out["executive_sponsor"] = raw.get("Executive Sponsor")
    out["program_owner"] = raw.get("Program Owner")
    out["delivery_lead"] = pd.NA
    out["phase"] = raw.get("Phase")
    out["start_date"] = raw.get("Start Date")
    out["target_date"] = raw.get("Target Date")
    out["target_quarter"] = raw.get("Target Quarter")
    out["budget_usd"] = raw.get("Budget (USD)")
    out["spent_usd"] = raw.get("Spent (USD)")
    out["source_system"] = "PMO Register"
    out["source_files"] = pd.NA
    out["jira_project_keys"] = pd.NA
    out["demand_assignment_groups"] = pd.NA
    out["agent_sub_domains"] = pd.NA
    out["key_risks"] = raw.get("Key Risks")
    return out


# ------------------------------------------------------------------ loading ---
@dataclass
class LoadResult:
    programs: pd.DataFrame
    work_items: pd.DataFrame
    issues: pd.DataFrame
    board_items: pd.DataFrame
    demands: pd.DataFrame
    generic_items: pd.DataFrame
    programs_meta: pd.DataFrame


#: A generated file may be an enriched *replacement* for a real one rather than
#: an addition to it. Loading both would double the agent board. The real file
#: is never modified - it is simply skipped while its enriched twin is present,
#: so deleting the generated folder restores it automatically.
SUPERSEDED_BY = {"AI for BI Board.csv": "ai_bi_board_enriched.csv"}


def _source_paths(directories) -> list:
    paths = []
    for directory in directories:
        base = Path(directory)
        if not base.exists():
            continue
        for pattern in ("*.csv", "*.xlsx"):
            paths.extend(sorted(base.glob(pattern)))

    present = {p.name for p in paths}
    return [p for p in paths
            if SUPERSEDED_BY.get(p.name) not in present]


def discover_and_load(raw_dir=RAW_DIR, generated_dir=GENERATED_DIR) -> LoadResult:
    directories = [raw_dir, generated_dir]
    programs = registry.load(*directories)

    paths = [p for p in _source_paths(directories) if not _is_registry(p)]
    meta_rows, work_frames = [], []
    issue_frames, board_frames, demand_frames, generic_frames = [], [], [], []
    work_detail_frames = []  # milestone/ticket sources: work_items is the detail
    strategic_rows = []

    for path in paths:
        try:
            columns = _columns_of(path)
        except Exception as exc:  # a malformed file must not stop the build
            meta_rows.append({"source_file": path.name, "kind": "error", "row_count": 0,
                              "detail": str(exc)})
            continue

        try:
            if _is_strategic_export(columns):
                strategic_rows.append(strategic_csv_to_registry_rows(path))
                meta_rows.append({"source_file": path.name, "kind": "strategic_registry",
                                  "row_count": len(strategic_rows[-1]), "detail": ""})
                continue

            resolver = registry.Resolver(programs)
            if _is_jira_export(columns):
                program_id = resolver.by_source_file(path.name)
                work, detail = jira.parse(path, program_id)
                if program_id == UNATTACHED and "project_key" in detail.columns:
                    resolved = resolver.by_jira_project_key(detail["project_key"])
                    detail["program_id"] = resolved
                    work["program_id"] = resolved.values
                issue_frames.append(detail)
                kind = "jira_issues"
            elif _is_board_export(columns):
                work, detail = board.parse(path, UNATTACHED)
                resolved = resolver.by_agent_sub_domain(detail["sub_domain"])
                detail["program_id"] = resolved
                work["program_id"] = resolved.values
                board_frames.append(detail)
                kind = "board"
            elif _is_demands_export(columns):
                work, detail = demand_intake.parse(path, UNATTACHED)
                resolved = resolver.by_assignment_group(detail["assignment_group"])
                detail["program_id"] = resolved
                work["program_id"] = resolved.values
                demand_frames.append(detail)
                kind = "demands"
            elif _is_servicenow_export(columns):
                work, detail = servicenow.parse(path, resolver)
                work_detail_frames.append(detail)
                kind = "servicenow"
            elif _milestone_spec(columns) is not None:
                spec = _milestone_spec(columns)
                work, detail = milestone_sources.parse(path, spec, resolver)
                work_detail_frames.append(detail)
                kind = spec.source_system.lower().replace(" ", "_")
            else:
                work, detail = _parse_generic(path, resolver.by_source_file(path.name))
                generic_frames.append(detail)
                kind = "generic"
        except Exception as exc:  # noqa: BLE001 - one bad file, not a broken build
            meta_rows.append({"source_file": path.name, "kind": "error", "row_count": 0,
                              "detail": str(exc)})
            continue

        work_frames.append(work)
        meta_rows.append({"source_file": path.name, "kind": kind, "row_count": len(work),
                          "detail": ""})

    if strategic_rows:
        extra = pd.concat(strategic_rows, ignore_index=True)
        merged = pd.concat([programs, registry.normalize(extra)], ignore_index=True)
        programs = merged.drop_duplicates(subset="program_id", keep="first").reset_index(drop=True)

    return LoadResult(
        programs=programs,
        work_items=(pd.concat(work_frames, ignore_index=True)[WORK_ITEM_COLUMNS]
                    if work_frames else empty_work_items()),
        issues=_concat(issue_frames, ISSUES_COLUMNS),
        board_items=_concat(board_frames, BOARD_COLUMNS),
        demands=_concat(demand_frames, DEMANDS_COLUMNS),
        generic_items=_concat(generic_frames, GENERIC_COLUMNS),
        programs_meta=(pd.DataFrame(meta_rows) if meta_rows
                       else pd.DataFrame(columns=["source_file", "kind", "row_count", "detail"])),
    )


#: Minimal column sets so an absent source still produces a real (empty) table
#: rather than a zero-column one, which SQLite cannot create.
ISSUES_COLUMNS = ["issue_key", "summary", "issue_type", "status", "status_category",
                  "project_key", "project_name", "priority", "assignee", "parent_key",
                  "parent_summary", "created", "updated", "resolved", "due_date",
                  "domain", "workstream", "program_id", "program_name", "source_file"]
BOARD_COLUMNS = ["item_key", "name", "description", "owner", "domain", "sub_domain",
                 "status", "origin", "demand_intake_number", "platform", "link", "eta",
                 "comment", "created", "updated", "went_live", "program_id",
                 "program_name", "source_file"]
DEMANDS_COLUMNS = ["demand_key", "request_number", "title", "requestor", "request_type",
                   "status", "status_category", "assignment_group", "team_required",
                   "solution_architect", "vp_leader", "ic_approval_status", "delay_type",
                   "project_status", "created", "go_live_date", "development_start_date",
                   "estimation_approval_date", "cancellation_date", "hours_estimate",
                   "cost_estimate_usd", "program_id", "program_name", "source_file"]
GENERIC_COLUMNS = ["name", "status", "owner", "category", "program_id", "program_name",
                   "source_file"]


def _concat(frames: list, columns: list) -> pd.DataFrame:
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


def _parse_generic(path: Path, program_id: str):
    """Fallback so a CSV added before anyone writes its adapter still shows up
    (counted, listed, attributable) rather than being silently ignored."""
    from common.adapters.base import finalize, normalize_status

    raw = read_csv_robust(path, dtype="string", keep_default_na=True, low_memory=False)
    raw.columns = [str(c).strip() for c in raw.columns]

    def find(*aliases):
        lower = {c.lower(): c for c in raw.columns}
        for alias in aliases:
            if alias in lower:
                return raw[lower[alias]]
        return pd.Series([pd.NA] * len(raw), dtype="string")

    detail = pd.DataFrame(index=raw.index)
    detail["name"] = find("name", "title", "summary", "item")
    if detail["name"].isna().all() and len(raw.columns):
        detail["name"] = raw.iloc[:, 0]
    detail["status"] = find("status", "state")
    detail["owner"] = find("owner", "assignee", "architect", "architects", "lead")
    detail["category"] = find("domain", "category", "type", "sub-domain")
    detail["source_file"] = path.name
    detail["program_id"] = program_id
    detail["program_name"] = path.stem

    work = pd.DataFrame({
        "program_id": program_id,
        "item_key": raw.index.astype(str),
        "title": detail["name"],
        "item_type": "Item",
        "domain": detail["category"],
        "owner": detail["owner"],
        "status_raw": detail["status"],
        "status_category": normalize_status(detail["status"]),
        "is_leaf": True,
    })
    return finalize(work, "Unknown", path.name), detail


# ------------------------------------------------------------------ persist ---
TABLE_ORDER = [
    (TABLE_PROGRAMS, "programs"),
    (TABLE_WORK_ITEMS, "work_items"),
    (TABLE_ISSUES, "issues"),
    (TABLE_BOARD_ITEMS, "board_items"),
    (TABLE_DEMANDS, "demands"),
    (TABLE_GENERIC_ITEMS, "generic_items"),
    (TABLE_PROGRAMS_META, "programs_meta"),
]


def build_and_save_sqlite(raw_dir=RAW_DIR, generated_dir=GENERATED_DIR,
                          db_path=SQLITE_PATH) -> LoadResult:
    result = discover_and_load(raw_dir, generated_dir)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        # strategic_initiatives is no longer its own table - initiatives are rows
        # in `programs` with is_strategic set. Drop any copy left by an older
        # build so nothing reads a stale, contradictory version of the truth.
        conn.execute("DROP TABLE IF EXISTS strategic_initiatives")
        for table, attribute in TABLE_ORDER:
            frame = getattr(result, attribute).copy()
            for col in frame.columns:
                if pd.api.types.is_datetime64_any_dtype(frame[col]):
                    frame[col] = frame[col].astype("string")
            frame.to_sql(table, conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()

    _append_snapshot(result, db_path)
    return result


def _append_snapshot(result: LoadResult, db_path) -> None:
    """Record today's value for the metrics that cannot be rewound from item
    dates (blocked counts, health bands). Completion and throughput history is
    derived on the fly in common/snapshots.py and needs nothing stored - so only
    the genuinely unrecoverable numbers are persisted here."""
    from common import kpi, snapshots

    scorecard = kpi.program_scorecard(result.programs, result.work_items)
    if scorecard.empty:
        return
    today = pd.Timestamp.now().normalize()
    rows = []
    for _, program in scorecard.iterrows():
        for metric_key in ("blocked", "open", "total", "pct_complete", "schedule_variance"):
            value = program.get(metric_key)
            if value is not None and not pd.isna(value):
                rows.append({"snapshot_date": today, "program_id": program["program_id"],
                             "metric_key": metric_key, "value": float(value)})
    snapshots.append(pd.DataFrame(rows), db_path)


if __name__ == "__main__":
    res = build_and_save_sqlite()
    print(f"programs: {len(res.programs)} | work_items: {len(res.work_items)} | "
          f"issues: {len(res.issues)} | board_items: {len(res.board_items)} | "
          f"demands: {len(res.demands)} | sources: {len(res.programs_meta)}")
