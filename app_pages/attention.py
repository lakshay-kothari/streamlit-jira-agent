"""Needs attention: one ranked list of what to do today.

Managers do not want four dashboards to correlate by eye. Everything that has
crossed a threshold - off-track programs, blocked work, aged demands, stalled
agents - is pulled into a single list ordered by severity, with the reason
spelled out and a route to the detail.

Thresholds all come from `config.METRIC_TARGETS`, so this page never invents its
own definition of "bad" - it surfaces the same judgements the KPI cards make.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.components import card_key, metric_row, page_header
from common.config import METRIC_TARGETS
from common.icons import icon
from common.theme import PANEL_KEY_PREFIX

programs = data_access.get_programs()
work_items = data_access.get_work_items()
demands = data_access.get_demands()
board = data_access.get_board_items()

page_header("Needs attention",
            "Everything across the portfolio that has crossed a threshold, ranked by "
            "severity. One list, not four dashboards to reconcile.")

now = pd.Timestamp.now()
scorecard = kpi.program_scorecard(programs, work_items)
items = kpi.attention_items(work_items, demands, board, scorecard, now=now)

SEVERITY_LABELS = {1: "Critical", 2: "High", 3: "Watch"}
SEVERITY_COLORS = {1: "red", 2: "orange", 3: "gray"}

if items.empty:
    st.success("Nothing has crossed a threshold. Every program is tracking to plan, no work "
               "is blocked past its limit, and no demand or agent has aged out.")
    st.stop()

critical = int((items["severity"] == 1).sum())
high = int((items["severity"] == 2).sum())

metric_row([
    mx.MetricResult(
        key="critical", label="Critical", value=float(critical), display=str(critical),
        question="What is failing right now and needs a decision today?",
        insight="Off-track programs and demands over a year old",
        target=0.0, target_display="none outstanding",
        status=mx.GOOD if critical == 0 else mx.BAD),
    mx.MetricResult(
        key="high", label="High", value=float(high), display=str(high),
        question="What will become critical if left another cycle?",
        insight="Blocked work and demands past their ageing threshold",
        target=0.0, target_display="none outstanding",
        status=mx.GOOD if high == 0 else mx.WATCH),
    mx.MetricResult(
        key="total_flags", label="Total flagged", value=float(len(items)),
        display=str(len(items)),
        question="How much of the portfolio is off its expected path?",
        insight=f"Across {items['area'].nunique()} activity areas"),
    mx.blocked_work(work_items, now),
])

st.caption(f"{icon('info')} Thresholds: blocked beyond "
           f"{METRIC_TARGETS['work_item_blocked_days']}d, demands open beyond "
           f"{METRIC_TARGETS['demand_aging_days']}d, agents idle beyond "
           f"{METRIC_TARGETS['agent_stalled_days']}d, schedule variance under "
           f"{METRIC_TARGETS['schedule_variance_off_track_pct']:.0f} points.")

areas = sorted(items["area"].unique())
chosen = st.segmented_control("Filter", ["All", *areas], default="All", key="attention_area")
view = items if chosen == "All" else items[items["area"] == chosen]

for severity, group in view.groupby("severity", sort=True):
    st.subheader(f"{icon('attention')} {SEVERITY_LABELS.get(severity, 'Other')} "
                 f"({len(group)})")
    for _, row in group.iterrows():
        with st.container(border=True,
                          key=card_key(PANEL_KEY_PREFIX, "row", str(row["item"]))):
            head, tail = st.columns([5, 1], vertical_alignment="center")
            with head:
                st.markdown(f"**{row['item']}**")
                st.caption(f"{row['issue']} · {row['detail']}")
            with tail:
                st.badge(row["area"], color=SEVERITY_COLORS.get(severity, "gray"))
