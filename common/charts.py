"""Plotly chart builders sharing one consistent Medtronic-navy visual style."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from common.theme import (CHART_COLORWAY, CHART_FONT, FUNNEL_COLORS, HEALTH_COLORS,
                          STATUS_COLORS)

TEXT_DARK = "#101828"
TEXT_MUTED = "#667085"

LAYOUT_DEFAULTS = dict(
    margin=dict(l=10, r=10, t=10, b=10),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=CHART_FONT, size=12.5, color=TEXT_DARK),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    colorway=CHART_COLORWAY,
    height=290,
)


def _style(fig: go.Figure) -> go.Figure:
    fig.update_layout(**LAYOUT_DEFAULTS)
    fig.update_xaxes(showgrid=False, linecolor="#EAECF3")
    fig.update_yaxes(showgrid=True, gridcolor="#F0F2F8", zeroline=False)
    return fig


def _bar_width_fraction(n: int) -> float:
    """Fraction of each category's slot a bar actually fills. Plotly sizes a
    slot as plot_extent / n_categories, so a chart with only 1-4 categories
    would otherwise stretch every bar to fill nearly the whole plot (a
    single-category vertical bar becomes one giant block; 2-3 horizontal bars
    look like fat slabs) - shrink the fraction as n drops to keep bars a
    sane, consistent thickness regardless of category count."""
    return {1: 0.28, 2: 0.38, 3: 0.48, 4: 0.58}.get(n, 0.8)


def _bar_chart_height(n: int) -> int:
    """Chart height that scales with category count instead of a fixed 290px
    for every chart - a handful of categories get a shorter card instead of
    stretching into oversized bars; many categories get more room."""
    return max(200, min(320, 90 + 34 * n))


def _apply_bar_sizing(fig: go.Figure, n: int, horizontal: bool) -> go.Figure:
    """Shared thickness/height fix applied last (after `_style()`, whose
    LAYOUT_DEFAULTS would otherwise overwrite a custom height back to 290)."""
    fig.update_traces(width=_bar_width_fraction(n))
    if horizontal:
        fig.update_layout(height=_bar_chart_height(n), bargap=0.35)
    else:
        fig.update_layout(bargap=0.35)
    return fig


def empty_chart(message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=13, color=TEXT_MUTED))
    fig.update_layout(**LAYOUT_DEFAULTS)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def bar_chart(df: pd.DataFrame, x: str, y: str, horizontal: bool = True, text_auto: bool = True,
              highlight: str | None = None) -> go.Figure:
    """`highlight` (a category value from `x`) recolors that one bar in the
    primary accent and mutes the rest - used for clickable drill-down charts
    (see app_pages/agents.py) so the active filter is visually obvious."""
    if df.empty:
        return empty_chart()
    if horizontal:
        df = df.sort_values(y)
        fig = px.bar(df, x=y, y=x, orientation="h", text_auto=text_auto)
    else:
        fig = px.bar(df, x=x, y=y, text_auto=text_auto)
    if highlight is not None:
        colors = [CHART_COLORWAY[0] if str(v) == str(highlight) else "#D0D5DD" for v in df[x]]
        fig.update_traces(marker_color=colors, marker_line_width=0)
    else:
        fig.update_traces(marker_color=CHART_COLORWAY[0], marker_line_width=0)
    return _apply_bar_sizing(_style(fig), len(df), horizontal)


def donut_chart(df: pd.DataFrame, names: str, values: str) -> go.Figure:
    if df.empty:
        return empty_chart()
    fig = px.pie(df, names=names, values=values, hole=0.55)
    fig.update_traces(textinfo="percent", textposition="inside")
    return _style(fig)


def grouped_bar_chart(df: pd.DataFrame, x: str, y: str, color: str, horizontal: bool = True,
                       barmode: str = "stack") -> go.Figure:
    """Bar chart split by a free-form category column (no fixed status palette).

    `barmode="group"` puts the series side by side, which is the right choice
    when the series are on very different scales - stacking two such series
    makes the smaller one an invisible sliver against the larger.
    """
    if df.empty:
        return empty_chart()
    if horizontal:
        fig = px.bar(df, x=y, y=x, color=color, orientation="h", barmode=barmode)
    else:
        fig = px.bar(df, x=x, y=y, color=color, barmode=barmode)
    fig.update_traces(marker_line_width=0)
    fig.update_layout(legend_title_text="")
    return _apply_bar_sizing(_style(fig), df[x].nunique(), horizontal)


def stacked_status_bar(df: pd.DataFrame, x: str, status_col: str = "status_category",
                        y: str = "count", horizontal: bool = False) -> go.Figure:
    """Grouped bar of counts per `x` (e.g. program or domain), colored by status
    category with a fixed semantic palette (grey=To Do, amber=In Progress, green=Done)."""
    if df.empty:
        return empty_chart()
    color_map = {k: v for k, v in STATUS_COLORS.items() if k in df[status_col].astype(str).unique()}
    if horizontal:
        fig = px.bar(df, x=y, y=x, color=status_col, orientation="h", barmode="stack",
                     color_discrete_map=color_map or None)
    else:
        fig = px.bar(df, x=x, y=y, color=status_col, barmode="stack",
                     color_discrete_map=color_map or None)
    fig.update_traces(marker_line_width=0)
    fig.update_layout(legend_title_text="")
    return _apply_bar_sizing(_style(fig), df[x].nunique(), horizontal)


def line_chart(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    if df.empty:
        return empty_chart()
    fig = px.line(df, x=x, y=y, markers=True)
    fig.update_traces(line_color=CHART_COLORWAY[0], line_width=3)
    return _style(fig)


def category_color_bar_chart(df: pd.DataFrame, x: str, y: str, color_map: dict[str, str],
                              horizontal: bool = True) -> go.Figure:
    """Bar chart where each bar's color comes from `color_map[value]` (e.g.
    Strategic initiatives' health Green/Amber/Red) instead of one flat accent -
    like `bar_chart`'s `highlight`, but every bar gets its own semantic color."""
    if df.empty:
        return empty_chart()
    if horizontal:
        df = df.sort_values(y)
        fig = px.bar(df, x=y, y=x, orientation="h", text_auto=True)
    else:
        fig = px.bar(df, x=x, y=y, text_auto=True)
    fig.update_traces(marker_color=[color_map.get(str(v), "#D0D5DD") for v in df[x]], marker_line_width=0)
    return _apply_bar_sizing(_style(fig), len(df), horizontal)


def timeline_chart(df: pd.DataFrame, task_col: str, start_col: str, end_col: str,
                    color_col: str | None = None, color_map: dict[str, str] | None = None) -> go.Figure:
    """Horizontal Gantt-style bar, one row per task spanning start->end - used
    for the Strategic initiatives multi-quarter timeline."""
    if df.empty:
        return empty_chart()
    fig = px.timeline(df, x_start=start_col, x_end=end_col, y=task_col, color=color_col,
                       color_discrete_map=color_map)
    fig.update_yaxes(autorange="reversed")
    fig.update_traces(marker_line_width=0)
    if color_col:
        fig.update_layout(legend_title_text="", showlegend=True)
    else:
        fig.update_traces(marker_color=CHART_COLORWAY[0])
    return _style(fig)


def multi_line_chart(df: pd.DataFrame, x: str, y_cols: list[str]) -> go.Figure:
    if df.empty:
        return empty_chart()
    fig = go.Figure()
    for i, col in enumerate(y_cols):
        fig.add_trace(go.Scatter(x=df[x], y=df[col], mode="lines+markers", name=col,
                                  line=dict(color=CHART_COLORWAY[i % len(CHART_COLORWAY)], width=3)))
    return _style(fig)


def health_matrix(scorecard: pd.DataFrame, x: str = "pct_elapsed",
                  y: str = "pct_complete") -> go.Figure:
    """Progress against time elapsed, one point per program.

    The dashed diagonal is "on plan". Everything below it is behind, and how far
    below is the size of the problem - which a table of percentages cannot show
    at a glance. This is the chart that answers "who do I need to talk to".
    """
    if scorecard is None or scorecard.empty:
        return empty_chart()
    df = scorecard.dropna(subset=[x, y])
    if df.empty:
        return empty_chart("No program has both a plan window and measurable progress")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[0, 100], y=[0, 100], mode="lines", line=dict(color="#CDD2DE", width=2, dash="dash"),
        hoverinfo="skip", showlegend=False))
    # Labelling all 17 points produced an unreadable smear where programs
    # cluster. Name only the handful furthest behind - the ones a leader has to
    # be able to read without hovering - and alternate the label above and below
    # the marker so neighbouring labels do not collide. Every point keeps its
    # full detail on hover.
    label_count = min(6, len(df))
    named = set(df.nsmallest(label_count, "schedule_variance")["name"])         if "schedule_variance" in df.columns else set(df["name"])
    labels = [n if n in named else "" for n in df["name"]]
    positions = ["top center" if i % 2 == 0 else "bottom center" for i in range(len(df))]
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y], mode="markers+text", text=labels, textposition=positions,
        hovertext=df["name"],
        textfont=dict(size=10, color=TEXT_MUTED),
        marker=dict(
            size=(df["total"].clip(lower=25) ** 0.5).clip(9, 32),
            color=[HEALTH_COLORS.get(h, "#98A2B3") for h in df["health"]],
            line=dict(width=0)),
        customdata=df[["health", "total", "blocked"]].values,
        hovertemplate=("<b>%{hovertext}</b><br>%{y:.0f}% delivered vs %{x:.0f}% elapsed"
                        "<br>%{customdata[0]} - %{customdata[1]:,} items, "
                        "%{customdata[2]} blocked<extra></extra>")))
    fig.update_layout(height=430, showlegend=False)
    fig.update_xaxes(title="% of plan window elapsed", range=[-4, 108])
    fig.update_yaxes(title="% of scope delivered", range=[-4, 108])
    return _style(fig)


def funnel_chart(df: pd.DataFrame, stage_col: str, value_col: str,
                  color_map: dict | None = None) -> go.Figure:
    """Rollout stages in pipeline order, so a bottom-heavy funnel is obvious.
    A frequency-sorted bar chart hides exactly that."""
    if df is None or df.empty:
        return empty_chart()
    palette = color_map or FUNNEL_COLORS
    fig = px.bar(df, x=stage_col, y=value_col, text_auto=True)
    fig.update_traces(
        marker_color=[palette.get(str(v), CHART_COLORWAY[0]) for v in df[stage_col]],
        marker_line_width=0)
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(title="")
    return _style(fig)


def flow_chart(df: pd.DataFrame, x: str, series: list[str],
                colors: list[str] | None = None) -> go.Figure:
    """Arrivals against completions over time. Two lines on one axis, because
    the gap between them *is* the metric - on separate cards it would have to be
    compared by eye."""
    if df is None or df.empty:
        return empty_chart()
    palette = colors or [CHART_COLORWAY[4], CHART_COLORWAY[2], "#98A2B3"]
    fig = go.Figure()
    for i, column in enumerate(series):
        if column not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df[x], y=df[column], mode="lines+markers", name=column.replace("_", " ").title(),
            line=dict(color=palette[i % len(palette)], width=3)))
    fig.update_layout(height=330)
    return _style(fig)


def target_bar_chart(df: pd.DataFrame, category: str, value: str, target: str) -> go.Figure:
    """Measured values with their target marked alongside, so each bar reads as
    pass or fail instead of as a number the reader must compare in their head."""
    if df is None or df.empty:
        return empty_chart()
    frame = df.dropna(subset=[value])
    if frame.empty:
        return empty_chart("Not enough dated records to measure these stages")
    colors = [STATUS_COLORS["Blocked"] if v > t else STATUS_COLORS["Done"]
              for v, t in zip(frame[value], frame[target])]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=frame[category], x=frame[value], orientation="h",
                          marker_color=colors, marker_line_width=0, name="Actual",
                          text=[f"{v:.0f}d" for v in frame[value]], textposition="auto"))
    fig.add_trace(go.Scatter(y=frame[category], x=frame[target], mode="markers", name="Target",
                              marker=dict(symbol="line-ns-open", size=20, color=TEXT_DARK,
                                          line=dict(width=3))))
    fig.update_layout(height=max(210, 80 + 54 * len(frame)), bargap=0.45)
    fig.update_xaxes(title="Calendar days")
    return _style(fig)


def forecast_timeline(df: pd.DataFrame, name_col: str, start_col: str, target_col: str,
                       forecast_col: str) -> go.Figure:
    """Planned window per initiative with the projected finish marked on it, so
    slip reads as distance rather than being inferred from two dates."""
    if df is None or df.empty:
        return empty_chart()
    frame = df.dropna(subset=[start_col, target_col])
    if frame.empty:
        return empty_chart("No initiative has both a start and a target date")
    fig = px.timeline(frame, x_start=start_col, x_end=target_col, y=name_col)
    fig.update_traces(marker_color=CHART_COLORWAY[0], marker_line_width=0, name="Planned",
                       showlegend=True)
    forecasts = frame.dropna(subset=[forecast_col])
    if not forecasts.empty:
        fig.add_trace(go.Scatter(
            x=forecasts[forecast_col], y=forecasts[name_col], mode="markers", name="Forecast",
            marker=dict(symbol="diamond", size=12, color=STATUS_COLORS["Blocked"]),
            hovertemplate="Forecast finish %{x|%b %Y}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", title="")
    fig.update_layout(height=max(250, 70 + 42 * len(frame)), showlegend=True)
    return _style(fig)
