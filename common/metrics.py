"""Metric definitions: what a number means, what good looks like, how far to
trust it.

Every KPI in this app is a `MetricResult`, and each one carries four things a
bare number does not:

* **question**  - the decision it informs. If a metric cannot name one, it does
                  not belong on a page.
* **target**    - from `config.METRIC_TARGETS`. A value with no baseline is not
                  a judgement, just a reading.
* **coverage**  - the share of rows that could actually be measured. A cycle
                  time computed over 24% of the data says so on the card,
                  rather than implying it speaks for everything.
* **insight**   - the "so what", generated from the value itself.

`status` is what the UI colours on: good / watch / bad / unknown. Unknown is a
real outcome - it is what an under-covered or un-targeted metric returns, and it
is far more useful than a confident-looking wrong number.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common.config import COVERAGE_BANDS, METRIC_TARGETS

#: Item types that are activity feeds rather than program delivery scope.
#: A demand is a request for work and an agent is a product idea; counting
#: either as delivery scope would let intake volume move a program's completion.
NON_DELIVERY_ITEM_TYPES = {"Demand", "Agent"}

GOOD, WATCH, BAD, UNKNOWN = "good", "watch", "bad", "unknown"


@dataclass
class MetricResult:
    key: str
    label: str
    display: str
    question: str = ""
    value: float | None = None
    insight: str | None = None
    target: float | None = None
    target_display: str | None = None
    status: str = UNKNOWN
    coverage_pct: float | None = None
    coverage_note: str | None = None
    delta_display: str | None = None
    delta_direction: str = "off"
    detail: dict = field(default_factory=dict)

    @property
    def help_text(self) -> str:
        """What the KPI card shows in its tooltip: the question, the target, and
        any caveat about how much of the data actually backs the number."""
        parts = [self.question] if self.question else []
        if self.target_display:
            parts.append(f"Target: {self.target_display}.")
        if self.coverage_note:
            parts.append(self.coverage_note)
        return " ".join(parts)


# ------------------------------------------------------------------ helpers ---
def coverage(series: pd.Series) -> float:
    """Share of rows carrying a usable value, as a percentage."""
    if series is None or len(series) == 0:
        return 0.0
    return round(100 * float(series.notna().mean()), 1)


def coverage_band(pct: float | None) -> str:
    if pct is None:
        return "Unknown"
    for threshold, label in COVERAGE_BANDS:
        if pct >= threshold:
            return label
    return "Unreliable"


def _coverage_note(pct: float | None, subject: str) -> str | None:
    """Only says something when there is something worth saying - a fully
    covered metric should not shout about it."""
    if pct is None:
        return None
    if pct >= 90:
        return None
    return f"Measured on {pct:.0f}% of {subject}; the rest do not record it."


def band(value: float | None, target: float | None, direction: str,
         watch_ratio: float = 0.85) -> str:
    """Traffic light for a value against its target."""
    if value is None or target is None:
        return UNKNOWN
    if direction == "higher_better":
        if value >= target:
            return GOOD
        return WATCH if value >= target * watch_ratio else BAD
    if value <= target:
        return GOOD
    return WATCH if value <= target / watch_ratio else BAD


def fmt_pct(value: float | None, digits: int = 0) -> str:
    return "-" if value is None or pd.isna(value) else f"{value:.{digits}f}%"


def fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "-"


def fmt_days(value: float | None) -> str:
    return "-" if value is None or pd.isna(value) else f"{value:.0f}d"


def fmt_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    if abs(value) >= 1e6:
        return f"${value / 1e6:.1f}M"
    if abs(value) >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:.0f}"


def fmt_money_md(value: float | None) -> str:
    """Money for a markdown context (captions, progress labels, st.markdown).

    Two unescaped dollar signs in one string are parsed by Streamlit as inline
    LaTeX, which silently ate the amounts on the initiatives page. Metric
    *values* are not markdown and can use `fmt_money` directly.
    """
    return fmt_money(value).replace("$", r"\$")


def delivery_items(work_items: pd.DataFrame) -> pd.DataFrame:
    """Program delivery scope only - demands and agents excluded (see
    NON_DELIVERY_ITEM_TYPES), and container rows excluded so an epic and its
    children are never counted as separate scope."""
    if work_items.empty:
        return work_items
    df = work_items[~work_items["item_type"].isin(NON_DELIVERY_ITEM_TYPES)]
    if "is_leaf" in df.columns:
        df = df[df["is_leaf"].astype(bool)]
    return df


def _counts(work_items: pd.DataFrame) -> dict:
    categories = work_items["status_category"] if not work_items.empty else pd.Series(dtype=object)
    return {
        "total": len(work_items),
        "done": int((categories == "Done").sum()),
        "in_progress": int((categories == "In Progress").sum()),
        "blocked": int((categories == "Blocked").sum()),
        "to_do": int((categories == "To Do").sum()),
        "cancelled": int((categories == "Cancelled").sum()),
        "unknown": int((categories == "Unknown").sum()),
    }


# --------------------------------------------------------- delivery metrics ---
def pct_complete(work_items: pd.DataFrame) -> MetricResult:
    """Delivered share of scope that was actually pursued.

    Cancelled and descoped work leaves the denominator entirely. Counting
    abandoned scope as delivered - which is what Jira's own status category does
    with "Descoped" - overstated this program by roughly five points.
    """
    df = delivery_items(work_items)
    counts = _counts(df)
    pursued = counts["total"] - counts["cancelled"]
    value = round(100 * counts["done"] / pursued, 1) if pursued else None
    insight = None
    if value is not None and counts["cancelled"]:
        insight = (f"{counts['done']:,} of {pursued:,} pursued items; "
                   f"{counts['cancelled']:,} cancelled and excluded")
    return MetricResult(
        key="pct_complete", label="% complete", value=value, display=fmt_pct(value),
        question="How much of the scope this program actually pursued has been delivered?",
        insight=insight, detail=counts,
    )


def descope_rate(work_items: pd.DataFrame) -> MetricResult:
    """Share of scope abandoned rather than delivered - a scope-discipline
    signal that was previously invisible, because descoped work was filed as
    done."""
    df = delivery_items(work_items)
    counts = _counts(df)
    value = round(100 * counts["cancelled"] / counts["total"], 1) if counts["total"] else None
    target = METRIC_TARGETS["descope_rate_pct"]
    insight = None
    if value is not None and value > target:
        insight = f"{counts['cancelled']:,} items dropped after being committed"
    return MetricResult(
        key="descope_rate", label="Descope rate", value=value, display=fmt_pct(value, 1),
        question="How much committed scope is being abandoned rather than delivered?",
        insight=insight, target=target, target_display=f"under {target:.0f}%",
        status=band(value, target, "lower_better"), detail=counts,
    )


def blocked_work(work_items: pd.DataFrame, now: pd.Timestamp | None = None) -> MetricResult:
    """Blocked items and how long they have been sitting.

    Blocked used to be folded into In Progress, which hid the most actionable
    state in the dataset: work holding capacity while waiting on someone else.
    """
    now = now or pd.Timestamp.now()
    df = delivery_items(work_items)
    blocked = df[df["status_category"] == "Blocked"]
    count = len(blocked)
    median_age = None
    if count and blocked["updated"].notna().any():
        ages = (now - blocked["updated"]).dt.total_seconds() / 86400.0
        median_age = round(float(ages.median()), 0)
    target = METRIC_TARGETS["work_item_blocked_days"]
    insight = (f"Median {median_age:.0f} days since last movement"
               if median_age is not None else None)
    status = GOOD if count == 0 else band(median_age, target, "lower_better")
    return MetricResult(
        key="blocked_work", label="Blocked", value=float(count), display=fmt_int(count),
        question="What work is holding capacity while waiting on somebody else?",
        insight=insight, target=target, target_display=f"cleared within {target}d",
        status=status, detail={"count": count, "median_age_days": median_age},
    )


def schedule_variance(work_items: pd.DataFrame, start, target_date,
                      now: pd.Timestamp | None = None) -> MetricResult:
    """Progress minus elapsed time, in percentage points.

    The single most useful program-level number: 40% complete is meaningless
    until you know whether 20% or 80% of the window has gone. Negative means
    behind the straight-line plan.
    """
    now = now or pd.Timestamp.now()
    completion = pct_complete(work_items).value
    start, target_date = pd.to_datetime(start), pd.to_datetime(target_date)
    if completion is None or pd.isna(start) or pd.isna(target_date) or target_date <= start:
        return MetricResult(
            key="schedule_variance", label="Schedule variance", display="-",
            question="Is this program ahead of or behind its straight-line plan?",
            coverage_note="Needs a start and target date on the program registry.",
        )
    elapsed = float(np.clip(100 * (now - start) / (target_date - start), 0, 100))
    value = round(completion - elapsed, 1)
    at_risk = METRIC_TARGETS["schedule_variance_at_risk_pct"]
    off_track = METRIC_TARGETS["schedule_variance_off_track_pct"]
    status = GOOD if value >= at_risk else (WATCH if value >= off_track else BAD)
    return MetricResult(
        key="schedule_variance", label="Schedule variance",
        value=value, display=f"{value:+.0f} pts",
        question="Is this program ahead of or behind its straight-line plan?",
        insight=f"{completion:.0f}% delivered against {elapsed:.0f}% of the window elapsed",
        target=at_risk, target_display=f"no worse than {at_risk:.0f} pts",
        status=status, detail={"pct_complete": completion, "pct_elapsed": round(elapsed, 1)},
    )


def health_label(variance: MetricResult) -> str:
    """Program health, derived from schedule variance rather than typed in by
    whoever last updated the tracker."""
    return {GOOD: "On Track", WATCH: "At Risk", BAD: "Off Track"}.get(variance.status, "Unknown")


def forecast_completion(work_items: pd.DataFrame, now: pd.Timestamp | None = None):
    """Projected finish date from the trailing delivery rate. Returns None when
    there is no throughput to extrapolate - an honest "cannot say" rather than
    a date invented from a zero rate."""
    from common import snapshots

    now = now or pd.Timestamp.now()
    df = delivery_items(work_items)
    counts = _counts(df)
    remaining = counts["total"] - counts["done"] - counts["cancelled"]
    if remaining <= 0:
        return now
    done = df[df["status_category"] == "Done"]
    dated = done["completed"].dropna() if not done.empty else pd.Series(dtype="datetime64[ns]")
    if not done.empty and (len(dated) / len(done) * 100 < METRIC_TARGETS["min_coverage_pct"]
                           or dated.empty or (now - dated.max()).days > 28):
        return None  # under-dated completions give a rate of zero, not a real forecast
    rate = snapshots.throughput(df, days=84, as_of=now)  # 12 weeks smooths sprint noise
    if rate <= 0:
        return None
    return now + pd.Timedelta(days=float(remaining / rate) * 7)


def delivery_confidence(work_items: pd.DataFrame, target_date,
                        now: pd.Timestamp | None = None) -> MetricResult:
    """Will the current delivery rate finish the remaining scope before the
    committed date? Expressed as the slip, in weeks, against that date."""
    now = now or pd.Timestamp.now()
    target_date = pd.to_datetime(target_date)
    forecast = forecast_completion(work_items, now)
    if forecast is None or pd.isna(target_date):
        return MetricResult(
            key="delivery_confidence", label="Forecast vs target", display="-",
            question="Will the current delivery rate hit the committed date?",
            coverage_note="No completions in the last 12 weeks, so there is no rate to project.",
        )
    slip_weeks = round((forecast - target_date).days / 7.0, 1)
    status = GOOD if slip_weeks <= 0 else (WATCH if slip_weeks <= 8 else BAD)
    display = "On target" if slip_weeks <= 0 else f"+{slip_weeks:.0f} wks"
    return MetricResult(
        key="delivery_confidence", label="Forecast vs target", value=slip_weeks, display=display,
        question="Will the current delivery rate hit the committed date?",
        insight=f"Projected finish {forecast:%b %Y} against a {target_date:%b %Y} target",
        target=0.0, target_display="on or before the target date", status=status,
        detail={"forecast": forecast, "target": target_date},
    )


def last_activity(work_items: pd.DataFrame, now: pd.Timestamp | None = None):
    """The most recent date anything actually happened in this source.

    Future dates are excluded: a demand with a go-live scheduled for next year
    is a plan, not activity, and counting it made freshness read as a negative
    number of days. An export that stopped being refreshed months ago otherwise
    cannot be told apart from a team that stopped delivering.
    """
    if work_items.empty:
        return None
    now = now or pd.Timestamp.now()
    stamps = []
    for col in ("updated", "completed", "created"):
        if col in work_items.columns:
            past = work_items[col][work_items[col] <= now]
            if not past.empty:
                stamps.append(past.max())
    stamps = [s for s in stamps if pd.notna(s)]
    return max(stamps) if stamps else None


def data_freshness(work_items: pd.DataFrame, now: pd.Timestamp | None = None) -> MetricResult:
    """Days since the source last showed any activity. A stale export silently
    drags every rate-based metric to zero, so it is reported as its own number
    rather than left for someone to infer."""
    now = now or pd.Timestamp.now()
    latest = last_activity(work_items)
    if latest is None:
        return MetricResult(key="data_freshness", label="Data freshness", display="-",
                            question="Is this source current enough to trust its trends?")
    days = round((now - latest).total_seconds() / 86400.0, 0)
    return MetricResult(
        key="data_freshness", label="Data freshness", value=days, display=fmt_days(days),
        question="Is this source current enough to trust its trends?",
        insight=f"Last activity {latest:%d %b %Y}",
        target=14.0, target_display="refreshed within 14d",
        status=band(days, 14.0, "lower_better"),
    )


def throughput_metric(work_items: pd.DataFrame, now: pd.Timestamp | None = None) -> MetricResult:
    """Items delivered per week, recent rate against the longer-run rate - the
    question being whether the program is speeding up or slowing down.

    Guarded by source freshness: a stale export would otherwise report 0/wk,
    which reads as "this team delivered nothing" when it means "nobody has
    re-exported the file".
    """
    from common import snapshots

    now = now or pd.Timestamp.now()
    df = delivery_items(work_items)
    done = df[df["status_category"] == "Done"]
    dated = done["completed"].dropna() if not done.empty else pd.Series(dtype="datetime64[ns]")

    # Throughput is only meaningful if completions carry a date. On the real
    # Jira export only 23% of Done issues have a resolution date and the newest
    # is months old, so a trailing rate there would read 0/wk - which says the
    # team delivered nothing, when it means the field is not being filled in.
    if not done.empty:
        pct_dated = round(100 * len(dated) / len(done), 1)
        stale = dated.empty or (now - dated.max()).days > 28
        if pct_dated < METRIC_TARGETS["min_coverage_pct"] or stale:
            note = (f"Only {pct_dated:.0f}% of completed items record a completion date"
                    if pct_dated < METRIC_TARGETS["min_coverage_pct"]
                    else "No completion has been dated in the last 28 days")
            return MetricResult(
                key="throughput", label="Throughput", display="-",
                question="How fast is this program actually delivering, and is that rate holding?",
                insight="Not measurable from this source",
                coverage_pct=pct_dated,
                coverage_note=f"{note}, so a delivery rate cannot be computed honestly.",
                status=UNKNOWN,
            )
    recent = snapshots.throughput(df, days=28, as_of=now)
    baseline = snapshots.throughput(df, days=84, as_of=now)
    delta_display, direction = None, "off"
    if baseline > 0:
        change = 100 * (recent - baseline) / baseline
        delta_display = f"{change:+.0f}% vs 12-wk rate"
        direction = "normal" if change >= 0 else "inverse"
    return MetricResult(
        key="throughput", label="Throughput", value=recent, display=f"{recent:.1f}/wk",
        question="How fast is this program actually delivering, and is that rate holding?",
        insight=f"12-week average {baseline:.1f}/wk" if baseline else None,
        delta_display=delta_display, delta_direction=direction,
        status=GOOD if baseline and recent >= baseline else (WATCH if recent > 0 else BAD),
    )


def cycle_time(work_items: pd.DataFrame) -> MetricResult:
    """Median days from creation to completion, with its coverage stated.

    Only 24% of the real program's completed issues carry a resolution date, so
    this number speaks for a quarter of the work. Saying so on the card is the
    difference between a metric and a misleading one.
    """
    df = delivery_items(work_items)
    done = df[df["status_category"] == "Done"]
    measurable = done[done["completed"].notna() & done["created"].notna()]
    if done.empty:
        return MetricResult(key="cycle_time", label="Cycle time (median)", display="-",
                            question="How long does a unit of work take from start to delivered?")
    pct = round(100 * len(measurable) / len(done), 1)
    if measurable.empty:
        return MetricResult(
            key="cycle_time", label="Cycle time (median)", display="-",
            question="How long does a unit of work take from start to delivered?",
            coverage_pct=0.0,
            coverage_note="No completed item records a completion date.")
    days = (measurable["completed"] - measurable["created"]).dt.total_seconds() / 86400.0
    value = round(float(days.median()), 0)
    reliable = pct >= METRIC_TARGETS["min_coverage_pct"]
    return MetricResult(
        key="cycle_time", label="Cycle time (median)", value=value, display=fmt_days(value),
        question="How long does a unit of work take from start to delivered?",
        insight=f"85th percentile {days.quantile(0.85):.0f}d",
        coverage_pct=pct,
        coverage_note=_coverage_note(pct, "completed items"),
        status=GOOD if reliable else UNKNOWN,
    )


def aging_work(work_items: pd.DataFrame, now: pd.Timestamp | None = None) -> MetricResult:
    """Open items with no movement past the staleness threshold - the backlog
    that is decaying rather than progressing."""
    now = now or pd.Timestamp.now()
    df = delivery_items(work_items)
    open_items = df[df["status_category"].isin(["To Do", "In Progress", "Blocked"])]
    threshold = METRIC_TARGETS["work_item_stale_days"]
    if open_items.empty or open_items["updated"].isna().all():
        return MetricResult(key="aging_work", label="Stale open work", display="-",
                            question="What is sitting untouched and quietly slipping?")
    idle_days = (now - open_items["updated"]).dt.total_seconds() / 86400.0
    stale = int((idle_days > threshold).sum())
    share = round(100 * stale / len(open_items), 1)
    return MetricResult(
        key="aging_work", label="Stale open work", value=float(stale), display=fmt_int(stale),
        question="What is sitting untouched and quietly slipping?",
        insight=f"{share:.0f}% of open work untouched for {threshold}+ days",
        target=0.0, target_display=f"no item idle beyond {threshold}d",
        status=GOOD if share < 10 else (WATCH if share < 30 else BAD),
        detail={"stale": stale, "open": len(open_items), "share_pct": share},
    )


def unassigned_work(work_items: pd.DataFrame) -> MetricResult:
    """Open work nobody owns. Distinct from unallocated capacity: this is work
    that cannot start because it has no name against it."""
    df = delivery_items(work_items)
    open_items = df[df["status_category"].isin(["To Do", "In Progress", "Blocked"])]
    if open_items.empty:
        return MetricResult(key="unassigned", label="Unowned open work", display="-",
                            question="What open work has nobody accountable for it?")
    count = int(open_items["owner"].isna().sum())
    share = round(100 * count / len(open_items), 1)
    return MetricResult(
        key="unassigned", label="Unowned open work", value=float(count), display=fmt_int(count),
        question="What open work has nobody accountable for it?",
        insight=f"{share:.0f}% of open items have no owner",
        target=0.0, target_display="every open item owned",
        status=GOOD if share < 5 else (WATCH if share < 20 else BAD),
    )


# ----------------------------------------------------------- money metrics ---
def burn_efficiency(work_items: pd.DataFrame, budget, spent) -> MetricResult:
    """Budget consumed per unit of scope delivered.

    Above 1.0 means money is going out faster than work is coming in. This is
    the number that turns a "% spent" reading into a judgement.
    """
    completion = pct_complete(work_items).value
    budget = float(budget) if budget and not pd.isna(budget) else None
    spent = float(spent) if spent and not pd.isna(spent) else None
    if not budget or spent is None or not completion:
        return MetricResult(key="burn_efficiency", label="Burn efficiency", display="-",
                            question="Is spend running ahead of delivered scope?",
                            coverage_note="Needs a budget, spend and measurable progress.")
    spent_pct = 100 * spent / budget
    value = round(spent_pct / completion, 2)
    target = METRIC_TARGETS["burn_efficiency_at_risk"]
    return MetricResult(
        key="burn_efficiency", label="Burn efficiency", value=value, display=f"{value:.2f}x",
        question="Is spend running ahead of delivered scope?",
        insight=f"{spent_pct:.0f}% of budget spent for {completion:.0f}% delivered",
        target=target, target_display=f"under {target:.1f}x",
        status=band(value, target, "lower_better"),
        detail={"spent_pct": round(spent_pct, 1), "pct_complete": completion},
    )


# ------------------------------------------------------------ flow metrics ---
def net_flow(arrivals: pd.Series, completions: pd.Series,
             days: int | None = None, now: pd.Timestamp | None = None) -> MetricResult:
    """Arrivals divided by completions over the trailing window.

    Above 1.0 the backlog grows no matter how hard anyone works, which is a
    capacity conversation rather than a delivery one.
    """
    now = now or pd.Timestamp.now()
    days = days or METRIC_TARGETS["flow_window_days"]
    window_start = now - pd.Timedelta(days=days)
    arrived = int(((arrivals >= window_start) & (arrivals <= now)).sum())
    completed = int(((completions >= window_start) & (completions <= now)).sum())
    if completed == 0:
        display = f"{arrived} in / 0 out"
        return MetricResult(
            key="net_flow", label="Net flow", value=None, display=display,
            question="Is the organisation taking on more than it finishes?",
            insight="Nothing completed in the window", status=BAD if arrived else UNKNOWN)
    value = round(arrived / completed, 2)
    target = METRIC_TARGETS["net_flow_ratio"]
    return MetricResult(
        key="net_flow", label="Net flow", value=value, display=f"{value:.2f}x",
        question="Is the organisation taking on more than it finishes?",
        insight=f"{arrived:,} arrived vs {completed:,} completed in {days} days",
        target=target, target_display=f"at or below {target:.1f}x",
        status=band(value, target, "lower_better"),
        detail={"arrived": arrived, "completed": completed, "days": days},
    )
