"""Jira CSV export -> work_items.

Also the home of the hierarchy walk that recovers the **Domain** dimension.
Jira's `Custom field (Domain)` is empty on every row of the real export, but the
information is not actually missing - it is encoded in the issue tree. Top-level
`Initiative` issues in this project *are* the business domains (Finance, Supply
Chain, Quality, MDM, ...), with Epics as workstreams beneath them. Walking
`parent_key` upward recovers domain and workstream for ~2/3 of issues without
anyone touching Jira.

The remaining third genuinely is not domain-organized - those epics are grouped
by *source system* and *release* instead (`DIH to DBX - Release 2 - Source GTS`).
They are labelled `Unmapped` rather than forced into a domain they do not belong
to; the Data coverage page reports the real percentage.
"""
from __future__ import annotations

import re

import pandas as pd

from common.adapters.base import (
    coalesce_candidates,
    finalize,
    normalize_status,
    parse_jira_datetime,
    read_csv_robust,
)

SOURCE_SYSTEM = "Jira"

DUE_DATE_CANDIDATES = [
    "Due date", "Custom field (Due Date)", "Custom field (Due Date )",
    "Custom field (Target Due Date)", "Custom field (Target Due Date )",
    "Custom field (Revised Due Date)", "Custom field (Target Deployment Date)",
]
STORY_POINT_CANDIDATES = ["Custom field (Story Points)", "Custom field (Story point estimate)"]
SOLUTION_ARCHITECT_CANDIDATES = ["Custom field (Solution Architect)", "Custom field (Data Architect)"]
DOMAIN_CANDIDATES = ["Custom field (Domain)"]

UNMAPPED = "Unmapped"
#: An Initiative heading at least this many issues is treated as a real grouping
#: rather than a mis-typed task, which is how junk like "Code movement to QA"
#: (filed as an Initiative) is kept out of the domain vocabulary.
MIN_DOMAIN_DESCENDANTS = 5
MAX_DOMAIN_WORDS = 4
MAX_DOMAIN_CHARS = 45
#: Initiatives that describe a *programme* rather than a domain. Their children
#: carry the real domain, so the walk must not stop at them.
NON_DOMAIN_INITIATIVES = {"Data Platform Modernization", "Platform Migration of DIH to Databricks"}


def _ancestor_chains(df: pd.DataFrame) -> dict:
    """key -> [(issue_type, summary), ...] from the issue itself up to its root.
    Cycle-safe: a key already seen on the way up terminates the walk."""
    lookup = {
        str(k): (str(t) if pd.notna(t) else "", str(s) if pd.notna(s) else "",
                 str(p) if pd.notna(p) else None)
        for k, t, s, p in zip(df["issue_key"], df["issue_type"], df["summary"], df["parent_key"])
    }
    chains = {}
    for key in lookup:
        chain, seen, cur = [], set(), key
        while cur in lookup and cur not in seen:
            seen.add(cur)
            item_type, summary, parent = lookup[cur]
            chain.append((item_type, summary))
            if not parent or parent not in lookup:
                break
            cur = parent
        chains[key] = chain
    return chains


def _domain_vocabulary(chains: dict) -> list:
    """The project's own domain names, learned from the data rather than
    hard-coded: Initiative summaries that read like a domain and head enough
    work to actually be one."""
    counts: dict = {}
    for chain in chains.values():
        for item_type, summary in chain:
            if item_type == "Initiative" and summary:
                counts[summary] = counts.get(summary, 0) + 1
    vocab = [
        name for name, n in counts.items()
        if n >= MIN_DOMAIN_DESCENDANTS
        and len(name.split()) <= MAX_DOMAIN_WORDS
        and len(name) < MAX_DOMAIN_CHARS
        and name not in NON_DOMAIN_INITIATIVES
        and "test for" not in name.lower()
    ]
    return sorted(vocab, key=len, reverse=True)


def _resolve_domain(chain: list, vocab: list) -> str:
    """Nearest Initiative ancestor that names a domain; failing that, the same
    vocabulary matched against the epic names in the chain - which is how
    "DIH to DBX - Supply Chain Domain" resolves to Supply Chain."""
    for item_type, summary in chain:
        if item_type == "Initiative" and summary in vocab:
            return summary
    text = " | ".join(s.lower() for _, s in chain)
    for name in vocab:
        head = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()[0]
        if len(head) <= 3:
            if re.search(r"\b" + re.escape(head) + r"\b", text):
                return name
        elif head in text:
            return name
    return UNMAPPED


def _resolve_workstream(chain: list):
    """The outermost Epic in the chain - the mid-level grouping a delivery lead
    actually manages. Falls back to the root summary when there is no Epic."""
    epics = [s for t, s in chain if t == "Epic" and s]
    if epics:
        return epics[-1]
    return chain[-1][1] if chain else None


def parse(path, program_id: str):
    """Returns (work_items, issues_detail). The second frame keeps the
    Jira-specific columns the Programs page still uses for its drill-downs."""
    raw = read_csv_robust(path, dtype="string", keep_default_na=True, low_memory=False)

    detail = pd.DataFrame(index=raw.index)
    detail["issue_key"] = raw.get("Issue key")
    detail["issue_id"] = raw.get("Issue id")
    detail["summary"] = raw.get("Summary")
    detail["issue_type"] = raw.get("Issue Type")
    detail["status"] = raw.get("Status")
    detail["project_key"] = raw.get("Project key")
    detail["project_name"] = raw.get("Project name")
    detail["priority"] = raw.get("Priority")
    detail["resolution"] = raw.get("Resolution")
    detail["assignee"] = raw.get("Assignee")
    detail["reporter"] = raw.get("Reporter")
    detail["creator"] = raw.get("Creator")
    detail["parent_key"] = raw.get("Parent key")
    detail["parent_summary"] = raw.get("Parent summary")
    detail["team_name"] = raw.get("Team Name")
    detail["sprint"] = coalesce_candidates(raw, ["Sprint"])
    detail["solution_architect"] = coalesce_candidates(raw, SOLUTION_ARCHITECT_CANDIDATES)
    detail["story_points"] = pd.to_numeric(
        coalesce_candidates(raw, STORY_POINT_CANDIDATES), errors="coerce")

    detail["created"] = parse_jira_datetime(raw.get("Created", pd.Series(dtype="string")))
    detail["updated"] = parse_jira_datetime(raw.get("Updated", pd.Series(dtype="string")))
    detail["resolved"] = parse_jira_datetime(raw.get("Resolved", pd.Series(dtype="string")))
    detail["due_date"] = parse_jira_datetime(coalesce_candidates(raw, DUE_DATE_CANDIDATES))

    for col in ("Original estimate", "Remaining Estimate", "Time Spent"):
        detail[col.lower().replace(" ", "_") + "_sec"] = pd.to_numeric(raw.get(col), errors="coerce")
    detail["estimate_hours"] = detail["original_estimate_sec"] / 3600.0
    detail.loc[detail["estimate_hours"].isna(), "estimate_hours"] = \
        detail["remaining_estimate_sec"] / 3600.0

    # Jira's own Status Category is only a *fallback* for statuses the shared
    # patterns miss: it maps Descoped to Done, which is the exact conflation
    # this taxonomy exists to undo.
    detail["status_category"] = normalize_status(
        detail["status"], raw.get("Status Category", pd.Series(dtype="string")))

    chains = _ancestor_chains(detail)
    vocab = _domain_vocabulary(chains)
    keys = detail["issue_key"].astype(str)
    explicit = coalesce_candidates(raw, DOMAIN_CANDIDATES)
    derived = keys.map(lambda k: _resolve_domain(chains.get(k, []), vocab))
    detail["domain"] = explicit.where(explicit.notna(), derived)
    detail["workstream"] = keys.map(lambda k: _resolve_workstream(chains.get(k, [])))
    detail["program_id"] = program_id
    detail["program_name"] = detail["project_name"]
    source_name = getattr(path, "name", str(path))
    detail["source_file"] = source_name

    # Epics and Initiatives are containers, not deliverables: counting them
    # alongside their own children would double count the same scope.
    parent_keys = set(detail["parent_key"].dropna().astype(str))
    work = pd.DataFrame({
        "program_id": program_id,
        "item_key": detail["issue_key"],
        "title": detail["summary"],
        "item_type": detail["issue_type"],
        "workstream": detail["workstream"],
        "domain": detail["domain"],
        "owner": detail["assignee"],
        "status_raw": detail["status"],
        "status_category": detail["status_category"],
        "priority": detail["priority"],
        "created": detail["created"],
        "started": pd.NaT,
        "due_date": detail["due_date"],
        "completed": detail["resolved"],
        "updated": detail["updated"],
        "effort_hours": detail["estimate_hours"],
        "is_leaf": ~keys.isin(parent_keys),
    })
    return finalize(work, SOURCE_SYSTEM, source_name), detail
