"""Generate the synthetic portfolio that sits alongside the real exports.

    python scripts/generate_demo_data.py            # writes data/raw/generated/
    python scripts/generate_demo_data.py --seed 7   # a different draw

Everything lands in `data/raw/generated/`. The four real files in `data/raw/`
are never read for writing and never modified. Delete the generated folder and
rebuild to return the app to real-data-only - which matters when demoing, so
you can always say which numbers came from a real system.

Why generate at all: the portfolio model has to work for programs arriving from
different tools with different fields, and there is exactly one real program
today. So each generated program gets its own source *shape* (Jira, ServiceNow,
an Excel milestone tracker, a validated-system export, a weekly status report, a
Smartsheet plan) and its own delivery *profile* - size, cadence, health, and
characteristic failure mode. A portfolio where every program looks the same
would prove nothing and teach a leader nothing.
"""
from __future__ import annotations

import argparse
import sys
import zlib
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.adapters.base import JIRA_DATE_FORMAT, read_csv_robust, slugify  # noqa: E402
from common.config import GENERATED_DIR  # noqa: E402

# --------------------------------------------------------------------- people ---
OWNERS = [
    "Priya Nandakumar", "Daniel Osei", "Marta Kowalski", "Hiroshi Tanaka", "Amara Okafor",
    "Sean Gallagher", "Lucia Ferrari", "Rajesh Iyer", "Nora Lindqvist", "Tomas Vargas",
    "Ingrid Bauer", "Wei Zhang", "Fatima Al-Rashid", "Colin Murphy", "Beatriz Santos",
    "Anders Holm", "Yuki Nakamura", "Grace Mwangi", "Pavel Novak", "Elena Petrova",
]
SPONSORS = [
    "VP, Finance Transformation", "VP, Global Operations", "VP, Data & Analytics",
    "VP, Quality & Regulatory", "VP, Commercial Excellence", "VP, Global Trade & Customs",
    "SVP, Enterprise Technology", "VP, Corporate Development", "VP, APAC Region",
]

# ------------------------------------------------------------------- profiles ---
# Every program is deliberately different: a portfolio of look-alikes would make
# the dashboard's comparisons meaningless. `mix` is the status distribution the
# program is drawn from, and it is what gives each one its character - scope
# churn, a blocked queue, a clean run, a stalled discovery phase.
PROFILES = [
    dict(name="Finance Digital Transformation", shape="smartsheet", strategic=True,
         purpose="Consolidate the financial close and management reporting stack onto S4.",
         portfolio="Finance", domain="Finance", phase="Execution",
         start="2024-09-02", target="2027-03-31", quarter="Q4 FY27",
         budget=4_200_000, spent=2_640_000, items=220, owners=7, cycle_median=38,
         mix=dict(done=0.45, in_progress=0.24, blocked=0.06, to_do=0.16, cancelled=0.09),
         groups=["Record to Report", "Order to Cash", "Procure to Pay", "Treasury"],
         streams=["Close Automation", "Reporting Layer", "Controls & SOX", "Data Migration"],
         risk="Statutory reporting scope keeps expanding; four late change requests in the last quarter."),
    dict(name="S4 Modernization", shape="excel_tracker", strategic=True,
         purpose="Core ERP replacement across every manufacturing and commercial region.",
         portfolio="ERP", domain="ERP Modernization", phase="Planning",
         start="2025-06-02", target="2029-06-29", quarter="Q1 FY30",
         budget=18_000_000, spent=3_100_000, items=64, owners=9, cycle_median=95,
         mix=dict(done=0.18, in_progress=0.30, blocked=0.09, to_do=0.40, cancelled=0.03),
         groups=["Finance", "Supply Chain", "Manufacturing", "Commercial"],
         streams=["Global Template", "Regional Rollout", "Data & Cutover", "OCM"],
         risk="Global template sign-off is the gating dependency for every regional wave."),
    dict(name="S4 WS 4A", shape="excel_tracker", strategic=True, parent="s4-modernization",
         purpose="Workstream 4A - plant maintenance and quality integration for S4.",
         portfolio="ERP", domain="ERP Modernization", phase="Discovery",
         start="2026-01-05", target="2028-06-30", quarter="Q2 FY28",
         budget=5_600_000, spent=780_000, items=28, owners=4, cycle_median=110,
         mix=dict(done=0.12, in_progress=0.21, blocked=0.14, to_do=0.50, cancelled=0.03),
         groups=["Manufacturing", "Quality"],
         streams=["Process Design", "Integration Build", "Validation"],
         risk="Plant maintenance SME availability is unresolved at three of nine sites."),
    dict(name="Kaika (Japan JDE)", shape="status_report", strategic=True,
         purpose="Converge the Japan JDE estate onto the global S4 template.",
         portfolio="APAC", domain="Regional ERP", phase="Execution",
         start="2025-02-03", target="2026-12-18", quarter="Q3 FY27",
         budget=3_400_000, spent=2_210_000, items=42, owners=5, cycle_median=44,
         mix=dict(done=0.61, in_progress=0.22, blocked=0.02, to_do=0.13, cancelled=0.02),
         groups=["Japan", "APAC Shared"],
         streams=["Finance Convergence", "Logistics", "Localization", "Cutover"],
         risk="Japanese statutory localization testing is compressed into a single window."),
    dict(name="SPM", shape="status_report", strategic=True,
         purpose="Supplier performance management - scorecards and supplier risk signals.",
         portfolio="Supply Chain", domain="Supply Chain", phase="Planning",
         start="2026-02-02", target="2027-09-30", quarter="Q2 FY28",
         budget=1_200_000, spent=190_000, items=26, owners=3, cycle_median=52,
         mix=dict(done=0.15, in_progress=0.19, blocked=0.12, to_do=0.50, cancelled=0.04),
         groups=["Direct Materials", "Indirect"],
         streams=["Scorecard Design", "Data Sourcing", "Pilot"],
         risk="Two of three analyst roles are still unfilled; start date has moved twice."),
    dict(name="NextGen Trackwise", shape="trackwise", strategic=True,
         purpose="Quality management system upgrade, including computer-system validation.",
         portfolio="Quality", domain="Quality & Regulatory", phase="Stabilization",
         start="2024-11-04", target="2026-11-30", quarter="Q3 FY27",
         budget=6_800_000, spent=5_950_000, items=96, owners=6, cycle_median=61,
         mix=dict(done=0.72, in_progress=0.16, blocked=0.05, to_do=0.05, cancelled=0.02),
         groups=["Minneapolis", "Galway", "Singapore"],
         streams=["Validation", "Migration", "Training", "Hypercare"],
         risk="Validation evidence rework is consuming the contingency built into hypercare."),
    dict(name="FieldLink", shape="servicenow", strategic=True,
         purpose="Mobile enablement for field service technicians and their service orders.",
         portfolio="Commercial", domain="Field Operations", phase="Execution",
         start="2025-01-06", target="2026-10-30", quarter="Q2 FY27",
         budget=2_900_000, spent=1_820_000, items=310, owners=8, cycle_median=19,
         mix=dict(done=0.68, in_progress=0.18, blocked=0.03, to_do=0.09, cancelled=0.02),
         groups=["Field Service", "Service Parts"],
         streams=["Mobile App", "Offline Sync", "Dispatch", "Reporting"],
         risk="Offline sync conflicts remain the top defect category in the field pilot."),
    dict(name="M&A", shape="smartsheet", strategic=True,
         purpose="Acquisition integration playbook, plus two live carve-out integrations.",
         portfolio="Corporate", domain="Corporate Development", phase="Discovery",
         start="2026-03-02", target="2027-12-31", quarter="Q3 FY28",
         budget=2_100_000, spent=440_000, items=74, owners=5, cycle_median=41,
         mix=dict(done=0.22, in_progress=0.24, blocked=0.08, to_do=0.32, cancelled=0.14),
         groups=["Integration", "Divestiture", "Playbook"],
         streams=["Day 1 Readiness", "Systems Integration", "TSA Exit"],
         risk="Scope is deal-driven: two workstreams were stood down when a deal lapsed."),
    dict(name="NextGen P&C Commercial", shape="servicenow", strategic=True,
         purpose="Pricing and contracting modernization for the commercial organisation.",
         portfolio="Commercial", domain="Commercial", phase="Execution",
         start="2024-10-01", target="2027-06-30", quarter="Q1 FY28",
         budget=7_500_000, spent=4_900_000, items=420, owners=11, cycle_median=27,
         mix=dict(done=0.51, in_progress=0.23, blocked=0.11, to_do=0.11, cancelled=0.04),
         groups=["Pricing", "Contracting", "Rebates"],
         streams=["Price Engine", "Contract Lifecycle", "Rebate Settlement", "Integrations"],
         risk="Eleven percent of the queue is blocked on a single external pricing vendor."),
    dict(name="Commercial GCDH", shape="servicenow", strategic=True,
         purpose="Global Commercial Data Hub - one governed customer and product view.",
         portfolio="Commercial", domain="Commercial Data", phase="Execution",
         start="2025-05-05", target="2026-12-31", quarter="Q3 FY27",
         budget=3_300_000, spent=2_420_000, items=180, owners=6, cycle_median=31,
         mix=dict(done=0.44, in_progress=0.21, blocked=0.06, to_do=0.12, cancelled=0.17),
         groups=["Customer", "Product", "Territory"],
         streams=["Ingestion", "Governance", "Consumption APIs"],
         risk="Seventeen percent of accepted scope has been descoped - requirements churn."),
    dict(name="SAP GTS", shape="jira", jira_key="GTS", strategic=True,
         purpose="Automated denied-party screening, customs classification and duty management.",
         portfolio="Global Trade", domain="Global Trade & Compliance", phase="Execution",
         start="2026-01-12", target="2027-03-31", quarter="Q1 FY27",
         budget=2_400_000, spent=1_450_000, items=240, owners=6, cycle_median=23,
         mix=dict(done=0.66, in_progress=0.17, blocked=0.03, to_do=0.11, cancelled=0.03),
         groups=["Screening", "Classification", "Customs Filing"],
         streams=["Denied Party", "Product Classification", "Broker EDI", "Duty Management"],
         risk="Customs broker EDI certification is tracking about three weeks late."),
    dict(name="SAP MDG", shape="jira", jira_key="MDG", strategic=True,
         purpose="Master data governance for material, vendor and customer master.",
         portfolio="Master Data", domain="Master Data Management", phase="Planning",
         start="2026-04-01", target="2027-09-30", quarter="Q3 FY27",
         budget=1_800_000, spent=410_000, items=130, owners=4, cycle_median=57,
         mix=dict(done=0.19, in_progress=0.22, blocked=0.13, to_do=0.43, cancelled=0.03),
         groups=["Material Master", "Vendor Master", "Customer Master"],
         streams=["Stewardship Workflow", "Data Quality Rules", "Integration"],
         risk="Business data stewards are unconfirmed in two of four regions."),
    dict(name="Reltio - MDM", shape="jira", jira_key="RLT", strategic=True,
         purpose="Consolidate MDM onto Reltio and retire the legacy hub.",
         portfolio="Master Data", domain="Master Data Management", phase="Stabilization",
         start="2024-08-05", target="2026-12-31", quarter="Q4 FY26",
         budget=3_100_000, spent=2_730_000, items=300, owners=7, cycle_median=29,
         mix=dict(done=0.84, in_progress=0.09, blocked=0.02, to_do=0.03, cancelled=0.02),
         groups=["HCP", "HCO", "Product"],
         streams=["Golden Record", "Survivorship Rules", "Legacy Retirement"],
         risk="Legacy hub decommissioning depends on two downstream consumers migrating."),

    # ---- non-strategic programs: real delivery work, no sponsor-level framing ----
    dict(name="BI Platform Support", shape="servicenow", strategic=False,
         purpose="Run and support for the existing BI estate - keep the lights on.",
         portfolio="Data & AI Platform", domain="Data Platform", phase="Execution",
         start="2024-01-08", target="2027-12-31", quarter="Ongoing",
         budget=1_600_000, spent=1_180_000, items=260, owners=5, cycle_median=6,
         mix=dict(done=0.82, in_progress=0.10, blocked=0.02, to_do=0.05, cancelled=0.01),
         groups=["Reporting", "Data Quality", "Access"],
         streams=["Incidents", "Service Requests", "Minor Enhancements"],
         risk="Steady-state queue; risk is capacity being pulled onto project work."),
    dict(name="Regulatory Reporting Automation", shape="jira", jira_key="REG", strategic=False,
         purpose="Automate periodic regulatory submissions and their evidence packs.",
         portfolio="Quality", domain="Quality & Regulatory", phase="Execution",
         start="2025-09-01", target="2026-11-30", quarter="Q3 FY27",
         budget=900_000, spent=540_000, items=95, owners=3, cycle_median=25,
         mix=dict(done=0.57, in_progress=0.20, blocked=0.04, to_do=0.16, cancelled=0.03),
         groups=["EU MDR", "FDA", "Health Canada"],
         streams=["Submission Engine", "Evidence Capture", "Audit Trail"],
         risk="EU MDR template changes land mid-build and force rework."),
    dict(name="Analytics Enablement", shape="status_report", strategic=False,
         purpose="Self-service analytics enablement, training and community of practice.",
         portfolio="Data & AI Platform", domain="Data Platform", phase="Execution",
         start="2025-03-03", target="2027-03-31", quarter="Q4 FY27",
         budget=650_000, spent=380_000, items=34, owners=3, cycle_median=21,
         mix=dict(done=0.63, in_progress=0.18, blocked=0.03, to_do=0.14, cancelled=0.02),
         groups=["Global", "EMEA", "Americas"],
         streams=["Curriculum", "Champions Network", "Certification"],
         risk="Adoption depends on business-unit champions who have day jobs."),
]

STATUS_WORDS = {
    "jira": dict(done="Deployment Completed", in_progress="Development in Progress",
                 blocked="Blocked", to_do="To Do", cancelled="Descoped"),
    "servicenow": dict(done="Closed Complete", in_progress="Work in Progress",
                       blocked="Pending Vendor", to_do="Assigned", cancelled="Cancelled"),
    "excel_tracker": dict(done="Complete", in_progress="In Progress", blocked="Blocked",
                          to_do="Not Started", cancelled="Deferred"),
    "status_report": dict(done="Complete", in_progress="In Progress", blocked="Slipped",
                          to_do="Not Started", cancelled="Dropped"),
    "smartsheet": dict(done="Complete", in_progress="In Progress", blocked="On Hold",
                       to_do="Not Started", cancelled="Cancelled"),
    "trackwise": dict(done="Closed", in_progress="Verification", blocked="Awaiting QA Sign-off",
                      to_do="Draft", cancelled="Voided"),
}

CATEGORY_KEYS = ["done", "in_progress", "blocked", "to_do", "cancelled"]


# ----------------------------------------------------------------- generation ---
def _draw_items(profile: dict, rng: np.random.Generator, today: pd.Timestamp) -> pd.DataFrame:
    """One row per unit of work, with dates that make the program's profile true.

    Cycle times are drawn lognormally around the program's own median, so a fast
    support queue and a slow validated-system programme produce genuinely
    different distributions rather than the same curve with a different label.
    """
    n = profile["items"]
    start = pd.Timestamp(profile["start"])
    target = pd.Timestamp(profile["target"])
    horizon = min(today, target)

    weights = np.array([profile["mix"][k] for k in CATEGORY_KEYS], dtype=float)
    weights = weights / weights.sum()
    category = rng.choice(CATEGORY_KEYS, size=n, p=weights)

    span_days = max((horizon - start).days, 30)
    cycle = rng.lognormal(np.log(profile["cycle_median"]), 0.62, n)

    is_done = category == "done"
    is_cancelled = category == "cancelled"
    active = np.isin(category, ["in_progress", "blocked"])
    finished = is_done | is_cancelled

    # Closed work is dated by when it *finished*, spread across the whole
    # elapsed window and running right up to today, with `created` backed out
    # from the cycle time. Deriving completion from creation instead leaves a
    # gap of one cycle-length at the end of the series, which would make every
    # program look stalled in exactly the trailing window the throughput and
    # forecast metrics read from.
    finish_offset = rng.uniform(0.04, 1.0, n) * span_days
    completed_days = np.where(finished, finish_offset, np.nan)
    # Open work is created across the window, front-loaded slightly: plans are
    # broken down faster early on than during the long delivery tail.
    open_created_days = rng.beta(1.6, 2.2, n) * span_days

    created_days = np.where(finished,
                            np.maximum(completed_days - cycle, 0),
                            open_created_days)
    created = pd.to_datetime([start + timedelta(days=int(d)) for d in created_days])

    planned = np.maximum(cycle * rng.uniform(0.75, 1.35, n), 3)
    due = created + pd.to_timedelta(planned.round(), unit="D")

    completed = pd.Series(pd.NaT, index=range(n))
    started = pd.Series(pd.NaT, index=range(n))
    completed[finished] = pd.to_datetime(
        [start + timedelta(days=int(d)) for d in completed_days[finished]])
    # Nothing can have finished in the future.
    completed = completed.where(completed.isna() | (completed <= today), today)
    started[is_done | active] = created[is_done | active] + pd.to_timedelta(
        rng.integers(0, 14, int((is_done | active).sum())), unit="D")

    # Updated: done work stops moving; blocked work is the stalest of all, which
    # is what makes the blocked-age metric worth looking at.
    updated = completed.copy()
    idle = rng.integers(1, 30, n)
    idle = np.where(category == "blocked", rng.integers(10, 120, n), idle)
    idle = np.where(category == "to_do", rng.integers(5, 200, n), idle)
    open_updated = pd.to_datetime([today - timedelta(days=int(d)) for d in idle])
    updated = updated.where(updated.notna(), pd.Series(open_updated, index=range(n)))
    updated = updated.where(updated >= pd.Series(created, index=range(n)),
                            pd.Series(created, index=range(n)))

    owners = OWNERS[: profile["owners"]]
    # A realistic board is not evenly loaded: a couple of people carry most of it.
    owner_weights = np.array([1.0 / (i + 1) ** 0.7 for i in range(len(owners))])
    owner_weights /= owner_weights.sum()

    words = STATUS_WORDS[profile["shape"]]
    return pd.DataFrame({
        "seq": np.arange(1, n + 1),
        "category": category,
        "status": [words[c] for c in category],
        "title": _titles(profile, n, rng),
        "workstream": rng.choice(profile["streams"], n),
        "domain": rng.choice(profile["groups"], n),
        "owner": rng.choice(owners, n, p=owner_weights),
        "created": created,
        "started": started.values,
        "due": due,
        "completed": completed.values,
        "updated": updated.values,
        "effort_hours": np.round(rng.lognormal(np.log(24), 0.9, n)).clip(2, 900),
        "reported_pct": np.where(is_done, 100,
                                 np.where(active, rng.integers(10, 85, n),
                                          np.where(is_cancelled, 0, 0))),
    })


VERBS = ["Design", "Build", "Configure", "Migrate", "Validate", "Integrate", "Document",
         "Test", "Deploy", "Refactor", "Onboard", "Automate", "Reconcile", "Decommission"]
NOUNS = ["interface", "data model", "approval workflow", "reporting extract", "reconciliation",
         "master record", "audit trail", "batch job", "user role", "dashboard", "API contract",
         "conversion rule", "test script", "cutover task", "training module"]


def _titles(profile: dict, n: int, rng: np.random.Generator) -> list:
    verbs = rng.choice(VERBS, n)
    nouns = rng.choice(NOUNS, n)
    streams = rng.choice(profile["streams"], n)
    return [f"{v} {s} {no}" for v, s, no in zip(verbs, streams, nouns)]


def _jira_dt(series) -> list:
    out = []
    for value in pd.to_datetime(pd.Series(series)):
        out.append("" if pd.isna(value) else value.strftime(JIRA_DATE_FORMAT))
    return out


def _iso(series) -> list:
    out = []
    for value in pd.to_datetime(pd.Series(series)):
        out.append("" if pd.isna(value) else value.strftime("%Y-%m-%d"))
    return out


# ----------------------------------------------------------------- writers ---
def write_jira(profiles: list, frames: dict, path: Path) -> None:
    """A Jira export hosting several programs, one project key each. Includes a
    real Initiative -> Epic -> Story tree so the hierarchy-based domain
    derivation is exercised by the generated data too, not just by the real
    export it was written for."""
    rows = []
    for profile in profiles:
        items = frames[profile["name"]]
        key = profile["jira_key"]
        issue_id = 100000
        # Initiatives are the domains; Epics are the workstreams beneath them.
        initiative_keys, epic_keys = {}, {}
        for i, domain in enumerate(profile["groups"], start=1):
            initiative_keys[domain] = f"{key}-{i}"
            rows.append(dict(_jira_row(f"{key}-{i}", issue_id + i, domain, "Initiative",
                                       "To Do", "To Do", key, profile, None, None)))
        offset = len(profile["groups"])
        for j, stream in enumerate(profile["streams"], start=1):
            parent_domain = profile["groups"][(j - 1) % len(profile["groups"])]
            epic_key = f"{key}-{offset + j}"
            epic_keys[stream] = (epic_key, parent_domain)
            rows.append(dict(_jira_row(epic_key, issue_id + offset + j, stream, "Epic",
                                       "To Do", "To Do", key, profile,
                                       initiative_keys[parent_domain], parent_domain)))
        offset += len(profile["streams"])

        for _, item in items.iterrows():
            epic_key, _ = epic_keys[item["workstream"]]
            number = offset + int(item["seq"])
            rows.append(dict(_jira_row(
                f"{key}-{number}", issue_id + number, item["title"],
                "Story" if item["seq"] % 4 else "Task", item["status"],
                _jira_category(item["category"]), key, profile, epic_key, item["workstream"],
                item)))
    pd.DataFrame(rows).to_csv(path, index=False)


def _jira_category(category: str) -> str:
    # Jira's own Status Category is written the way Jira really writes it -
    # including filing Descoped under Done. The adapter deliberately overrides
    # this; leaving it accurate is what makes that override worth testing.
    return {"done": "Done", "cancelled": "Done", "in_progress": "In Progress",
            "blocked": "In Progress", "to_do": "To Do"}[category]


def _jira_row(issue_key, issue_id, summary, issue_type, status, category, project_key,
              profile, parent_key, parent_summary, item=None) -> dict:
    row = {
        "Issue key": issue_key, "Issue id": issue_id, "Summary": summary,
        "Issue Type": issue_type, "Status": status, "Status Category": category,
        "Project key": project_key, "Project name": profile["name"],
        "Priority": "P3 - Medium", "Resolution": "Done" if category == "Done" else "",
        "Assignee": "", "Reporter": OWNERS[0], "Creator": OWNERS[0],
        "Parent key": parent_key or "", "Parent summary": parent_summary or "",
        "Team Name": profile["portfolio"], "Sprint": "",
        "Created": "", "Updated": "", "Resolved": "", "Due date": "",
        "Custom field (Domain)": "", "Custom field (Story Points)": "",
        "Custom field (Solution Architect)": "", "Original estimate": "",
    }
    if item is not None:
        row.update({
            "Assignee": item["owner"],
            "Priority": item["priority"] if "priority" in item else "P3 - Medium",
            "Created": _jira_dt([item["created"]])[0],
            "Updated": _jira_dt([item["updated"]])[0],
            "Resolved": _jira_dt([item["completed"]])[0] if status not in ("Descoped",) else "",
            "Due date": _jira_dt([item["due"]])[0],
            "Custom field (Solution Architect)": item["owner"],
            "Original estimate": int(item["effort_hours"] * 3600),
            "Resolution": {"Deployment Completed": "Done", "Descoped": "Won't Do"}.get(status, ""),
        })
    return row


def write_servicenow(profiles: list, frames: dict, path: Path) -> None:
    rows = []
    for profile in profiles:
        items = frames[profile["name"]]
        prefix = slugify(profile["name"])[:6]
        for _, item in items.iterrows():
            rows.append({
                "sys_id": f"{prefix}{int(item['seq']):05d}",
                "number": f"RITM{int(item['seq']):07d}",
                "short_description": item["title"],
                "u_program": profile["name"],
                "assignment_group": f"{profile['name']} POD",
                "u_workstream": item["workstream"],
                "u_business_area": item["domain"],
                "assigned_to": item["owner"],
                "u_state": item["status"],
                "priority": "3 - Moderate",
                "opened_at": _iso([item["created"]])[0],
                "work_start": _iso([item["started"]])[0],
                "due_date": _iso([item["due"]])[0],
                "closed_at": _iso([item["completed"]])[0],
                "sys_updated_on": _iso([item["updated"]])[0],
                "u_effort_hours": item["effort_hours"],
            })
    pd.DataFrame(rows).to_csv(path, index=False)


def write_excel_tracker(profiles: list, frames: dict, path: Path) -> None:
    rows = []
    for profile in profiles:
        for _, item in frames[profile["name"]].iterrows():
            rag = {"done": "Green", "in_progress": "Green", "blocked": "Red",
                   "to_do": "Amber", "cancelled": "Grey"}[item["category"]]
            rows.append({
                "Program": profile["name"],
                "Milestone ID": f"MS-{int(item['seq']):03d}",
                "Milestone": item["title"],
                "Workstream": item["workstream"],
                "Business Area": item["domain"],
                "Owner": item["owner"],
                "Status": item["status"],
                "RAG": rag,
                "% Complete": item["reported_pct"],
                "Baseline Start": _iso([item["created"]])[0],
                "Actual Start": _iso([item["started"]])[0],
                "Baseline Finish": _iso([item["due"]])[0],
                "Actual Finish": _iso([item["completed"]])[0],
                "Last Reviewed": _iso([item["updated"]])[0],
                "Effort (hrs)": item["effort_hours"],
            })
    pd.DataFrame(rows).to_excel(path, index=False)


def write_status_report(profiles: list, frames: dict, path: Path) -> None:
    rows = []
    for profile in profiles:
        for _, item in frames[profile["name"]].iterrows():
            rag = {"done": "Green", "in_progress": "Green", "blocked": "Red",
                   "to_do": "Amber", "cancelled": "Grey"}[item["category"]]
            rows.append({
                "Program": profile["name"],
                "Ref": f"D-{int(item['seq']):03d}",
                "Deliverable": item["title"],
                "Workstream": item["workstream"],
                "Region": item["domain"],
                "Accountable": item["owner"],
                "Status": item["status"],
                "RAG": rag,
                "Started": _iso([item["created"]])[0],
                "Committed Date": _iso([item["due"]])[0],
                "Delivered Date": _iso([item["completed"]])[0],
                "Report Week": _iso([item["updated"]])[0],
                "Commentary": profile["risk"] if item["category"] == "blocked" else "",
            })
    pd.DataFrame(rows).to_csv(path, index=False)


def write_smartsheet(profiles: list, frames: dict, path: Path) -> None:
    """An indented plan: one summary row per phase, then its tasks. Summary rows
    are what `is_leaf` exists to exclude - counting a phase and its tasks as
    separate scope would inflate the program by the number of phases."""
    rows = []
    row_id = 1
    for profile in profiles:
        items = frames[profile["name"]]
        for stream in profile["streams"]:
            stream_items = items[items["workstream"] == stream]
            if stream_items.empty:
                continue
            summary_pct = int(round(stream_items["reported_pct"].mean()))
            rows.append({
                "Program": profile["name"], "Row ID": row_id, "Outline Level": 1,
                "Task Name": stream, "Phase": stream, "Function": profile["domain"],
                "Assigned To": "", "Status": "In Progress", "% Complete": summary_pct,
                "Start": _iso([stream_items["created"].min()])[0],
                "Finish": _iso([stream_items["due"].max()])[0],
                "Completed On": "", "Modified": _iso([stream_items["updated"].max()])[0],
                "Duration (hrs)": int(stream_items["effort_hours"].sum()),
                "Predecessors": "",
            })
            parent_row = row_id
            row_id += 1
            for _, item in stream_items.iterrows():
                rows.append({
                    "Program": profile["name"], "Row ID": row_id, "Outline Level": 2,
                    "Task Name": item["title"], "Phase": stream, "Function": item["domain"],
                    "Assigned To": item["owner"], "Status": item["status"],
                    "% Complete": item["reported_pct"],
                    "Start": _iso([item["created"]])[0],
                    "Finish": _iso([item["due"]])[0],
                    "Completed On": _iso([item["completed"]])[0],
                    "Modified": _iso([item["updated"]])[0],
                    "Duration (hrs)": item["effort_hours"],
                    "Predecessors": parent_row if item["seq"] % 3 == 0 else "",
                })
                row_id += 1
    pd.DataFrame(rows).to_csv(path, index=False)


def write_trackwise(profiles: list, frames: dict, path: Path) -> None:
    rows = []
    for profile in profiles:
        for _, item in frames[profile["name"]].iterrows():
            rows.append({
                "Program": profile["name"],
                "Record ID": f"TW-{int(item['seq']):05d}",
                "Title": item["title"],
                "Phase": item["workstream"],
                "Site": item["domain"],
                "Record Owner": item["owner"],
                "Record State": item["status"],
                "Gate": f"Gate {1 + int(item['seq']) % 4}",
                "Opened": _iso([item["created"]])[0],
                "Target Close": _iso([item["due"]])[0],
                "Actual Close": _iso([item["completed"]])[0],
                "Last Action": _iso([item["updated"]])[0],
                "Effort (hrs)": item["effort_hours"],
            })
    pd.DataFrame(rows).to_csv(path, index=False)


# Attach rules for the two activity feeds that are not program-scoped at source.
# Real demand assignment groups and real agent sub-domains are pointed at the
# programs they plausibly serve, so "demand load by program" and "which programs
# are getting AI leverage" have something to measure. Editing these two dicts is
# how the team would re-point them once the real mapping is known.
DEMAND_GROUPS = {
    "Finance Digital Transformation": "Finance;#Support Enhancement Hours",
    "S4 WS 4A": "Manufacturing",
    "Commercial GCDH": "GOSC POD",
    "NextGen P&C Commercial": "GSR POD;#Global Region POD",
    "Kaika (Japan JDE)": "MEIC",
    "BI Platform Support": "AMPS;#TCS POD",
    "Regulatory Reporting Automation": "CTS POD",
}
AGENT_SUB_DOMAINS = {
    "Commercial GCDH": "GOSC",
    "NextGen P&C Commercial": "Commercial",
    "S4 WS 4A": "Manufacturing",
    "Regulatory Reporting Automation": "Regulatory",
    "Reltio - MDM": "MDM",
    "NextGen Trackwise": "Quality",
    "FieldLink": "GSR",
    "SAP GTS": "SAP",
    "BI Platform Support": "Enterprise",
}

SHAPE_FILES = {
    "jira": ("sap_delivery_jira.csv", write_jira),
    "servicenow": ("commercial_servicenow.csv", write_servicenow),
    "excel_tracker": ("s4_program_tracker.xlsx", write_excel_tracker),
    "status_report": ("apac_kaika_status.csv", write_status_report),
    "smartsheet": ("finance_ma_smartsheet.csv", write_smartsheet),
    "trackwise": ("quality_trackwise_export.csv", write_trackwise),
}
#: Regulatory Reporting gets its own Jira file to prove two exports of the same
#: shape, with different project keys, can coexist and stay separately attributed.
SEPARATE_FILES = {"Regulatory Reporting Automation": "regulatory_reporting_jira.csv"}


def _stable_index(value: str, modulus: int) -> int:
    """Deterministic across processes and runs, which `hash()` is not."""
    return zlib.crc32(value.encode("utf-8")) % modulus


def write_registry(profiles: list, path: Path) -> None:
    rows = []
    for profile in profiles:
        shape = profile["shape"]
        filename = SEPARATE_FILES.get(profile["name"], SHAPE_FILES[shape][0])
        rows.append({
            "program_id": slugify(profile["name"]),
            "name": profile["name"],
            "is_strategic": str(profile["strategic"]).lower(),
            "parent_program_id": profile.get("parent", ""),
            "portfolio": profile["portfolio"],
            "domain": profile["domain"],
            # crc32, not hash(): Python randomises string hashing per process,
            # so hash() gave a different sponsor on every run and broke the
            # reproducibility the --seed flag promises.
            "executive_sponsor": SPONSORS[_stable_index(profile["name"], len(SPONSORS))],
            "program_owner": OWNERS[_stable_index(profile["name"], len(OWNERS))],
            "delivery_lead": OWNERS[_stable_index(profile["name"] + "lead", len(OWNERS))],
            "phase": profile["phase"],
            "start_date": profile["start"],
            "target_date": profile["target"],
            "target_quarter": profile["quarter"],
            "budget_usd": profile["budget"],
            "spent_usd": profile["spent"],
            "source_system": {"jira": "Jira", "servicenow": "ServiceNow",
                              "excel_tracker": "Excel PM Tracker",
                              "status_report": "Status Report",
                              "smartsheet": "Smartsheet",
                              "trackwise": "TrackWise"}[shape],
            # Jira files host several programs, so they attach per row by project
            # key instead of by filename - otherwise the first program listed
            # would claim every issue in the file.
            "source_files": "" if shape == "jira" else filename,
            "jira_project_keys": profile.get("jira_key", ""),
            # Two kinds of group name land here: the ServiceNow export writes
            # "<program> POD" on its own tickets, and the real demand intake uses
            # the organisation's own group names. A program can answer to both.
            "demand_assignment_groups": ";#".join(
                [g for g in ([f"{profile['name']} POD"] if shape == "servicenow" else [])
                 + ([DEMAND_GROUPS[profile["name"]]] if profile["name"] in DEMAND_GROUPS else [])
                 if g]),
            "agent_sub_domains": AGENT_SUB_DOMAINS.get(profile["name"], ""),
            "key_risks": profile["risk"],
        })
    pd.DataFrame(rows).to_csv(path, index=False)


def enrich_agent_board(source: Path, destination: Path, rng: np.random.Generator,
                       today: pd.Timestamp) -> int:
    """Fill the AI/BI board fields that are blank in the real export.

    Status, ETA, Platform, Origin and Demand Intake Number are populated per
    agent from its own sub-domain and owner rather than uniformly, so the
    rollout funnel, time-to-live and demand-linkage metrics have something real
    to measure. Description and ownership are copied through untouched - the
    real file stays the source of truth for everything it actually records.
    """
    # The real export carries stray cp1252 bytes; the shared robust reader
    # handles that the same way ingestion does.
    board = read_csv_robust(source)
    n = len(board)

    # Sub-domains that have been running longest are further along; newer ones
    # cluster at the idea end. That is what makes the funnel informative.
    maturity = {"GOSC": 0.75, "Commercial": 0.62, "Manufacturing": 0.55, "Regulatory": 0.40,
                "GSR": 0.45, "MDM": 0.58, "Enterprise": 0.30, "Quality": 0.35, "SAP": 0.25}

    statuses, etas, platforms, origins, demand_numbers, created, updated, live = (
        [], [], [], [], [], [], [], [])
    for i, row in board.iterrows():
        score = maturity.get(str(row.get("Sub-Domain")).strip(), 0.35)
        score = float(np.clip(rng.normal(score, 0.18), 0.02, 0.98))
        if score > 0.86:
            stage = "Live"
        elif score > 0.72:
            stage = "UAT"
        elif score > 0.48:
            stage = "WIP"
        elif score > 0.24:
            stage = "Scoping"
        else:
            stage = "Idea"
        if rng.random() < 0.06:
            stage = "On Hold"
        statuses.append(stage)

        age = int(rng.integers(60, 620))
        start = today - timedelta(days=age)
        created.append(start.strftime("%Y-%m-%d"))
        if stage == "Live":
            went_live = start + timedelta(days=int(rng.integers(40, min(age, 400)) or 40))
            live.append(went_live.strftime("%Y-%m-%d"))
            etas.append(went_live.strftime("%Y-%m-%d"))
            updated.append(went_live.strftime("%Y-%m-%d"))
        else:
            live.append("")
            eta = today + timedelta(days=int(rng.integers(-40, 300)))
            etas.append(eta.strftime("%Y-%m-%d") if rng.random() < 0.78 else "")
            idle = int(rng.integers(120, 300)) if stage in ("Idea", "On Hold") else int(rng.integers(1, 70))
            updated.append((today - timedelta(days=idle)).strftime("%Y-%m-%d"))

        platforms.append(rng.choice(["Snowflake", "Databricks", "Power BI", "Tableau", "Azure OpenAI"],
                                    p=[0.34, 0.24, 0.18, 0.12, 0.12]))
        # Governance signal: only about a third of the board traces back to a
        # formal demand. The rest is self-originated, which is the point.
        from_demand = rng.random() < 0.34
        origins.append("Demand" if from_demand else "Self")
        demand_numbers.append(f"DMND{int(rng.integers(10000, 99999))}" if from_demand else "")

    board["Status"] = statuses
    board["ETA"] = etas
    board["Platform"] = platforms
    board["Origin"] = origins
    board["Demand Intake Number"] = demand_numbers
    board["Created"] = created
    board["Last Updated"] = updated
    board["Go Live Date"] = live
    board.to_csv(destination, index=False)
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--today", default=None,
                        help="Anchor date (YYYY-MM-DD). Output is reproducible for a given "
                             "seed and anchor; the default anchor is today, so the demo "
                             "portfolio always looks current.")
    parser.add_argument("--out", default=str(GENERATED_DIR))
    args = parser.parse_args()

    today = pd.Timestamp(args.today) if args.today else pd.Timestamp.now().normalize()
    rng = np.random.default_rng(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = {p["name"]: _draw_items(p, rng, today) for p in PROFILES}

    by_file: dict = {}
    for profile in PROFILES:
        filename = SEPARATE_FILES.get(profile["name"], SHAPE_FILES[profile["shape"]][0])
        by_file.setdefault((filename, profile["shape"]), []).append(profile)

    for (filename, shape), profiles in sorted(by_file.items()):
        writer = SHAPE_FILES[shape][1]
        writer(profiles, frames, out_dir / filename)
        total = sum(len(frames[p["name"]]) for p in profiles)
        print(f"  {filename:<34} {shape:<14} {len(profiles)} program(s), {total} items")

    write_registry(PROFILES, out_dir / "program_registry_generated.csv")
    print(f"  {'program_registry_generated.csv':<34} {'registry':<14} {len(PROFILES)} programs")

    real_board = Path(__file__).resolve().parent.parent / "data" / "raw" / "AI for BI Board.csv"
    if real_board.exists():
        count = enrich_agent_board(real_board, out_dir / "ai_bi_board_enriched.csv", rng, today)
        print(f"  {'ai_bi_board_enriched.csv':<34} {'board':<14} {count} agents enriched")

    strategic = sum(1 for p in PROFILES if p["strategic"])
    print(f"\n{len(PROFILES)} programs generated ({strategic} strategic, "
          f"{len(PROFILES) - strategic} standard) into {out_dir}")


if __name__ == "__main__":
    main()
