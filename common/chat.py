"""SnowJira chat: conversation state + KPI grounding, rendered inside the
floating launcher's panel (see `render_floating_button` below).

The snapshot handed to Cortex is deliberately *metric-shaped* rather than a dump
of counts. Each entry carries the value, the question the metric answers, its
target and its coverage - so the agent can reason about whether a number is good
and whether it can be trusted, instead of just reading it back.

It also carries the portfolio model explicitly (strategic initiatives are the
flagged subset of programs), because the most common question a leader asks
spans both, and a model the agent has to infer is a model it will get wrong.

Falls back to a deterministic offline answer when no Snowflake connection is
reachable, so the panel stays usable in local demos.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from common import kpi
from common import metrics as mx
from common.config import AGENT_NAME, AGENT_TAGLINE, DEFAULT_CORTEX_MODEL
from common.cortex import cortex_available, cortex_complete
from common.icons import icon
from common.theme import FLOATING_AGENT_KEY

HISTORY_KEY = "agent_chat_history"
PANEL_OPEN_KEY = "snowjira_panel_open"
REFS_KEY = "snowjira_refs"
MESSAGES_KEY = f"{FLOATING_AGENT_KEY}_messages"
MAX_SHOWN = 8  # keep the panel compact - full history still in state


def _metric(result: mx.MetricResult) -> dict:
    """One metric, with everything needed to reason about it rather than just
    quote it."""
    return {
        "value": result.display,
        "answers": result.question,
        "target": result.target_display,
        "status": result.status,
        "insight": result.insight,
        "caveat": result.coverage_note,
    }


def _snapshot(programs: pd.DataFrame, work_items: pd.DataFrame, board: pd.DataFrame,
              demands: pd.DataFrame) -> dict:
    scorecard = kpi.program_scorecard(programs, work_items)
    delivery = mx.delivery_items(work_items)
    health = kpi.portfolio_health(scorecard)
    strategic = scorecard[scorecard["is_strategic"]] if not scorecard.empty else scorecard
    stage_times = kpi.demand_stage_times(demands)

    return {
        "portfolio_model": (
            "A strategic initiative IS a program with is_strategic=true. There is one "
            "programs table; the strategic count is always a subset of the program count. "
            "Never add them together."
        ),
        "portfolio": {
            "programs": health["total"],
            "strategic_initiatives": int(scorecard["is_strategic"].sum()) if not scorecard.empty else 0,
            "on_track": health["on_track"],
            "at_risk": health["at_risk"],
            "off_track": health["off_track"],
        },
        "portfolio_metrics": {
            "pct_complete": _metric(mx.pct_complete(delivery)),
            "blocked": _metric(mx.blocked_work(delivery)),
            "descope_rate": _metric(mx.descope_rate(delivery)),
            "stale_work": _metric(mx.aging_work(delivery)),
            "net_flow": _metric(mx.net_flow(
                pd.concat([delivery["created"], demands["created"]], ignore_index=True),
                pd.concat([delivery["completed"], demands["go_live_date"]], ignore_index=True))),
        },
        "programs": (scorecard[["name", "is_strategic", "phase", "total", "pct_complete",
                                "pct_elapsed", "schedule_variance", "health", "blocked",
                                "descope_rate", "burn_efficiency", "forecast_slip_weeks"]]
                     .astype(str).to_dict(orient="records") if not scorecard.empty else []),
        "strategic_summary": {
            "budget_usd": float(strategic["budget_usd"].sum(skipna=True)) if not strategic.empty else 0,
            "spent_usd": float(strategic["spent_usd"].sum(skipna=True)) if not strategic.empty else 0,
            "note": "Every initiative percentage is derived from linked delivery work; the "
                    "PMO register's typed % complete is not used anywhere.",
        },
        "demands": {
            "total": len(demands),
            "open": int((~demands["status_category"].isin(["Done", "Cancelled"])).sum()) if not demands.empty else 0,
            "stage_times": stage_times.astype(str).to_dict(orient="records") if not stage_times.empty else [],
            "bottleneck": kpi.demand_bottleneck(stage_times),
            "cancellation": kpi.demand_cancellation_waste(demands),
            "delay_reasons": kpi.demand_delay_reasons(demands, top_n=6).to_dict(orient="records"),
            "approval_backlog": kpi.demand_approval_backlog(demands).to_dict(orient="records"),
        },
        "agents": {
            "total": len(board),
            "funnel": kpi.agent_funnel(board).to_dict(orient="records"),
            "owner_concentration": kpi.agent_owner_concentration(board),
            "demand_linkage": kpi.agent_demand_linkage(board),
            "time_to_live": kpi.agent_time_to_live(board),
        },
        "data_coverage": kpi.field_coverage(
            {"work_items": work_items, "demands": demands, "board_items": board}
        ).to_dict(orient="records"),
        "attention": kpi.attention_items(work_items, demands, board, scorecard,
                                          limit=15).to_dict(orient="records"),
    }


def _reference_catalog(snapshot: dict) -> list[dict]:
    """Flat, pickable list of the metrics already sitting in the snapshot -
    the "@ Reference" popover's menu (see `render` below). Streamlit's
    chat_input is a plain text box with no live "@"-triggered autocomplete
    (that needs a custom rich-text component); this is the native-widget
    equivalent - pick from a list instead of typing a trigger character -
    covering the same portfolio-wide metrics the agent already reasons over,
    since the panel isn't scoped to whichever page it was opened from."""
    portfolio = snapshot["portfolio"]
    items = [
        {"label": "Programs", "value": str(portfolio["programs"])},
        {"label": "Strategic initiatives", "value": str(portfolio["strategic_initiatives"])},
        {"label": "Programs off track", "value": str(portfolio["off_track"])},
        {"label": "Programs at risk", "value": str(portfolio["at_risk"])},
    ]
    for m in snapshot["portfolio_metrics"].values():
        items.append({"label": m["answers"], "value": str(m["value"])})
    items.append({"label": "Open demands", "value": str(snapshot["demands"]["open"])})
    items.append({"label": "Agents on the board", "value": str(snapshot["agents"]["total"])})
    return items


def _offline_answer(question: str, snapshot: dict) -> str:
    portfolio = snapshot["portfolio"]
    demands = snapshot["demands"]
    bottleneck = demands.get("bottleneck") or {}
    return (
        "**Offline mode** (no Snowflake connection configured - a data-grounded "
        "template, not an LLM answer):\n\n"
        f"- You asked: _{question}_\n"
        f"- Portfolio: {portfolio['programs']} programs, of which "
        f"{portfolio['strategic_initiatives']} are strategic initiatives "
        f"({portfolio['off_track']} off track, {portfolio['at_risk']} at risk)\n"
        f"- Delivery: {snapshot['portfolio_metrics']['pct_complete']['value']} complete, "
        f"{snapshot['portfolio_metrics']['blocked']['value']} blocked\n"
        f"- Demands: {demands['total']} total, {demands['open']} open; slowest stage is "
        f"{bottleneck.get('stage', 'not measurable')}\n"
        f"- Agents: {snapshot['agents']['total']} on the board, top-2 owners hold "
        f"{snapshot['agents']['owner_concentration'].get('share_pct')}%\n"
        "- Connect this app to Snowflake (see the README) for full Cortex reasoning here."
    )


SYSTEM_PROMPT = (
    "You are a precise portfolio analyst for a Data+AI organisation. You cover Programs "
    "(delivery work from several different tools), Strategic initiatives (the subset of "
    "programs flagged strategic), Demands (the intake queue) and Agents (the AI/BI board).\n\n"
    "Rules:\n"
    "1. Use ONLY the JSON snapshot below. Do not invent numbers.\n"
    "2. Respect the portfolio model: a strategic initiative IS a program. Never sum the two.\n"
    "3. Every metric carries the question it answers, its target and any coverage caveat. "
    "When a metric has a caveat, say so rather than quoting it as fact.\n"
    "4. Prefer the judgement over the number: say what is off target and what to do about "
    "it, not just what the value is.\n"
    "5. If the answer is not derivable from the snapshot, say so plainly."
)


def render(programs: pd.DataFrame, work_items: pd.DataFrame, board: pd.DataFrame,
           demands: pd.DataFrame) -> None:
    """Chat body for the floating launcher's panel. Owns its own conversation
    history in session state.

    The message history renders into its own container (`messages_box`) so
    CSS can make *only* that region scroll (see common/theme.py) - the
    connection badge above it and the chat input below stay put. `st.chat_input`
    is called after the container closes (so its own wrapper lands as a later
    sibling, pinned at the panel's bottom edge by CSS) but a still-open
    Python reference to `messages_box` lets the reply that follows be
    rendered back *into* that earlier container instead of after the input -
    `with` on a container handle re-enters it wherever it's called from."""
    history: list = st.session_state.setdefault(HISTORY_KEY, [])
    refs: list = st.session_state.setdefault(REFS_KEY, [])

    connected = cortex_available()
    st.badge("Cortex connected" if connected else "Offline mode",
             icon=icon("bolt") if connected else icon("info"),
             color="green" if connected else "orange")

    # Computed once per render (not just on submit) since the "@ Reference"
    # popover below needs it too, and both uses would otherwise recompute
    # the same KPIs independently.
    snapshot = _snapshot(programs, work_items, board, demands)

    messages_box = st.container(key=MESSAGES_KEY)
    with messages_box:
        for msg in history[-MAX_SHOWN:]:
            avatar = icon("bot") if msg["role"] == "assistant" else None
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])

    # "@ Reference": the closest native-Streamlit equivalent to a live "@"
    # autocomplete inside the chat input (which is a plain text box with no
    # such thing built in) - pick a metric from a menu instead of typing a
    # trigger character, attach it as a chip, send it as grounding context
    # alongside the next question.
    with st.container(key=f"{FLOATING_AGENT_KEY}_refs", horizontal=True,
                      vertical_alignment="center"):
        with st.popover("@ Reference", icon=icon("link")):
            st.caption("Attach a metric to ground your next question in.")
            for item in _reference_catalog(snapshot):
                if st.button(f"{item['label']}: {item['value']}",
                             key=f"snowjira_ref_pick_{item['label']}",
                             disabled=item in refs, width="stretch"):
                    refs.append(item)
                    st.rerun()
        for i, ref in enumerate(list(refs)):
            if st.button(f"{ref['label']} ×", key=f"snowjira_ref_chip_{i}_{ref['label']}",
                         help="Remove this reference"):
                refs.remove(ref)
                st.rerun()

    if prompt := st.chat_input(f"Ask {AGENT_NAME}...", key="agent_chat_input"):
        ref_note = (f"  \n*Referencing: {', '.join(r['label'] for r in refs)}*"
                    if refs else "")
        history.append({"role": "user", "content": prompt + ref_note})
        with messages_box, st.chat_message("user"):
            st.markdown(prompt + ref_note)
        ref_context = (
            "\n\nThe user explicitly attached these metrics to this question - "
            "ground your answer in them rather than guessing what they mean:\n"
            + "\n".join(f"- {r['label']}: {r['value']}" for r in refs)
        ) if refs else ""
        with st.spinner("Reasoning over your portfolio..."):
            full_prompt = (f"{SYSTEM_PROMPT}{ref_context}\n\nSNAPSHOT:\n"
                           f"{json.dumps(snapshot, default=str)}\n\nQUESTION: {prompt}")
            response = cortex_complete(full_prompt, DEFAULT_CORTEX_MODEL)
            if response is None:
                response = _offline_answer(prompt, snapshot)
        refs.clear()  # consumed by this question
        history.append({"role": "assistant", "content": response})
        # Rendered inline rather than via st.rerun(): the panel is ordinary
        # page content now (not an st.dialog), so a rerun wouldn't close it -
        # but it would still lose the in-progress scroll position/flicker
        # the whole page. The history loop above will still pick these two
        # messages up the next time this surface reruns for any other reason.
        with messages_box, st.chat_message("assistant", avatar=icon("bot")):
            st.markdown(response)


def render_floating_button(programs: pd.DataFrame, work_items: pd.DataFrame,
                           board: pd.DataFrame, demands: pd.DataFrame) -> None:
    """Fixed bottom-right launcher for SnowJira - a floating panel (CSS
    `position: fixed`, common/theme.py), not an `st.dialog`. A dialog is a
    full-viewport modal: it blocks every other page element, sidebar
    included, while open. This is deliberately just normal page content
    pinned to a corner, the same technique as the launcher button itself, so
    the rest of the app - switching pages via the sidebar in particular -
    stays fully usable while the panel is open."""
    is_open = st.session_state.get(PANEL_OPEN_KEY, False)

    if not is_open:
        with st.container(key=FLOATING_AGENT_KEY):
            if st.button(f"{AGENT_NAME} AI", icon=icon("bot"), key=f"{FLOATING_AGENT_KEY}_btn",
                         type="primary"):
                st.session_state[PANEL_OPEN_KEY] = True
                st.rerun()
        return

    with st.container(key=f"{FLOATING_AGENT_KEY}_panel"):
        with st.container(key=f"{FLOATING_AGENT_KEY}_header", horizontal=True,
                          vertical_alignment="center"):
            st.markdown(f"##### {icon('bot')} Ask {AGENT_NAME}")
            if st.button("", icon=icon("close"), key=f"{FLOATING_AGENT_KEY}_close",
                         help="Close"):
                st.session_state[PANEL_OPEN_KEY] = False
                st.rerun()
        st.caption(AGENT_TAGLINE)
        render(programs, work_items, board, demands)
