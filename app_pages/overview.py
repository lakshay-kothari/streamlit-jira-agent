"""Overview: the portfolio at VP altitude.

Five questions, five numbers. Every KPI here earns its place by informing a
decision a leader actually makes:

* Where do I intervene?          -> programs off track
* Will we make the year?         -> initiatives forecast to miss their date
* Are we taking on too much?     -> net flow across delivery and intake
* What is rotting?               -> aged open work and demands
* Are we spending ahead of pace? -> portfolio burn efficiency

What it deliberately no longer shows: "total tracked work items", "programs in
flight", "agents being built". Counts with no denominator and no baseline; none
of them changed anybody's mind about anything.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import flow_chart, health_matrix
from common.components import (activity_card, card_grid, insight_note, metric_row,
                               page_header, panel)
from common.config import ACTIVITIES, METRIC_TARGETS
from common.icons import icon

programs = data_access.get_programs()
work_items = data_access.get_work_items()
demands = data_access.get_demands()
board = data_access.get_board_items()

page_header("Overview",
            "The whole portfolio in five numbers - each one tied to a decision, "
            "a target, and the data that actually backs it.")

scorecard = kpi.program_scorecard(programs, work_items)
health = kpi.portfolio_health(scorecard)
delivery = mx.delivery_items(work_items)
strategic = scorecard[scorecard["is_strategic"]] if not scorecard.empty else scorecard
now = pd.Timestamp.now()

# --------------------------------------------------------------- the five ---
intervene = mx.MetricResult(
    key="off_track", label="Programs off track", value=float(health["off_track"]),
    display=str(health["off_track"]),
    question="Where do I need to intervene this week?",
    insight=f"{health['at_risk']} more at risk of {health['total']} programs",
    target=0.0, target_display="none off track",
    status=(mx.GOOD if health["off_track"] == 0
            else mx.WATCH if health["off_track"] <= 2 else mx.BAD),
)

slipping = strategic[strategic["forecast_slip_weeks"].notna()
                     & (strategic["forecast_slip_weeks"] > 0)] if not strategic.empty else strategic
measurable = strategic[strategic["forecast_slip_weeks"].notna()] if not strategic.empty else strategic
confidence = mx.MetricResult(
    key="delivery_confidence", label="Initiatives set to slip",
    value=float(len(slipping)), display=f"{len(slipping)} of {len(measurable)}",
    question="Will the strategic portfolio land on the dates it has committed to?",
    insight=(f"Worst case {slipping['forecast_slip_weeks'].max():.0f} weeks late"
             if len(slipping) else "Every measurable initiative is on target"),
    target=0.0, target_display="none forecast to slip",
    coverage_note=(f"{len(strategic) - len(measurable)} initiatives have too few dated "
                   "completions to forecast." if len(measurable) < len(strategic) else None),
    status=(mx.GOOD if len(slipping) == 0 else mx.WATCH if len(slipping) <= 2 else mx.BAD),
)

arrivals = pd.concat([delivery["created"], demands["created"]], ignore_index=True)
completions = pd.concat([delivery["completed"], demands["go_live_date"]], ignore_index=True)
flow = mx.net_flow(arrivals, completions, now=now)
flow.label = "Net flow"
flow.question = "Is the organisation taking on more work than it finishes?"

open_demands = demands[~demands["status_category"].isin(["Done", "Cancelled"])]
demand_ages = (now - open_demands["created"]).dt.days if not open_demands.empty else pd.Series(dtype=float)
aging_threshold = METRIC_TARGETS["demand_aging_days"]
aged_demands = int((demand_ages > aging_threshold).sum()) if not demand_ages.empty else 0
stale_work = mx.aging_work(delivery, now)
rotting = mx.MetricResult(
    key="rotting", label="Ageing work", value=float(aged_demands + (stale_work.value or 0)),
    display=mx.fmt_int(aged_demands + (stale_work.value or 0)),
    question="What is sitting untouched long enough that it is quietly failing?",
    insight=f"{aged_demands:,} demands over {aging_threshold}d, "
            f"{int(stale_work.value or 0):,} work items gone stale",
    target=0.0, target_display="nothing past its ageing threshold",
    status=stale_work.status,
)

portfolio_burn = mx.burn_efficiency(
    mx.delivery_items(work_items[work_items["program_id"].isin(strategic["program_id"])])
    if not strategic.empty else delivery,
    strategic["budget_usd"].sum(skipna=True) if not strategic.empty else None,
    strategic["spent_usd"].sum(skipna=True) if not strategic.empty else None,
)
portfolio_burn.label = "Spend vs progress"
portfolio_burn.question = "Is the strategic portfolio burning budget faster than it delivers?"

history = kpi.portfolio_history(delivery, weeks=26)
trends = {}
if not history.empty and len(history) > 3:
    trends["off_track"] = None  # health is not rewindable; no fabricated sparkline

metric_row([intervene, confidence, flow, rotting, portfolio_burn], trends=trends)

# The single most important sentence on the page, generated from the data.
if not scorecard.empty:
    worst = scorecard.iloc[0]
    if worst["health"] == "Off Track":
        insight_note(
            f"**{worst['name']} needs attention first.** It is {worst['schedule_variance']:+.0f} "
            f"points behind plan - {worst['pct_complete']:.0f}% of scope delivered against "
            f"{worst['pct_elapsed']:.0f}% of its window elapsed, with "
            f"{int(worst['blocked'])} items blocked.", tone="error")

left, right = st.columns([3, 2])
with left, panel("Delivery against plan", "health",
                 "Every program as one bubble, sized by scope. Below the dashed line is behind."):
    st.plotly_chart(health_matrix(scorecard), width="stretch", config={"displayModeBar": False})
with right, panel("Portfolio flow", "flow",
                  "Work arriving against work completed, across every program."):
    st.plotly_chart(flow_chart(kpi.monthly_flow(delivery), "month", ["created", "completed"]),
                    width="stretch", config={"displayModeBar": False})
    # The completed line can only plot work that recorded a completion date.
    # Saying so is the difference between an understated chart and a wrong one.
    done_items = delivery[delivery["status_category"] == "Done"]
    if not done_items.empty:
        dated = done_items["completed"].notna().mean()
        if dated < 0.9:
            st.caption(f"The completed line understates delivery: only "
                       f"{100 * dated:.0f}% of completed work records a completion date. "
                       f"See Data coverage.")

# ------------------------------------------------------------ activities ---
st.subheader(f"{icon('apps')} Activity areas")
st.caption("Click a card to open its dashboard.")

strategic_count = int(scorecard["is_strategic"].sum()) if not scorecard.empty else 0
blocked_total = int(scorecard["blocked"].sum()) if not scorecard.empty else 0
waste = kpi.demand_cancellation_waste(demands)
concentration = kpi.agent_owner_concentration(board)
live_agents = int((board["status"] == "Live").sum()) if "status" in board.columns else 0

card_metrics = {
    # Programs and Strategic initiatives share a denominator on purpose: the
    # cards should make the subset relationship obvious rather than imply two
    # separate portfolios.
    "programs": [("Programs", str(health["total"])),
                 ("Off track", str(health["off_track"])),
                 ("Blocked", f"{blocked_total:,}")],
    "strategic_initiatives": [("Of programs", f"{strategic_count}/{health['total']}"),
                              ("Set to slip", str(len(slipping))),
                              ("Burn", portfolio_burn.display)],
    "agents": [("Live", str(live_agents)),
               ("Top-2 load", mx.fmt_pct(concentration["share_pct"])),
               ("Stalled", str(len(kpi.agent_stalled(board, now=now))))],
    "demands": [("Open", f"{len(open_demands):,}"),
                ("Cancelled", mx.fmt_pct(waste["rate_pct"], 0)),
                ("Net flow", flow.display)],
}

with card_grid("activities"):
    for activity in ACTIVITIES:
        activity_card(
            key=activity["key"], label=activity["label"], icon_name=activity["icon"],
            tagline=activity["tagline"], page_path=activity["path"], live=activity["live"],
            metrics=card_metrics.get(activity["key"], []),
        )

st.caption(f"{icon('info')} Strategic initiatives are the {strategic_count} programs flagged "
           f"strategic out of {health['total']} - a subset, never a separate total.")
