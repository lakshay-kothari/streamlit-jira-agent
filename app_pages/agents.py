"""Agents: the AI/BI board - what is being built, how far it has got, and who
is carrying it.

Rebuilt around three questions the old page could not answer:

* **Is anything shipping?** A rollout funnel in pipeline order, rather than a
  frequency-sorted bar where "Not Started" (which really meant "nobody filled
  the field in") dominated by construction.
* **Who is this resting on?** Two people own roughly two thirds of the board.
  That was visible in the data all along and shown nowhere.
* **Where is the AI effort not going?** Business areas generating demand with
  no agents behind them - the white space.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import data_access, kpi
from common import metrics as mx
from common.charts import bar_chart, funnel_chart, grouped_bar_chart
from common.components import (drill_caption, filter_chip_row, insight_note, metric_row,
                               page_header, panel, card_key)
from common.theme import PANEL_KEY_PREFIX
from common.config import METRIC_TARGETS
from common.icons import icon

board = data_access.get_board_items()
demands = data_access.get_demands()
programs = data_access.get_programs()

page_header("Agents",
            "Every agent and data product on the AI/BI board - rollout progress, "
            "ownership concentration, and where the white space is.")

if board.empty:
    st.info("No agents loaded yet - drop the AI/BI board CSV into data/raw/ and rebuild.")
    st.stop()

FILTER_DIMENSIONS = [
    ("status", "Rollout stage", "funnel", kpi.agent_funnel),
    ("sub_domain", "Business area", "explore", lambda df: kpi.agent_breakdown(df, "sub_domain")),
    ("owner", "Owner", "users", lambda df: kpi.agent_breakdown(df, "owner", top_n=12)),
    ("platform", "Platform", "stacks", lambda df: kpi.agent_breakdown(df, "platform")),
]

active_filters = {key: st.query_params[key] for key, *_ in FILTER_DIMENSIONS
                  if key in st.query_params}


def _apply(df: pd.DataFrame, exclude: str | None = None) -> pd.DataFrame:
    out = df
    for key, value in active_filters.items():
        if key == exclude or key not in out.columns:
            continue
        out = out[out[key].astype(str) == value]
    return out


filtered = _apply(board)
now = pd.Timestamp.now()

concentration = kpi.agent_owner_concentration(filtered)
linkage = kpi.agent_demand_linkage(filtered)
time_to_live = kpi.agent_time_to_live(filtered)
stalled = kpi.agent_stalled(filtered, now=now)
live_count = int((filtered["status"] == "Live").sum()) if "status" in filtered.columns else 0

shipped = mx.MetricResult(
    key="live_agents", label="Agents live", value=float(live_count),
    display=mx.fmt_int(live_count),
    question="How many agents are actually in production, rather than in progress?",
    insight=f"{100 * live_count / len(filtered):.0f}% of {len(filtered):,} on the board"
            if len(filtered) else None,
    target=None,
    status=mx.GOOD if live_count else mx.WATCH,
)

t2l = mx.MetricResult(
    key="time_to_live", label="Time to live (median)",
    value=time_to_live["median_days"], display=mx.fmt_days(time_to_live["median_days"]),
    question="How long does an agent take to get from idea to production?",
    insight=(f"Measured across {time_to_live['measured']} shipped agents"
             if time_to_live["measured"] else "No agent has shipped yet"),
    status=mx.GOOD if time_to_live["median_days"] else mx.UNKNOWN,
)

bus_factor = mx.MetricResult(
    key="owner_concentration", label="Top-2 owner load",
    value=concentration["share_pct"], display=mx.fmt_pct(concentration["share_pct"]),
    question="How exposed is the board if one or two people move on?",
    insight=(f"{' and '.join(str(o).split('@')[0] for o in concentration['top_owners'])} "
             f"across {concentration['distinct_owners']} owners"
             if concentration["top_owners"] else None),
    target=float(METRIC_TARGETS["agent_owner_concentration_pct"]),
    target_display=f"under {METRIC_TARGETS['agent_owner_concentration_pct']:.0f}%",
    status=mx.band(concentration["share_pct"],
                   METRIC_TARGETS["agent_owner_concentration_pct"], "lower_better"),
)

demand_linked = mx.MetricResult(
    key="demand_linked", label="Demand-linked", value=linkage["share_pct"],
    display=mx.fmt_pct(linkage["share_pct"]),
    question="Is the AI portfolio answering business demand, or building what it fancies?",
    insight=f"{linkage['linked']:,} traced to a demand, {linkage['self_originated']:,} self-originated",
    target=50.0, target_display="at least half traced to a demand",
    status=mx.band(linkage["share_pct"], 50.0, "higher_better"),
)

stalled_metric = mx.MetricResult(
    key="stalled_agents", label="Stalled", value=float(len(stalled)),
    display=mx.fmt_int(len(stalled)),
    question="What is sitting on the board consuming a slot without progressing?",
    insight=f"No movement in {METRIC_TARGETS['agent_stalled_days']}+ days",
    target=0.0, target_display="nothing stalled",
    status=mx.GOOD if stalled.empty else (mx.WATCH if len(stalled) < 10 else mx.BAD),
)

metric_row([shipped, t2l, bus_factor, demand_linked, stalled_metric])

if bus_factor.status == mx.BAD and concentration["top_owners"]:
    insight_note(
        f"**The board rests on two people.** {concentration['share_pct']:.0f}% of agents are "
        f"owned by {len(concentration['top_owners'])} of {concentration['distinct_owners']} "
        f"owners. That is a delivery risk before it is a capacity one - nothing they own can "
        f"move while they are unavailable.", tone="warning")

filter_chip_row(active_filters)

left, right = st.columns([3, 2])
with left, panel("Rollout funnel", "funnel",
                  "Stages in pipeline order, so a bottom-heavy board is obvious. "
                  "Sorting these bars by size would hide exactly that."):
    funnel = kpi.agent_funnel(filtered)
    st.plotly_chart(funnel_chart(funnel, "status", "count"),
                    width="stretch", config={"displayModeBar": False})
    if not funnel.empty:
        early = funnel[funnel["status"].isin(["Idea", "Scoping"])]["count"].sum()
        if early:
            st.caption(f"{early:,} of {len(filtered):,} agents "
                       f"({100 * early / len(filtered):.0f}%) have not started building.")
with right, panel("Ownership spread", "users",
                   "A long tail with two very tall bars is the shape of a bus-factor risk."):
    st.plotly_chart(bar_chart(kpi.agent_breakdown(filtered, "owner", top_n=10), "owner", "count"),
                    width="stretch", config={"displayModeBar": False})

with panel("Where the AI effort is not going", "idea",
            "Programs ranked by how little AI coverage they have relative to the demand "
            "they generate. Agents and demands are matched on the program registry, not "
            "on names - the board and the intake queue use different vocabularies."):
    white_space = kpi.agent_white_space(filtered, demands, programs)
    if white_space.empty:
        st.caption("No program has both agents and demands attached to it yet. Add attach "
                   "rules to the program registry to enable this comparison.")
    else:
        melted = white_space.melt(id_vars="program", value_vars=["agents", "demands"],
                                  var_name="measure", value_name="count")
        # Side by side, not stacked: demand volume is an order of magnitude
        # larger, and stacking would render the agent bars invisible.
        st.plotly_chart(grouped_bar_chart(melted, "program", "count", "measure",
                                          barmode="group"),
                        width="stretch", config={"displayModeBar": False})
        gaps = white_space[(white_space["agents"] == 0) & (white_space["demands"] > 0)]
        if not gaps.empty:
            st.caption(f"No agents at all on: {', '.join(gaps['program'].head(4))} - "
                       f"despite {int(gaps['demands'].sum()):,} demands raised against them.")

st.subheader(f"{icon('explore')} Break the board down")
st.caption("Click a bar to filter the board below.")
grid = st.columns(2)
for i, (key, title, icon_name, breakdown_fn) in enumerate(FILTER_DIMENSIONS):
    with grid[i % 2], panel(title, icon_name):
        drill_caption()
        counts = breakdown_fn(_apply(board, exclude=key))
        if counts.empty:
            st.caption("Not recorded on this board yet.")
            continue
        col = counts.columns[0]
        horizontal = key != "status"
        fig = (funnel_chart(counts, col, "count") if key == "status"
               else bar_chart(counts, col, "count", highlight=active_filters.get(key)))
        event = st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                                on_select="rerun", selection_mode="points",
                                key=f"agents_chart_{key}")
        if event.selection.points:
            point = event.selection.points[0]
            clicked = point.get("y") if horizontal else point.get("x")
            if clicked is not None and str(clicked) != active_filters.get(key):
                st.query_params[key] = str(clicked)
                st.rerun()

all_agents, stalled_tab = st.tabs([f"Agents ({len(filtered):,})", f"Stalled ({len(stalled):,})"])
with all_agents:
    show_cols = [c for c in ["item_key", "name", "owner", "sub_domain", "status", "platform",
                             "origin", "eta", "demand_intake_number"] if c in filtered.columns]
    table_event = st.dataframe(filtered[show_cols], width="stretch", hide_index=True,
                               on_select="rerun", selection_mode="single-row", key="agents_table")
    if table_event.selection.rows:
        row = filtered.iloc[table_event.selection.rows[0]]
        with st.container(border=True,
                          key=card_key(PANEL_KEY_PREFIX, "plain", "agent_detail")):
            st.markdown(f"#### {icon('bot')} {row.get('name') or row.get('item_key')}")
            st.write(row.get("description") or "No description provided.")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Owner", str(row.get("owner") or "Unassigned").split("@")[0])
            d2.metric("Business area", row.get("sub_domain") or "-")
            d3.metric("Stage", row.get("status") or "-")
            d4.metric("Origin", row.get("origin") or "-")
with stalled_tab:
    st.caption(f"Not live, and no movement in {METRIC_TARGETS['agent_stalled_days']}+ days.")
    st.dataframe(stalled, width="stretch", hide_index=True)
