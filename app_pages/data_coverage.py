"""Data coverage: which metrics you can trust, and what to fix to earn the rest.

Eight charts used to render empty because the fields behind them are not
populated at source - Domain on every Jira issue, ETA on every agent, hours
estimates on 99% of work. Those charts are gone. This page replaces them with
the thing that is actually actionable: the field, how complete it is, and the
metric that cannot be computed until somebody fills it in.

It also reports source freshness, because a stale export and a stalled team look
identical on every other page.
"""
from __future__ import annotations

import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import bar_chart
from common.components import insight_note, metric_row, page_header, panel

work_items = data_access.get_work_items()
demands = data_access.get_demands()
board = data_access.get_board_items()
programs = data_access.get_programs()
meta = data_access.get_programs_meta()

page_header("Data coverage",
            "How far each metric can be trusted, and which unpopulated field is "
            "standing between you and the ones that are missing.")

coverage = kpi.field_coverage({"work_items": work_items, "demands": demands,
                               "board_items": board})
freshness = kpi.source_freshness(work_items)

if coverage.empty:
    st.info("No data loaded yet.")
    st.stop()

unreliable = coverage[coverage["band"] == "Unreliable"]
partial = coverage[coverage["band"] == "Partial"]
good = coverage[coverage["band"] == "Good"]

metric_row([
    mx.MetricResult(
        key="trusted", label="Fields fully usable", value=float(len(good)),
        display=f"{len(good)} of {len(coverage)}",
        question="How many metric-critical fields are populated well enough to rely on?",
        insight=f"{len(partial)} partial, {len(unreliable)} effectively empty",
        target=float(len(coverage)), target_display="all of them",
        status=mx.band(len(good), len(coverage) * 0.8, "higher_better")),
    mx.MetricResult(
        key="blocked_metrics", label="Metrics blocked", value=float(len(unreliable)),
        display=str(len(unreliable)),
        question="How many views cannot be shown at all until a field is populated?",
        insight=(f"Including: {unreliable.iloc[0]['enables']}" if not unreliable.empty
                 else "Nothing is blocked"),
        target=0.0, target_display="none blocked",
        status=mx.GOOD if unreliable.empty else mx.BAD),
    mx.MetricResult(
        key="sources", label="Sources loaded", value=float(len(freshness)),
        display=str(len(freshness)),
        question="How many systems is this portfolio being assembled from?",
        insight=f"{freshness['source_system'].nunique()} distinct tools"
                if not freshness.empty else None),
    mx.data_freshness(work_items),
])

if not unreliable.empty:
    worst = unreliable.iloc[0]
    insight_note(
        f"**{worst['field']}** is populated on {worst['coverage_pct']:.0f}% of "
        f"`{worst['table']}` rows, which is why *{worst['enables'].lower()}* is unavailable. "
        f"This is a source-system fix, not a dashboard one - populating the field turns the "
        f"view on with no code change.", tone="warning")

with panel("Field completeness", "coverage",
           "Sorted worst first. Enables is the metric you get back by populating it."):
    st.dataframe(
        coverage.rename(columns={"table": "Table", "field": "Field",
                                 "coverage_pct": "Coverage", "band": "Band",
                                 "enables": "Enables", "rows": "Rows"}),
        width="stretch", hide_index=True,
        column_config={"Coverage": st.column_config.ProgressColumn(
            "Coverage", min_value=0, max_value=100, format="%.0f%%")})

left, right = st.columns([2, 3])
with left, panel("Coverage by field", "bar_chart"):
    st.plotly_chart(bar_chart(coverage.rename(columns={"coverage_pct": "count"}),
                              "field", "count"),
                    width="stretch", config={"displayModeBar": False})
with right, panel("Source freshness", "source",
                  "Days since each source last showed any activity. A stale export drags "
                  "every rate-based metric toward zero, which reads as a stalled team."):
    st.dataframe(
        freshness.rename(columns={"source_file": "Source", "source_system": "System",
                                  "rows": "Rows", "last_activity": "Last activity",
                                  "days_stale": "Days stale"}),
        width="stretch", hide_index=True)

with panel("What loaded", "folders",
           "Every file discovered under data/raw/ and data/raw/generated/, and the "
           "adapter that claimed it."):
    if meta.empty:
        st.caption("No source metadata recorded.")
    else:
        st.dataframe(meta.rename(columns={"source_file": "File", "kind": "Parsed as",
                                          "row_count": "Rows", "detail": "Detail"}),
                     width="stretch", hide_index=True)

    unattached = int((work_items["program_id"] == "unattached").sum()) if not work_items.empty else 0
    if unattached:
        st.caption(f"{unattached:,} rows are not attached to any program. Add an attach rule "
                   f"(`jira_project_keys`, `demand_assignment_groups`, `agent_sub_domains`) to "
                   f"a row in the program registry to bring them into portfolio totals.")
