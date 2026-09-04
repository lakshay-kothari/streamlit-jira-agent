"""The program registry: one row per program, strategic or not.

This is the answer to "all Strategic Initiatives are Programs, but not all
Programs are Strategic Initiatives". There is exactly one entity - a program -
and `is_strategic` is a boolean facet of it. The Programs page lists every row;
the Strategic initiatives page is the executive lens over the subset where
`is_strategic` is true. Because it is one table, a program is counted once and
the strategic count can never exceed the program count.

The registry also carries the **attach rules** that bind delivery work, demands
and agents to a program. No source system in this portfolio records which
program a row belongs to, so that mapping has to live somewhere the team owns:
here, in a CSV, rather than hard-coded in a parser.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.adapters.base import read_csv_robust, slugify

REGISTRY_FILENAMES = ("program_registry.csv", "program_registry_generated.csv")

#: Program id used for work that has not been attached to any program. Kept
#: explicit (rather than dropped or left null) so unattached volume is visible
#: and can be chased down, instead of quietly vanishing from portfolio totals.
UNATTACHED = "unattached"

PROGRAM_COLUMNS = [
    "program_id", "name", "is_strategic", "parent_program_id", "portfolio", "domain",
    "executive_sponsor", "program_owner", "delivery_lead", "phase",
    "start_date", "target_date", "target_quarter", "budget_usd", "spent_usd",
    "source_system", "source_files", "jira_project_keys",
    "demand_assignment_groups", "agent_sub_domains", "key_risks",
]

DATE_COLUMNS = ["start_date", "target_date"]
NUMERIC_COLUMNS = ["budget_usd", "spent_usd"]

#: Ordered lifecycle stages, shared by programs and the initiatives above them.
PHASE_ORDER = ["Discovery", "Planning", "Execution", "Stabilization", "Complete"]


def _split_rule(value) -> list:
    """Attach-rule cells hold several values in one string, delimited the same
    way Jira multi-selects are (`;#`), so a program can claim two Jira projects
    or three assignment groups without needing extra columns."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [part.strip() for part in str(value).split(";#") if part.strip()]


def empty_registry() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in PROGRAM_COLUMNS})


def load(*directories) -> pd.DataFrame:
    """Read every registry file found under `directories` and stack them. The
    hand-maintained registry and the generated one are separate files on
    purpose: deleting the generated data folder removes its programs cleanly."""
    frames = []
    for directory in directories:
        base = Path(directory)
        if not base.exists():
            continue
        for filename in REGISTRY_FILENAMES:
            path = base / filename
            if path.exists():
                frame = read_csv_robust(path)
                frame.columns = [str(c).strip() for c in frame.columns]
                frame["registry_file"] = path.name
                frames.append(frame)
    if not frames:
        return empty_registry()

    programs = normalize(pd.concat(frames, ignore_index=True))
    return merge_duplicates(programs)


def merge_duplicates(programs: pd.DataFrame) -> pd.DataFrame:
    """Combine rows describing the same program instead of discarding all but
    one. A program can legitimately be described in two places - the PMO
    register knows its sponsor and budget, the delivery registry knows which
    files carry its work - and dropping either would lose real information.
    First non-null wins per field, so earlier directories take precedence only
    where they actually populate a value."""
    if programs.empty:
        return programs.reset_index(drop=True)
    merged = (programs.groupby("program_id", sort=False, dropna=False)
                       .agg(lambda col: next((v for v in col if pd.notna(v) and v != ""), pd.NA)))
    merged = merged.reset_index()
    # groupby-agg collapses the boolean to object; a program flagged strategic
    # in any registry file is strategic.
    strategic = programs.groupby("program_id", sort=False, dropna=False)["is_strategic"].any()
    merged["is_strategic"] = merged["program_id"].map(strategic).fillna(False).astype(bool)
    for col in DATE_COLUMNS:
        merged[col] = pd.to_datetime(merged[col], errors="coerce")
    for col in NUMERIC_COLUMNS:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    return merged.reset_index(drop=True)


def normalize(programs: pd.DataFrame) -> pd.DataFrame:
    """Fill in missing columns and coerce types. Shared by `load` and by any
    caller turning another source (e.g. the PMO strategic register) into
    registry rows, so every path produces the same shape."""
    programs = programs.copy()
    for col in PROGRAM_COLUMNS:
        if col not in programs.columns:
            programs[col] = pd.NA

    programs["program_id"] = programs["program_id"].where(
        programs["program_id"].notna(), programs["name"].map(
            lambda v: slugify(v) if pd.notna(v) else None))
    programs["is_strategic"] = (
        programs["is_strategic"].astype("string").str.strip().str.lower()
        .isin(["true", "1", "yes", "y"]))
    for col in DATE_COLUMNS:
        programs[col] = pd.to_datetime(programs[col], errors="coerce")
    for col in NUMERIC_COLUMNS:
        programs[col] = pd.to_numeric(programs[col], errors="coerce")
    return programs


class Resolver:
    """Turns a source row into a program_id using the registry attach rules.

    Every lookup falls back to UNATTACHED rather than raising: a new export
    landing in data/raw/ before anyone has registered it should still load and
    be visible as unattached, not break the build.
    """

    def __init__(self, programs: pd.DataFrame):
        self.programs = programs
        self._by_file: dict = {}
        self._by_jira_key: dict = {}
        self._by_assignment_group: dict = {}
        self._by_agent_sub_domain: dict = {}
        self._by_name: dict = {}
        for _, row in programs.iterrows():
            pid = row["program_id"]
            self._by_name[str(row["name"]).strip().lower()] = pid
            for value in _split_rule(row.get("source_files")):
                self._by_file[value.lower()] = pid
            for value in _split_rule(row.get("jira_project_keys")):
                self._by_jira_key[value.upper()] = pid
            for value in _split_rule(row.get("demand_assignment_groups")):
                self._by_assignment_group[value.lower()] = pid
            for value in _split_rule(row.get("agent_sub_domains")):
                self._by_agent_sub_domain[value.lower()] = pid

    def by_source_file(self, filename: str) -> str:
        return self._by_file.get(str(filename).lower(), UNATTACHED)

    def by_name(self, name) -> str:
        if name is None or (isinstance(name, float) and pd.isna(name)):
            return UNATTACHED
        return self._by_name.get(str(name).strip().lower(), UNATTACHED)

    def by_jira_project_key(self, series: pd.Series) -> pd.Series:
        keys = series.astype("string").str.strip().str.upper()
        return keys.map(self._by_jira_key).fillna(UNATTACHED)

    def by_assignment_group(self, series: pd.Series) -> pd.Series:
        groups = series.astype("string").str.strip().str.lower()
        return groups.map(self._by_assignment_group).fillna(UNATTACHED)

    def by_agent_sub_domain(self, series: pd.Series) -> pd.Series:
        subs = series.astype("string").str.strip().str.lower()
        return subs.map(self._by_agent_sub_domain).fillna(UNATTACHED)
