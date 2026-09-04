"""Team & workload: who is carrying what, across every program and the board.

Two charts were removed here rather than left blank. "Open workload by solution
architect" read from a field that is null on all 10,000 rows of the real export,
and the team-allocation donut from one null on 9,994 of them. Both now appear on
the Data coverage page as fields to populate, which is the only thing that would
have made them work.

What replaces them is the question those charts were reaching for: is the load
spread, or is it resting on a handful of people?
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import bar_chart, stacked_status_bar
from common.components import insight_note, metric_row, page_header, panel

programs = data_access.get_programs()
work_items = data_access.get_work_items()
board = data_access.get_board_items()

page_header("Team & workload",
            "Where the open work sits, and how concentrated it is on individuals.")

if work_items.empty and board.empty:
    st.info("No data loaded yet.")
    st.stop()

name_by_id = dict(zip(programs["program_id"], programs["name"])) if not programs.empty else {}
options = sorted({name_by_id.get(p, p) for p in work_items["program_id"].dropna().unique()})
chosen = st.multiselect("Filter by program", options, default=[], key="team_program_filter",
                        placeholder="All programs")
if chosen:
    ids = [pid for pid, name in name_by_id.items() if name in chosen] or chosen
    scoped = work_items[work_items["program_id"].isin(ids)]
else:
    scoped = work_items

delivery = mx.delivery_items(scoped)
open_items = delivery[delivery["status_category"].isin(kpi.OPEN_STATUSES)]
owners = open_items["owner"].dropna() if not open_items.empty else pd.Series(dtype=object)

top_share = None
if not owners.empty:
    tally = owners.value_counts()
    top_share = round(100 * tally.head(5).sum() / len(owners), 1)

concentration = mx.MetricResult(
    key="load_concentration", label="Top-5 share of open work",
    value=top_share, display=mx.fmt_pct(top_share),
    question="Is the open workload spread, or resting on a handful of people?",
    insight=(f"{owners.nunique()} people hold {len(owners):,} owned open items"
             if not owners.empty else None),
    target=50.0, target_display="under 50%",
    status=mx.band(top_share, 50.0, "lower_better"),
)

metric_row([
    mx.MetricResult(
        key="open_items", label="Open work items", value=float(len(open_items)),
        display=mx.fmt_int(len(open_items)),
        question="How much work is currently in flight across the selected programs?",
        insight=f"{int((open_items['status_category'] == 'Blocked').sum()):,} of it blocked"
                if not open_items.empty else None),
    concentration,
    mx.unassigned_work(scoped),
    mx.aging_work(scoped),
    mx.blocked_work(scoped),
])

if concentration.status == mx.BAD and top_share:
    insight_note(
        f"**Open work is concentrated.** Five people hold {top_share:.0f}% of everything "
        f"currently in flight. Rebalancing is usually faster than hiring, and it is the "
        f"lever available this quarter.", tone="warning")

left, right = st.columns(2)
with left, panel("Open work by owner", "users",
                 "Top 15. A steep drop-off after the first few bars is a rebalancing signal."):
    st.plotly_chart(bar_chart(kpi.owner_workload(scoped, top_n=15), "owner", "count"),
                    width="stretch", config={"displayModeBar": False})
with right, panel("AI/BI board by owner", "bot",
                  "The board is a second, invisible workload on the same people."):
    st.plotly_chart(bar_chart(kpi.agent_breakdown(board, "owner", top_n=15), "owner", "count"),
                    width="stretch", config={"displayModeBar": False})

with panel("Open work by program", "explore",
           "Which programs the in-flight load actually belongs to."):
    scoped_named = scoped.copy()
    scoped_named["program"] = scoped_named["program_id"].map(
        lambda p: name_by_id.get(p, "Unattached"))
    st.plotly_chart(stacked_status_bar(kpi.status_by_dimension(scoped_named, "program"),
                                       "program", horizontal=True),
                    width="stretch", config={"displayModeBar": False})

blocked, stale, unowned = st.tabs(["Blocked", "Stale", "Unowned"])
with blocked:
    st.caption("Work waiting on somebody else, longest first.")
    st.dataframe(kpi.blocked_table(scoped, limit=300), width="stretch", hide_index=True)
with stale:
    st.caption("Open work with no movement past the staleness threshold.")
    st.dataframe(kpi.stale_table(scoped, limit=300), width="stretch", hide_index=True)
with unowned:
    st.caption("Open work with nobody accountable for it.")
    unassigned = open_items[open_items["owner"].isna()]
    cols = [c for c in ["item_key", "title", "status_raw", "workstream", "program_id"]
            if c in unassigned.columns]
    st.dataframe(unassigned[cols], width="stretch", hide_index=True)
