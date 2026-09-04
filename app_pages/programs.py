"""Programs: every delivery program in the portfolio - strategic ones included.

This is where the portfolio model shows up in the UI. A strategic initiative is
not a separate kind of thing; it is a program with `is_strategic` set, so it
appears here with a badge and can be filtered to, while the Strategic
initiatives page is the same rows seen at sponsor altitude. One entity, counted
once, wherever you look at it.

Hub -> detail via the `program` query param (see DESIGN_SYSTEM.md).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import bar_chart, flow_chart, health_matrix, stacked_status_bar
from common.components import (breadcrumb_back, card_grid, insight_note, metric_row,
                               page_header, panel, program_card)
from common.icons import icon

programs = data_access.get_programs()
work_items = data_access.get_work_items()
scorecard = kpi.program_scorecard(programs, work_items)


def _render_detail(program: pd.Series, items: pd.DataFrame) -> None:
    breadcrumb_back("Programs", param="program")
    page_header(program["name"],
                program.get("key_risks") or "Delivery breakdown for this program.")

    badges = []
    if program.get("is_strategic"):
        badges.append(("Strategic initiative", "violet"))
    for label, value in (("Portfolio", program.get("portfolio")),
                         ("Phase", program.get("phase")),
                         ("Source", program.get("source_system"))):
        if value and not pd.isna(value):
            badges.append((f"{label}: {value}", "gray"))
    with st.container(horizontal=True):
        for text, color in badges:
            st.badge(text, color=color)

    variance = mx.schedule_variance(items, program.get("start_date"), program.get("target_date"))
    metric_row([
        mx.pct_complete(items),
        variance,
        mx.blocked_work(items),
        mx.descope_rate(items),
        mx.throughput_metric(items),
    ])
    metric_row([
        mx.cycle_time(items),
        mx.delivery_confidence(items, program.get("target_date")),
        mx.aging_work(items),
        mx.unassigned_work(items),
        mx.burn_efficiency(items, program.get("budget_usd"), program.get("spent_usd")),
    ], key="kpi_row_2")

    if variance.status == "bad":
        counts = mx._counts(mx.delivery_items(items))
        remaining = counts["total"] - counts["done"] - counts["cancelled"]
        insight_note(
            f"**{program['name']} is off track.** {variance.insight}. "
            f"{remaining:,} items remain open, and hitting the target date needs them "
            f"delivered faster than the current rate.", tone="error")

    with panel("Delivery flow", "trend",
                "Work arriving against work completed. The gap between the lines is "
                "whether the backlog is growing or shrinking."):
        flow = kpi.monthly_flow(items)
        st.plotly_chart(flow_chart(flow, "month", ["created", "completed"]),
                        width="stretch", config={"displayModeBar": False})
        if not flow.empty:
            recent = flow.tail(6)
            arrived, finished = int(recent["created"].sum()), int(recent["completed"].sum())
            if finished:
                st.caption(f"Last 6 months: {arrived:,} in, {finished:,} out "
                           f"({arrived / finished:.1f}x arrival rate).")

    left, right = st.columns([3, 2])
    with left, panel("Progress by domain", "explore",
                      "Where the scope sits, and which domains carry the blocked work."):
        st.plotly_chart(stacked_status_bar(kpi.status_by_dimension(items, "domain"),
                                           "domain", horizontal=True),
                        width="stretch", config={"displayModeBar": False})
    with right, panel("Status mix", "bar_chart"):
        st.plotly_chart(bar_chart(kpi.status_breakdown(items), "status_category", "count"),
                        width="stretch", config={"displayModeBar": False})

    with panel("Workstream roll-up", "stacks",
                "Sorted by blocked then open work, so the workstream that needs a "
                "decision is at the top - not simply the biggest one."):
        rollup = kpi.workstream_rollup(items)
        if rollup.empty:
            st.caption("This source does not group work into workstreams.")
        else:
            st.dataframe(
                rollup.rename(columns={"workstream": "Workstream", "total": "Items",
                                       "done": "Done", "open": "Open", "blocked": "Blocked",
                                       "cancelled": "Cancelled", "pct_done": "% done",
                                       "at_risk": "At risk"}),
                width="stretch", hide_index=True,
                column_config={"% done": st.column_config.ProgressColumn(
                    "% done", min_value=0, max_value=100, format="%.0f%%")})

    with panel("Ageing of open work", "schedule",
                "A distribution, not an average - the tail is the part that matters."):
        st.plotly_chart(bar_chart(kpi.aging_buckets(items), "bucket", "count", horizontal=False),
                        width="stretch", config={"displayModeBar": False})

    blocked, stale, overdue = st.tabs(["Blocked", "Stale", "Overdue"])
    with blocked:
        table = kpi.blocked_table(items)
        st.caption("Work waiting on somebody else, oldest first.")
        st.dataframe(table, width="stretch", hide_index=True)
    with stale:
        st.caption("Open work with no movement past the staleness threshold.")
        st.dataframe(kpi.stale_table(items, limit=300), width="stretch", hide_index=True)
    with overdue:
        st.caption("Open work past its own due date.")
        st.dataframe(kpi.overdue_table(items, limit=300), width="stretch", hide_index=True)


def _render_hub() -> None:
    page_header("Programs",
                "Every delivery program in the portfolio. Strategic initiatives are the "
                "flagged subset - the same programs, seen at sponsor altitude.")

    if scorecard.empty:
        st.info("No programs registered yet - add a row to data/raw/program_registry.csv "
                "and rebuild the database.")
        return

    health = kpi.portfolio_health(scorecard)
    delivery = mx.delivery_items(work_items)
    strategic_count = int(scorecard["is_strategic"].sum())

    off_track = mx.MetricResult(
        key="off_track", label="Programs off track",
        value=float(health["off_track"]), display=str(health["off_track"]),
        question="Which programs need an intervention this week?",
        insight=f"{health['at_risk']} more at risk of {health['total']} programs",
        target=0.0, target_display="none off track",
        status="good" if health["off_track"] == 0 else ("watch" if health["off_track"] <= 2 else "bad"),
    )
    portfolio_size = mx.MetricResult(
        key="portfolio_size", label="Programs", value=float(health["total"]),
        display=str(health["total"]),
        question="How much is in the portfolio, and how much of it is strategic?",
        insight=f"{strategic_count} strategic, {health['total'] - strategic_count} standard",
    )
    metric_row([
        portfolio_size,
        off_track,
        mx.blocked_work(delivery),
        mx.descope_rate(delivery),
        mx.aging_work(delivery),
    ])

    with panel("Delivery against plan", "monitoring",
                "Each bubble is a program, sized by its scope. The dashed line is on-plan; "
                "everything below it is behind, and the distance is the size of the problem."):
        st.plotly_chart(health_matrix(scorecard), width="stretch",
                        config={"displayModeBar": False})
        behind = scorecard[scorecard["health"].isin(["Off Track", "At Risk"])]
        if not behind.empty:
            worst = behind.iloc[0]
            st.caption(f"Furthest behind: **{worst['name']}** at {worst['schedule_variance']:+.0f} "
                       f"points, {worst['pct_complete']:.0f}% delivered against "
                       f"{worst['pct_elapsed']:.0f}% of its window.")

    st.subheader(f"{icon('apps')} All programs")
    with st.container(horizontal=True, vertical_alignment="top", gap="medium"):
        scope = st.segmented_control("Show", ["All", "Strategic", "Standard"], default="All",
                                     key="program_scope")
        order = st.selectbox("Sort by", ["Needs attention", "Largest", "Furthest along",
                                         "Name"], key="program_sort")

    view = scorecard
    if scope == "Strategic":
        view = view[view["is_strategic"]]
    elif scope == "Standard":
        view = view[~view["is_strategic"]]
    view = {
        "Needs attention": view.sort_values("schedule_variance", na_position="last"),
        "Largest": view.sort_values("total", ascending=False),
        "Furthest along": view.sort_values("pct_complete", ascending=False, na_position="last"),
        "Name": view.sort_values("name"),
    }[order]

    if view.empty:
        st.info("No programs match this filter.")
        return
    st.caption(f"Showing {len(view)} of {len(scorecard)} programs.")
    with card_grid("programs"):
        for _, row in view.iterrows():
            program_card(row)


selected = st.query_params.get("program")
if selected and (programs.empty or selected not in set(programs["program_id"])):
    st.query_params.pop("program", None)
    selected = None

if selected:
    program_row = programs[programs["program_id"] == selected].iloc[0]
    _render_detail(program_row, work_items[work_items["program_id"] == selected])
else:
    _render_hub()
