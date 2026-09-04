"""Reusable UI building blocks built on native Streamlit elements (st.metric,
st.badge, st.container) - see DESIGN_SYSTEM.md for when to use each, and
common/theme.py for the (minimal) custom CSS these lean on."""
from __future__ import annotations

import re
from itertools import count

import pandas as pd
import streamlit as st

from common.icons import icon
from common.metrics import BAD, GOOD, UNKNOWN, WATCH, MetricResult
from common.theme import (CARD_GRID_KEY_PREFIX, METRIC_CARD_KEY_PREFIX,
                          METRIC_CHIP_KEY_PREFIX, PANEL_KEY_PREFIX, TILE_KEY_PREFIX)

# Streamlit badge/markdown colors (named, not hex) for the status taxonomy.
_STATUS_BADGE_COLORS = {"Done": "green", "In Progress": "orange", "Blocked": "red",
                        "To Do": "gray", "Cancelled": "gray", "Unknown": "gray"}
_HEALTH_BADGE_COLORS = {"On Track": "green", "At Risk": "orange", "Off Track": "red",
                        "Unknown": "gray"}
#: Metric status in words. Shown in the card's tooltip, so the colored bar
#: inside the card is a shortcut rather than the only way to read it.
_METRIC_STATUS_LABELS = {GOOD: "On target", WATCH: "Watch", BAD: "Off target",
                         UNKNOWN: "Not measurable"}


def page_header(title: str, subtitle: str, icon_name: str = "dashboard") -> None:
    """Text-only page title (no icon, per DESIGN_SYSTEM.md) + one-line caption."""
    st.title(title)
    st.caption(subtitle)


def breadcrumb_back(label: str, param: str) -> None:
    """"Back to <label>" link at the top of every drill-down - clears the query
    param that opened it and returns to the hub."""
    if st.button(f"Back to {label}", key=f"back_{param}", icon=icon("back"), type="tertiary"):
        st.query_params.pop(param, None)
        st.rerun()


def filter_chip_row(filters: dict) -> None:
    """Dismissible chips for the drill-down filters currently applied via query
    params. Call after filtering so users can see - and clear - what is
    narrowing the view."""
    if not filters:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption("Filtered by:")
        for key, value in filters.items():
            if st.button(f"{key.replace('_', ' ').title()}: {value}", key=f"chip_{key}",
                         icon=icon("close"), type="tertiary"):
                st.query_params.pop(key, None)
                st.rerun()
        if len(filters) > 1 and st.button("Clear all", key="chip_clear_all", type="tertiary"):
            for key in filters:
                st.query_params.pop(key, None)
            st.rerun()


def drill_caption(text: str = "Click a bar to drill in") -> None:
    """Affordance hint above/below interactive charts so users discover that
    KPIs are clickable, not decorative."""
    st.caption(f"{icon('forward')} {text}")


def metric_chip_row(key: str, metrics: list) -> None:
    """Compact stat row with a light-gray chip fill, for stats nested inside an
    already-bordered parent card. `key` must be unique per call site."""
    with st.container(key=f"{METRIC_CHIP_KEY_PREFIX}{key}", horizontal=True):
        for m_label, m_value in metrics:
            st.metric(m_label, m_value, height="content")


def card_grid(name: str):
    """Responsive grid for a row of repeating tiles (program/initiative/
    activity cards) - reflows the column count to whatever fits the
    available width (CSS Grid auto-fit/minmax in common/theme.py) instead of
    a fixed `st.columns(N)`, which just squeezes every card - and its
    nowrap `metric_chip_row` labels - narrower on a smaller screen rather
    than showing fewer of them per row.

    `name` must be unique per call site. Returns a context manager - render
    each card as a direct child of it, with no `st.columns` in between:

        with card_grid("programs"):
            for _, row in view.iterrows():
                program_card(row)
    """
    return st.container(key=f"{CARD_GRID_KEY_PREFIX}{name}")


# ------------------------------------------------------------ KPI rendering ---
#: Streamlit requires unique container keys, and the same metric can legitimately
#: appear twice on one page (a portfolio figure and a per-program one). A counter
#: keeps keys unique without callers having to invent an id.
_CARD_SEQUENCE = count()


def card_key(prefix: str, variant: str, hint: str) -> str:
    """Unique container key that also carries the card's variant, so the CSS in
    common/theme.py can style it without any inline HTML. For a KPI card the
    variant is its metric status; for every other card it is just "card"."""
    safe = re.sub(r"[^a-z0-9_]+", "_", str(hint).lower())[:40]
    return f"{prefix}{variant}__{safe}_{next(_CARD_SEQUENCE)}"


def metric_card(result: MetricResult, trend: pd.Series | None = None,
                show_status: bool = True) -> None:
    """Render one `MetricResult` as a native KPI card.

    The card itself is a plain `st.metric(border=True, height="stretch")` - the
    same component, padding and radius every KPI in this app has always used.
    What it adds on top of a bare number:

    * a **trend** delta and sparkline where an honest one exists - never a
      fabricated arrow, so a metric with no history simply shows none;
    * the **insight** underneath - the "so what" for this particular value;
    * a **status bar** inside the card's bottom gutter (green / amber / red /
      grey), which is what makes a wall of KPIs scannable at a glance. KPI cards
      are the only cards that carry one - a tile or a panel is a destination,
      not a judgement.

    The status arrives via the wrapper's key rather than as a badge inside the
    card: a badge changed the card's proportions and made KPI cards look unlike
    every other card in the product. The wrapper itself draws nothing.

    The tooltip carries the question the metric answers, its target, any caveat
    about how much of the data backs it, and the status in words - so colour is
    a shortcut, never the only way to read the card.
    """
    status = result.status if show_status else UNKNOWN
    help_text = result.help_text or ""
    if show_status and result.status != UNKNOWN:
        help_text = f"{help_text} Currently {_METRIC_STATUS_LABELS[result.status].lower()}.".strip()

    with st.container(key=card_key(METRIC_CARD_KEY_PREFIX, status, result.key)):
        st.metric(
            result.label,
            result.display,
            result.delta_display,
            delta_color=result.delta_direction or "off",
            delta_description=result.insight,
            help=help_text or None,
            border=True,
            chart_data=trend if trend is not None and len(trend) > 2 else None,
            chart_type="line",
            height="stretch",
        )


def metric_row(results: list, trends: dict | None = None, key: str = "kpi_row") -> None:
    """A row of KPI cards that share the row width and stretch to equal height.

    `key` must start with "kpi_row" - the no-wrap/equal-width CSS in
    common/theme.py matches on that prefix, so a page with two KPI rows passes
    "kpi_row_2" rather than an unrelated name."""
    trends = trends or {}
    with st.container(horizontal=True, key=key):
        for result in results:
            metric_card(result, trend=trends.get(result.key))


def kpi_metric(label: str, value: str, delta: str | None = None,
               delta_color: str = "off", icon_name: str | None = None,
               help_text: str | None = None, description: str | None = None) -> None:
    """Plain KPI card for numbers that are context, not judgements (a count of
    rows shown, a filter total). Anything that should be judged against a target
    belongs in `metric_card` with a `MetricResult` instead."""
    st.metric(label, value, delta, delta_color=delta_color, delta_description=description,
              help=help_text, border=True, height="stretch")


def panel(title: str, icon_name: str, caption: str | None = None):
    """A bordered card holding a chart, a table or a section.

    Every page used to define its own `_panel` helper with a plain
    `st.container(border=True)`. Streamlit renders that as a transparent,
    13px-padded box, so panels read as part of the page rather than as objects
    on it - and the app CSS that was meant to style them targeted an internal
    attribute (`data-test-wrap`) that no longer exists in Streamlit 1.60, so it
    had silently stopped applying. Keying the container is what lets the shared
    card styling in common/theme.py find it.

    Returns the container, so callers can use it as a context manager.
    """
    container = st.container(border=True, key=card_key(PANEL_KEY_PREFIX, "plain", title))
    with container:
        st.subheader(f"{icon(icon_name)} {title}")
        if caption:
            st.caption(caption)
    return container


def inline_badge(text: str, color: str = "gray", icon_name: str | None = None) -> str:
    """Markdown fragment for a colored badge, for composing several on one line."""
    prefix = f"{icon(icon_name)} " if icon_name else ""
    return f":{color}-badge[{prefix}{text}]"


def status_badges(segments: list, limit: int = 4) -> str:
    """Status-mix badges for a card, e.g. Done 120 · Blocked 8."""
    badges = [inline_badge(f"{label} {value}", _STATUS_BADGE_COLORS.get(label, "gray"))
              for label, value in segments if value]
    return " ".join(badges[:limit])


# ------------------------------------------------------------------- cards ---
def activity_card(key: str, label: str, icon_name: str, tagline: str, page_path: str,
                  live: bool, metrics: list) -> None:
    """One top-level activity tile on the Overview page."""
    with st.container(border=True, height="stretch",
                      key=card_key(TILE_KEY_PREFIX, "card", key)):
        top_left, top_right = st.columns([4, 1], vertical_alignment="center")
        with top_left:
            st.markdown(f"#### {icon(icon_name)} {label}")
        with top_right:
            if not live:
                st.badge("Soon", color="gray")
        st.caption(tagline)
        if metrics:
            metric_chip_row(key, metrics)
        if live:
            if st.button(f"Open {label.lower()}", key=f"open_{key}", icon=icon("forward"),
                         width="stretch", type="primary"):
                st.switch_page(page_path)
        else:
            st.button("Coming soon", key=f"soon_{key}", disabled=True, width="stretch")


def program_card(row, param: str = "program", key_prefix: str = "program") -> None:
    """One program tile, driven by a `program_scorecard` row.

    The badge shows *derived* health (schedule variance), not a typed-in RAG,
    and strategic programs are marked rather than separated - they are the same
    entity, seen from a different altitude.
    """
    name = row["name"]
    health = row.get("health") or "Unknown"
    with st.container(border=True, height="stretch",
                      key=card_key(TILE_KEY_PREFIX, "card", row["program_id"])):
        top_left, top_right = st.columns([3, 1], vertical_alignment="center")
        with top_left:
            st.markdown(f"**{name}**")
        with top_right:
            st.badge(health, color=_HEALTH_BADGE_COLORS.get(health, "gray"))

        subtitle = " · ".join(str(v) for v in
                              [row.get("portfolio"), row.get("phase"), row.get("source_system")]
                              if v and not pd.isna(v))
        if row.get("is_strategic"):
            subtitle = f"{inline_badge('Strategic', 'violet')} {subtitle}"
        st.markdown(subtitle)

        pct = row.get("pct_complete")
        elapsed = row.get("pct_elapsed")
        if pct is not None and not pd.isna(pct):
            caption = f"{pct:.0f}% complete"
            if elapsed is not None and not pd.isna(elapsed):
                caption += f" · {elapsed:.0f}% of window elapsed"
            st.progress(min(max(pct / 100, 0.0), 1.0), text=caption)

        variance = row.get("schedule_variance")
        metric_chip_row(f"{key_prefix}_{row['program_id']}", [
            ("Items", f"{int(row.get('total') or 0):,}"),
            ("Open", f"{int(row.get('open') or 0):,}"),
            ("Variance", f"{variance:+.0f} pts" if variance is not None and not pd.isna(variance) else "-"),
        ])

        badges = status_badges(row.get("segments") or [])
        if badges:
            st.markdown(badges)

        if st.button("Open program", key=f"open_{key_prefix}_{row['program_id']}",
                     icon=icon("forward"), width="stretch", type="primary"):
            st.query_params[param] = row["program_id"]
            st.rerun()


def initiative_card(row) -> None:
    """One strategic initiative tile. Same underlying program row as
    `program_card`, framed for a sponsor: money and forecast rather than
    item counts."""
    name = row["name"]
    health = row.get("health") or "Unknown"
    with st.container(border=True, height="stretch",
                      key=card_key(TILE_KEY_PREFIX, "card", row["program_id"])):
        top_left, top_right = st.columns([3, 1], vertical_alignment="center")
        with top_left:
            st.markdown(f"**{name}**")
        with top_right:
            st.badge(health, color=_HEALTH_BADGE_COLORS.get(health, "gray"))
        st.caption(" · ".join(str(v) for v in [row.get("domain"), row.get("phase"),
                                                f"target {row.get('target_quarter') or '-'}"]
                              if v and not pd.isna(v)))

        pct = row.get("pct_complete") or 0
        st.progress(min(max(pct / 100, 0.0), 1.0), text=f"{pct:.0f}% delivered (derived)")

        budget = row.get("budget_usd")
        burn = row.get("burn_efficiency")
        slip = row.get("forecast_slip_weeks")
        metric_chip_row(f"init_{row['program_id']}", [
            ("Budget", f"{(budget or 0) / 1e6:.1f}M USD"),
            ("Burn", f"{burn:.2f}x" if burn is not None and not pd.isna(burn) else "-"),
            ("Forecast", "On target" if slip is not None and not pd.isna(slip) and slip <= 0
             else (f"+{slip:.0f}w" if slip is not None and not pd.isna(slip) else "-")),
        ])
        if st.button("Open initiative", key=f"open_initiative_{row['program_id']}",
                     icon=icon("forward"), width="stretch", type="primary"):
            st.query_params["initiative"] = row["program_id"]
            st.rerun()


def coming_soon(icon_name: str, title: str, description: str, bullets: list | None = None) -> None:
    """Placeholder body for an activity not wired to data yet."""
    with st.container(border=True, horizontal_alignment="center"):
        st.markdown(f"## {icon(icon_name)} {title}")
        st.badge("Coming soon", color="gray", icon=icon("soon"))
        st.write(description)
        if bullets:
            st.markdown("\n".join(f"- {b}" for b in bullets))


def insight_note(text: str, tone: str = "info") -> None:
    """A one-line, data-derived callout under a chart - the interpretation the
    chart supports, so the reader is not left to infer it."""
    getattr(st, {"info": "info", "warning": "warning", "error": "error",
                 "success": "success"}[tone])(text)


def empty_metric_note(field: str, enables: str, coverage_pct: float) -> None:
    """Shown where a chart used to be. Naming the missing field and what it
    would enable turns a blank panel into something the team can act on."""
    st.info(f"**{field}** is populated on {coverage_pct:.0f}% of rows in this source, so "
            f"*{enables}* cannot be shown. Populating it at source turns this panel on.")
