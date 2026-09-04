"""Demands: the incoming business-ask queue, measured as a flow system.

The intake export carries four real stage timestamps, which makes this the one
place in the app where a bottleneck can be identified rather than guessed. The
page is built around four questions a leader actually has:

1. Are we keeping up?          -> intake vs completion, and net flow
2. Where does it get stuck?    -> stage cycle times against their SLA
3. What is it costing us?      -> cancellation rate and the effort behind it
4. Why are we late?            -> delay reasons and the approval backlog

The old page answered none of these: it showed "% complete" over a queue that
never completes, a raw cancelled count, and an average cycle time computed over
a biased quarter of the rows.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import bar_chart, flow_chart, target_bar_chart
from common.components import (drill_caption, filter_chip_row, insight_note, metric_row,
                               page_header, panel, card_key)
from common.theme import PANEL_KEY_PREFIX
from common.config import METRIC_TARGETS
from common.icons import icon

demands = data_access.get_demands()
programs = data_access.get_programs()

page_header("Demands",
            "The incoming business-ask queue, measured as a flow system: what arrives, "
            "where it stalls, and what the stalls cost.")

if demands.empty:
    st.info("No demands loaded yet - drop the Demand Intake export into data/raw/ and rebuild.")
    st.stop()

FILTER_DIMENSIONS = [
    ("status_category", "Status", "bar_chart", kpi.demand_status_category_breakdown),
    ("request_type", "Request type", "stacks", kpi.demand_request_type_breakdown),
    ("assignment_group", "Assignment group", "users", kpi.demand_assignment_group_breakdown),
    ("team_required", "Team required", "explore", kpi.demand_team_breakdown),
]

active_filters = {key: st.query_params[key] for key, *_ in FILTER_DIMENSIONS
                  if key in st.query_params}


def _apply(df: pd.DataFrame, exclude: str | None = None) -> pd.DataFrame:
    """All active filters except `exclude`. Substring matching, because Request
    type and Team required hold several tags in one delimited string."""
    out = df
    for key, value in active_filters.items():
        if key == exclude or key not in out.columns:
            continue
        out = out[out[key].astype(str).str.contains(value, regex=False, na=False)]
    return out


filtered = _apply(demands)
now = pd.Timestamp.now()

# ------------------------------------------------------------------- KPIs ---
stage_times = kpi.demand_stage_times(filtered)
bottleneck = kpi.demand_bottleneck(stage_times)
waste = kpi.demand_cancellation_waste(filtered)
open_demands = filtered[~filtered["status_category"].isin(["Done", "Cancelled"])]

flow = mx.net_flow(filtered["created"], filtered["go_live_date"], now=now)

end_to_end = (filtered[filtered["go_live_date"].notna() & filtered["created"].notna()]
              .pipe(lambda d: (d["go_live_date"] - d["created"]).dt.days))
lead_time = mx.MetricResult(
    key="lead_time", label="Lead time (median)",
    value=float(end_to_end.median()) if not end_to_end.empty else None,
    display=mx.fmt_days(end_to_end.median() if not end_to_end.empty else None),
    question="How long does a business ask take from raised to live?",
    insight=(f"85th percentile {end_to_end.quantile(0.85):.0f}d" if not end_to_end.empty else None),
    target=float(METRIC_TARGETS["demand_end_to_end_days"]),
    target_display=f"under {METRIC_TARGETS['demand_end_to_end_days']}d",
    coverage_pct=round(100 * len(end_to_end) / len(filtered), 1) if len(filtered) else 0.0,
    coverage_note=(f"Measured on the {len(end_to_end):,} demands that record a go-live date."
                   if len(end_to_end) < len(filtered) else None),
    status=mx.band(float(end_to_end.median()) if not end_to_end.empty else None,
                   float(METRIC_TARGETS["demand_end_to_end_days"]), "lower_better"),
)

ages = ((now - open_demands["created"]).dt.days if not open_demands.empty
        else pd.Series(dtype=float))
aging_threshold = METRIC_TARGETS["demand_aging_days"]
backlog_age = mx.MetricResult(
    key="backlog_age", label="Open backlog", value=float(len(open_demands)),
    display=mx.fmt_int(len(open_demands)),
    question="How big is the queue, and how long has it been waiting?",
    insight=(f"Median age {ages.median():.0f}d, oldest {ages.max():.0f}d"
             if not ages.empty else None),
    target=float(aging_threshold), target_display=f"nothing older than {aging_threshold}d",
    status=mx.band(float(ages.median()) if not ages.empty else None,
                   float(aging_threshold), "lower_better"),
)

cancellation = mx.MetricResult(
    key="cancellation", label="Cancellation rate", value=waste["rate_pct"],
    display=mx.fmt_pct(waste["rate_pct"], 1),
    question="How much intake effort goes into work that never ships?",
    insight=(f"{waste['cancelled']:,} cancelled, ~{waste['wasted_hours']:,.0f} estimated hours"
             if waste["wasted_hours"] else f"{waste['cancelled']:,} cancelled"),
    target=float(METRIC_TARGETS["demand_cancellation_rate_pct"]),
    target_display=f"under {METRIC_TARGETS['demand_cancellation_rate_pct']:.0f}%",
    status=mx.band(waste["rate_pct"], METRIC_TARGETS["demand_cancellation_rate_pct"],
                   "lower_better"),
)

bottleneck_metric = mx.MetricResult(
    key="bottleneck", label="Slowest stage",
    display=bottleneck["stage"] if bottleneck else "-",
    question="Which stage of intake is furthest past its service level?",
    insight=(f"{bottleneck['median_days']:.0f}d median against a "
             f"{bottleneck['target_days']:.0f}d target" if bottleneck else None),
    value=bottleneck["ratio"] if bottleneck else None,
    target=1.0, target_display="within its SLA",
    status=mx.band(bottleneck["ratio"] if bottleneck else None, 1.0, "lower_better"),
)

metric_row([flow, backlog_age, bottleneck_metric, lead_time, cancellation])

if flow.value and flow.value > 1.15:
    insight_note(
        f"**The queue is growing.** {flow.insight} - a net "
        f"{flow.detail['arrived'] - flow.detail['completed']:,} demands added in "
        f"{flow.detail['days']} days. No amount of prioritisation closes a gap that "
        f"sits in intake capacity rather than delivery speed.", tone="warning")

filter_chip_row(active_filters)

# ------------------------------------------------------------------ flow ---
with panel("Intake against completion", "flow",
            "The gap between the lines is the backlog changing. Cancellations are "
            "shown separately because they close a demand without delivering it."):
    st.plotly_chart(flow_chart(kpi.demand_monthly_flow(filtered), "month",
                               ["created", "completed", "cancelled"]),
                    width="stretch", config={"displayModeBar": False})

left, right = st.columns(2)
with left, panel("Where demands wait", "schedule",
                  "Median days per stage against its target (the marker). Red bars are "
                  "past their service level."):
    st.plotly_chart(target_bar_chart(stage_times, "stage", "median_days", "target_days"),
                    width="stretch", config={"displayModeBar": False})
    if bottleneck:
        st.caption(f"**{bottleneck['stage']}** is the constraint at "
                   f"{bottleneck['ratio']:.1f}x its target. Everything downstream inherits "
                   f"that delay regardless of how fast delivery runs.")
with right, panel("Ageing of the open queue", "trend",
                   "A distribution rather than an average - the long tail is where "
                   "requestors lose confidence."):
    st.plotly_chart(bar_chart(kpi.demand_aging(filtered), "bucket", "count", horizontal=False),
                    width="stretch", config={"displayModeBar": False})

# --------------------------------------------------------------- why late ---
left, right = st.columns(2)
with left, panel("Why demands are late", "warning",
                  "The intake process captures a delay reason on every slipped demand. "
                  "It has never been shown anywhere until now."):
    delays = kpi.demand_delay_reasons(filtered)
    if delays.empty:
        st.caption("No delay reasons recorded on the demands in this view.")
    else:
        st.plotly_chart(bar_chart(delays, "delay_type", "count"),
                        width="stretch", config={"displayModeBar": False})
with right, panel("Investment council backlog", "approval",
                   "Where demands sit in the approval flow. A large pending queue is a "
                   "governance constraint, not a delivery one."):
    approvals = kpi.demand_approval_backlog(filtered)
    st.plotly_chart(bar_chart(approvals, "ic_approval_status", "count"),
                    width="stretch", config={"displayModeBar": False})
    if not approvals.empty:
        pending = approvals[approvals["ic_approval_status"].str.contains(
            "pending", case=False, na=False)]["count"].sum()
        if pending:
            st.caption(f"{pending:,} of {len(filtered):,} demands are awaiting review "
                       f"({100 * pending / len(filtered):.0f}% of the queue).")

with panel("Demand load by program", "folders",
            "Which programs the intake is actually landing on - the link between the "
            "queue and the portfolio it feeds."):
    st.plotly_chart(bar_chart(kpi.demand_load_by_program(filtered, programs), "program", "count"),
                    width="stretch", config={"displayModeBar": False})

# ----------------------------------------------------------- drill-downs ---
st.subheader(f"{icon('explore')} Break the queue down")
st.caption("Click a bar to filter every panel on this page.")
grid = st.columns(2)
for i, (key, title, icon_name, breakdown_fn) in enumerate(FILTER_DIMENSIONS):
    with grid[i % 2], panel(title, icon_name):
        drill_caption()
        counts = breakdown_fn(_apply(demands, exclude=key))
        col = counts.columns[0] if not counts.empty else key
        fig = bar_chart(counts, col, "count", highlight=active_filters.get(key))
        event = st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                                on_select="rerun", selection_mode="points",
                                key=f"demands_chart_{key}")
        if event.selection.points:
            clicked = event.selection.points[0].get("y")
            if clicked is not None and str(clicked) != active_filters.get(key):
                st.query_params[key] = str(clicked)
                st.rerun()

oldest, everything = st.tabs(["Oldest open demands", "All demands"])
with oldest:
    st.caption("Demands carry no due date, so age since intake is the only honest measure "
               "of lateness. Oldest first.")
    st.dataframe(kpi.demand_oldest_open(filtered), width="stretch", hide_index=True)
with everything:
    show_cols = [c for c in ["demand_key", "title", "requestor", "request_type", "status",
                             "assignment_group", "solution_architect", "created"]
                 if c in filtered.columns]
    table_event = st.dataframe(filtered[show_cols], width="stretch", hide_index=True,
                               on_select="rerun", selection_mode="single-row",
                               key="demands_table")
    if table_event.selection.rows:
        row = filtered.iloc[table_event.selection.rows[0]]
        with st.container(border=True,
                          key=card_key(PANEL_KEY_PREFIX, "plain", "demand_detail")):
            st.markdown(f"#### {icon('demands')} {row.get('title') or row.get('demand_key')}")
            st.write(row.get("description") or "No description provided.")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Requestor", row.get("requestor") or "Unknown")
            d2.metric("Status", row.get("status") or "-")
            d3.metric("Solution architect", row.get("solution_architect") or "Unassigned")
            d4.metric("Assignment group", row.get("assignment_group") or "-")
