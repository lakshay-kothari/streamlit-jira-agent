"""Strategic initiatives: the strategic subset of programs, at sponsor altitude.

This page does not read a table of its own. It reads the same program registry
the Programs page reads, filtered to `is_strategic` - which is why an initiative
can never disagree with the program underneath it, and why the initiative count
is always a subset of the program count rather than a parallel total.

Every progress number here is **derived** from the linked delivery work. The
PMO register's hand-typed "% Complete" is deliberately not shown: a number
nobody can trace is not a status, it is an opinion.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import (bar_chart, flow_chart, forecast_timeline, health_matrix,
                           stacked_status_bar)
from common.components import (breadcrumb_back, card_grid, initiative_card, insight_note,
                               metric_row, page_header, panel)
from common.icons import icon

programs = data_access.get_programs()
work_items = data_access.get_work_items()
strategic = data_access.get_strategic_initiatives()
scorecard = kpi.program_scorecard(strategic, work_items)


def _children(program_id: str) -> pd.DataFrame:
    """Programs nested under this initiative (e.g. S4 WS 4A under S4
    Modernization). The registry supports one level of nesting so a workstream
    can be tracked in its own right without leaving the portfolio."""
    if programs.empty or "parent_program_id" not in programs.columns:
        return programs.iloc[0:0]
    return programs[programs["parent_program_id"] == program_id]


def _render_detail(program: pd.Series, items: pd.DataFrame) -> None:
    breadcrumb_back("Strategic initiatives", param="initiative")
    page_header(program["name"], program.get("key_risks") or "Strategic initiative.")

    with st.container(horizontal=True):
        st.badge("Strategic initiative", color="violet")
        for label, value in (("Sponsor", program.get("executive_sponsor")),
                             ("Owner", program.get("program_owner")),
                             ("Phase", program.get("phase")),
                             ("Target", program.get("target_quarter"))):
            if value and not pd.isna(value):
                st.badge(f"{label}: {value}", color="gray")

    variance = mx.schedule_variance(items, program.get("start_date"), program.get("target_date"))
    confidence = mx.delivery_confidence(items, program.get("target_date"))
    burn = mx.burn_efficiency(items, program.get("budget_usd"), program.get("spent_usd"))
    metric_row([mx.pct_complete(items), variance, confidence, burn, mx.blocked_work(items)])

    if burn.status == "bad" and burn.value:
        insight_note(
            f"**Spend is outrunning delivery.** {burn.insight} - every point of progress is "
            f"costing {burn.value:.2f} points of budget. At this ratio the initiative needs "
            f"{burn.value:.0%} of its remaining budget to finish its remaining scope.",
            tone="warning")

    left, right = st.columns([3, 2])
    with left, panel("Delivery flow", "flow",
                      "Scope arriving against scope delivered, monthly."):
        st.plotly_chart(flow_chart(kpi.monthly_flow(items), "month", ["created", "completed"]),
                        width="stretch", config={"displayModeBar": False})
    with right, panel("Where the money went", "budget"):
        budget = program.get("budget_usd")
        spent = program.get("spent_usd")
        if budget and not pd.isna(budget):
            st.progress(min(float(spent or 0) / float(budget), 1.0),
                        text=f"{mx.fmt_money_md(spent)} of {mx.fmt_money_md(budget)} spent")
            completion = mx.pct_complete(items).value or 0
            st.progress(min(completion / 100, 1.0), text=f"{completion:.0f}% of scope delivered")
            st.caption("The gap between these two bars is the burn-efficiency number above.")
        else:
            st.caption("No budget recorded for this initiative.")

    with panel("Progress by domain", "explore"):
        st.plotly_chart(stacked_status_bar(kpi.status_by_dimension(items, "domain"),
                                           "domain", horizontal=True),
                        width="stretch", config={"displayModeBar": False})

    children = _children(program["program_id"])
    if not children.empty:
        with panel("Programs beneath this initiative", "folders",
                    "Nested programs roll their delivery up into the numbers above."):
            child_scores = kpi.program_scorecard(children, work_items)
            st.dataframe(
                child_scores[["name", "phase", "total", "pct_complete", "schedule_variance",
                              "health", "blocked"]].rename(columns={
                    "name": "Program", "phase": "Phase", "total": "Items",
                    "pct_complete": "% complete", "schedule_variance": "Variance (pts)",
                    "health": "Health", "blocked": "Blocked"}),
                width="stretch", hide_index=True)

    with panel("What needs a decision", "attention"):
        blocked = kpi.blocked_table(items, limit=15)
        if blocked.empty:
            st.caption("Nothing is blocked on this initiative.")
        else:
            st.dataframe(blocked, width="stretch", hide_index=True)


def _render_hub() -> None:
    page_header("Strategic initiatives",
                "The strategic subset of the programs portfolio. Every number here is "
                "derived from delivery data, not reported.")

    if scorecard.empty:
        st.info("No programs are flagged strategic yet - set `is_strategic` on a row in "
                "data/raw/program_registry.csv and rebuild.")
        return

    health = kpi.portfolio_health(scorecard)
    delivery_all = mx.delivery_items(work_items[work_items["program_id"].isin(
        scorecard["program_id"])])

    budget = scorecard["budget_usd"].sum(skipna=True)
    spent = scorecard["spent_usd"].sum(skipna=True)
    overall = mx.pct_complete(delivery_all)
    portfolio_burn = mx.burn_efficiency(delivery_all, budget, spent)

    at_risk = mx.MetricResult(
        key="initiatives_at_risk", label="Initiatives off track",
        value=float(health["off_track"]), display=str(health["off_track"]),
        question="Which strategic bets need a sponsor conversation this month?",
        insight=f"{health['at_risk']} more at risk of {health['total']} initiatives",
        target=0.0, target_display="none off track",
        status="good" if health["off_track"] == 0 else ("watch" if health["off_track"] <= 1 else "bad"))

    slipping = scorecard[scorecard["forecast_slip_weeks"].notna()
                         & (scorecard["forecast_slip_weeks"] > 0)]
    confidence = mx.MetricResult(
        key="portfolio_confidence", label="Forecast to miss target",
        value=float(len(slipping)), display=str(len(slipping)),
        question="How many initiatives will miss their committed date at the current rate?",
        insight=(f"Worst slip {slipping['forecast_slip_weeks'].max():.0f} weeks"
                 if not slipping.empty else "Every measurable initiative is on target"),
        target=0.0, target_display="none forecast to slip",
        status="good" if slipping.empty else ("watch" if len(slipping) <= 2 else "bad"))

    metric_row([
        mx.MetricResult(key="count", label="Initiatives", value=float(health["total"]),
                        display=str(health["total"]),
                        question="How many programs carry strategic status?",
                        insight=f"of {len(programs)} programs in the portfolio"),
        at_risk,
        confidence,
        overall,
        portfolio_burn,
    ])

    st.caption(f"Portfolio budget {mx.fmt_money_md(budget)}, "
               f"{mx.fmt_money_md(spent)} spent.")

    with panel("Plan against forecast", "timeline",
                "The bar is the committed window; the diamond is where the current "
                "delivery rate actually lands. The distance between them is the slip."):
        timeline = scorecard.merge(
            programs[["program_id", "start_date"]], on="program_id", how="left")
        timeline["forecast_date"] = [
            mx.forecast_completion(work_items[work_items["program_id"] == pid])
            for pid in timeline["program_id"]]
        st.plotly_chart(
            forecast_timeline(timeline, "name", "start_date", "target_date", "forecast_date"),
            width="stretch", config={"displayModeBar": False})

    left, right = st.columns(2)
    with left, panel("Delivery against plan", "health",
                      "Below the dashed line is behind schedule."):
        st.plotly_chart(health_matrix(scorecard), width="stretch",
                        config={"displayModeBar": False})
    with right, panel("Burn efficiency", "money",
                       "Budget consumed per unit of scope delivered. Above 1.0x means "
                       "money is going out faster than work is coming in."):
        burn_table = scorecard.dropna(subset=["burn_efficiency"])[["name", "burn_efficiency"]]
        st.plotly_chart(bar_chart(burn_table.rename(columns={"burn_efficiency": "count"}),
                                  "name", "count"),
                        width="stretch", config={"displayModeBar": False})

    st.subheader(f"{icon('apps')} All initiatives")
    with card_grid("initiatives"):
        for _, row in scorecard.iterrows():
            initiative_card(row)


selected = st.query_params.get("initiative")
if selected and (strategic.empty or selected not in set(strategic["program_id"])):
    st.query_params.pop("initiative", None)
    selected = None

if selected:
    initiative = strategic[strategic["program_id"] == selected].iloc[0]
    _render_detail(initiative, work_items[work_items["program_id"] == selected])
else:
    _render_hub()
