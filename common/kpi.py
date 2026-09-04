"""Aggregations over the normalized tables.

Scalar judgements live in `common/metrics.py` (a number plus its question,
target and coverage). This module returns the tidy frames those judgements are
drawn on and that the charts render - breakdowns, roll-ups, ranked tables.

Everything program-shaped is computed over `work_items`, so a program delivered
through ServiceNow and one delivered through Jira are measured the same way.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import metrics as mx
from common import snapshots
from common.adapters.demand_intake import PIPELINE_STAGES
from common.adapters.registry import UNATTACHED
from common.config import METRIC_TARGETS

STATUS_ORDER = ["To Do", "In Progress", "Blocked", "Done", "Cancelled", "Unknown"]
OPEN_STATUSES = ["To Do", "In Progress", "Blocked"]


def _now() -> pd.Timestamp:
    return pd.Timestamp.now()


def counts(df: pd.DataFrame, col: str, top_n: int | None = None) -> pd.DataFrame:
    """Value counts as a tidy two-column frame, blanks excluded."""
    if col not in df.columns or df.empty:
        return pd.DataFrame(columns=[col, "count"])
    series = df[col].dropna()
    series = series[series.astype(str).str.strip() != ""]
    out = series.value_counts().reset_index()
    out.columns = [col, "count"]
    return out.head(top_n) if top_n else out


def _explode_counts(df: pd.DataFrame, col: str, delimiter: str = ";#",
                    top_n: int | None = None) -> pd.DataFrame:
    """For multi-select fields packed into one delimited string, so a combination
    does not fragment the breakdown into its own one-off bucket."""
    if col not in df.columns or df.empty:
        return pd.DataFrame(columns=[col, "count"])
    series = df[col].dropna().astype(str)
    series = series[series.str.strip() != ""]
    exploded = series.str.split(delimiter).explode().str.strip()
    exploded = exploded[exploded != ""]
    out = exploded.value_counts().reset_index()
    out.columns = [col, "count"]
    return out.head(top_n) if top_n else out


# ------------------------------------------------------------- work items ---
def status_breakdown(work_items: pd.DataFrame) -> pd.DataFrame:
    out = counts(mx.delivery_items(work_items), "status_category")
    rank = {c: i for i, c in enumerate(STATUS_ORDER)}
    out["_o"] = out["status_category"].map(rank).fillna(99)
    return out.sort_values("_o").drop(columns="_o").reset_index(drop=True)


def status_by_dimension(work_items: pd.DataFrame, dimension: str,
                        top_n: int = 15) -> pd.DataFrame:
    """Tidy cross-tab of `dimension` x status category, for a stacked bar."""
    df = mx.delivery_items(work_items)
    if df.empty or dimension not in df.columns:
        return pd.DataFrame(columns=[dimension, "status_category", "count"])
    keep = df[dimension].value_counts().head(top_n).index
    sub = df[df[dimension].isin(keep)]
    out = sub.groupby([dimension, "status_category"], dropna=False).size().reset_index(name="count")
    out["status_category"] = pd.Categorical(out["status_category"], categories=STATUS_ORDER,
                                             ordered=True)
    return out.sort_values([dimension, "status_category"])


def dimension_progress(work_items: pd.DataFrame, dimension: str = "domain",
                       top_n: int = 20) -> pd.DataFrame:
    """Per-value progress table: how much scope, how much delivered, how much
    stuck. Sorted by open work rather than by size, so the row a manager needs
    to act on is at the top rather than the biggest one."""
    df = mx.delivery_items(work_items)
    if df.empty or dimension not in df.columns:
        return pd.DataFrame(columns=[dimension, "total", "done", "open", "blocked", "pct_done"])
    grouped = df.groupby(dimension, dropna=False).agg(
        total=("item_key", "count"),
        done=("status_category", lambda s: int((s == "Done").sum())),
        blocked=("status_category", lambda s: int((s == "Blocked").sum())),
        cancelled=("status_category", lambda s: int((s == "Cancelled").sum())),
    ).reset_index()
    grouped["open"] = grouped["total"] - grouped["done"] - grouped["cancelled"]
    pursued = (grouped["total"] - grouped["cancelled"]).replace(0, np.nan)
    grouped["pct_done"] = (100 * grouped["done"] / pursued).round(1).fillna(0)
    return grouped.sort_values(["blocked", "open"], ascending=False).head(top_n)


def workstream_rollup(work_items: pd.DataFrame, top_n: int = 25) -> pd.DataFrame:
    """Progress per workstream (epic, phase, WBS branch) with an at-risk flag.
    Replaces the old epic table, which listed children and % done but gave no
    reason to look at any particular row."""
    table = dimension_progress(work_items, "workstream", top_n=top_n)
    if table.empty:
        return table
    table["at_risk"] = (table["blocked"] > 0) | (table["pct_done"] < 25)
    return table


def aging_buckets(work_items: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Open work by age since creation - a distribution rather than a mean,
    because the tail is the part that matters."""
    now = now or _now()
    df = mx.delivery_items(work_items)
    open_items = df[df["status_category"].isin(OPEN_STATUSES)]
    labels = ["0-30 days", "31-90 days", "91-180 days", "181-365 days", "365+ days"]
    if open_items.empty or open_items["created"].isna().all():
        return pd.DataFrame({"bucket": labels, "count": [0] * len(labels)})
    age = (now - open_items["created"]).dt.total_seconds() / 86400.0
    bucket = pd.cut(age, bins=[-1, 30, 90, 180, 365, float("inf")], labels=labels)
    out = bucket.value_counts().reindex(labels).fillna(0).astype(int).reset_index()
    out.columns = ["bucket", "count"]
    return out


def monthly_flow(work_items: pd.DataFrame, months: int = 18) -> pd.DataFrame:
    """Arrivals vs completions per month, plus the net change in open work.
    The shape that answers "are we keeping up" - which a created-only trend
    never could."""
    df = mx.delivery_items(work_items)
    if df.empty:
        return pd.DataFrame(columns=["month", "created", "completed", "net"])
    now = _now()
    created = (df.dropna(subset=["created"]).assign(
        month=lambda d: d["created"].dt.to_period("M").dt.to_timestamp())
        .groupby("month").size().rename("created"))
    finished = df[(df["status_category"] == "Done") & df["completed"].notna()]
    completed = (finished.assign(
        month=lambda d: d["completed"].dt.to_period("M").dt.to_timestamp())
        .groupby("month").size().rename("completed"))
    out = pd.concat([created, completed], axis=1).fillna(0).astype(int).reset_index()
    out["net"] = out["created"] - out["completed"]
    # Scheduled future go-lives are a plan, not flow. Including them drew a
    # long dead tail on the chart that read as the work drying up.
    out = out[out["month"] <= now.to_period("M").to_timestamp()]
    return out.sort_values("month").tail(months)


def blocked_table(work_items: pd.DataFrame, limit: int = 200,
                  now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or _now()
    df = mx.delivery_items(work_items)
    blocked = df[df["status_category"] == "Blocked"].copy()
    if blocked.empty:
        return pd.DataFrame(columns=["item_key", "title", "owner", "workstream", "days_blocked"])
    blocked["days_blocked"] = ((now - blocked["updated"]).dt.total_seconds() / 86400.0).round(0)
    cols = ["item_key", "title", "owner", "workstream", "status_raw", "days_blocked"]
    cols = [c for c in cols if c in blocked.columns]
    return blocked.sort_values("days_blocked", ascending=False)[cols].head(limit)


def stale_table(work_items: pd.DataFrame, days: int | None = None, limit: int = 200,
                now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or _now()
    days = days or METRIC_TARGETS["work_item_stale_days"]
    df = mx.delivery_items(work_items)
    open_items = df[df["status_category"].isin(OPEN_STATUSES)].copy()
    if open_items.empty:
        return pd.DataFrame(columns=["item_key", "title", "owner", "days_idle"])
    open_items["days_idle"] = ((now - open_items["updated"]).dt.total_seconds() / 86400.0).round(0)
    stale = open_items[open_items["days_idle"] > days]
    cols = ["item_key", "title", "owner", "status_raw", "workstream", "days_idle"]
    cols = [c for c in cols if c in stale.columns]
    return stale.sort_values("days_idle", ascending=False)[cols].head(limit)


def overdue_table(work_items: pd.DataFrame, limit: int = 200,
                  now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or _now()
    df = mx.delivery_items(work_items)
    open_items = df[df["status_category"].isin(OPEN_STATUSES)]
    overdue = open_items[open_items["due_date"].notna() & (open_items["due_date"] < now)].copy()
    if overdue.empty:
        return pd.DataFrame(columns=["item_key", "title", "owner", "due_date", "days_overdue"])
    overdue["days_overdue"] = ((now - overdue["due_date"]).dt.total_seconds() / 86400.0).round(0)
    cols = ["item_key", "title", "owner", "status_raw", "due_date", "days_overdue"]
    cols = [c for c in cols if c in overdue.columns]
    return overdue.sort_values("days_overdue", ascending=False)[cols].head(limit)


def owner_workload(work_items: pd.DataFrame, top_n: int = 15,
                   open_only: bool = True) -> pd.DataFrame:
    df = mx.delivery_items(work_items)
    if open_only and not df.empty:
        df = df[df["status_category"].isin(OPEN_STATUSES)]
    return counts(df, "owner", top_n)


# ------------------------------------------------------ program roll-ups ---
def program_scorecard(programs: pd.DataFrame, work_items: pd.DataFrame,
                      now: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per program with every headline judgement already computed.

    This is the table the Programs hub, the Strategic initiatives page and the
    portfolio KPIs all read from, which is what keeps a program's numbers
    identical wherever it appears.
    """
    now = now or _now()
    rows = []
    for _, program in programs.iterrows():
        pid = program["program_id"]
        items = work_items[work_items["program_id"] == pid] if not work_items.empty else work_items
        delivery = mx.delivery_items(items)
        completion = mx.pct_complete(items)
        variance = mx.schedule_variance(items, program.get("start_date"),
                                        program.get("target_date"), now)
        descope = mx.descope_rate(items)
        burn = mx.burn_efficiency(items, program.get("budget_usd"), program.get("spent_usd"))
        confidence = mx.delivery_confidence(items, program.get("target_date"), now)
        counts_ = mx._counts(delivery)
        rows.append({
            "program_id": pid,
            "name": program.get("name"),
            "is_strategic": bool(program.get("is_strategic", False)),
            "parent_program_id": program.get("parent_program_id"),
            "portfolio": program.get("portfolio"),
            "domain": program.get("domain"),
            "phase": program.get("phase"),
            "executive_sponsor": program.get("executive_sponsor"),
            "program_owner": program.get("program_owner"),
            "source_system": program.get("source_system"),
            "target_date": program.get("target_date"),
            "target_quarter": program.get("target_quarter"),
            "budget_usd": program.get("budget_usd"),
            "spent_usd": program.get("spent_usd"),
            "total": counts_["total"],
            "done": counts_["done"],
            "open": counts_["total"] - counts_["done"] - counts_["cancelled"],
            "blocked": counts_["blocked"],
            "cancelled": counts_["cancelled"],
            "pct_complete": completion.value,
            "pct_elapsed": variance.detail.get("pct_elapsed"),
            "schedule_variance": variance.value,
            "health": mx.health_label(variance),
            "health_status": variance.status,
            "descope_rate": descope.value,
            "burn_efficiency": burn.value,
            "forecast_slip_weeks": confidence.value,
            "throughput": mx.throughput_metric(items, now).value,
            "segments": [("Done", counts_["done"]), ("In Progress", counts_["in_progress"]),
                         ("Blocked", counts_["blocked"]), ("To Do", counts_["to_do"])],
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Programs needing attention first: worst schedule variance at the top.
    return out.sort_values("schedule_variance", ascending=True, na_position="last").reset_index(drop=True)


def portfolio_health(scorecard: pd.DataFrame) -> dict:
    """Counts by derived health band, for the Overview's headline judgement."""
    if scorecard.empty:
        return {"total": 0, "on_track": 0, "at_risk": 0, "off_track": 0, "unknown": 0}
    health = scorecard["health"]
    return {
        "total": len(scorecard),
        "on_track": int((health == "On Track").sum()),
        "at_risk": int((health == "At Risk").sum()),
        "off_track": int((health == "Off Track").sum()),
        "unknown": int((health == "Unknown").sum()),
    }


def portfolio_history(work_items: pd.DataFrame, weeks: int = 26) -> pd.DataFrame:
    return snapshots.weekly_history(mx.delivery_items(work_items), weeks=weeks)


# ---------------------------------------------------------------- demands ---
DEMAND_STATUS_ORDER = ["To Do", "In Progress", "Blocked", "Done", "Cancelled"]


def demand_stage_times(demands: pd.DataFrame) -> pd.DataFrame:
    """Median and 85th-percentile duration of each intake stage, against its SLA.

    The intake data carries four real timestamps, which makes this the one place
    in the app where a genuine bottleneck can be identified rather than guessed.
    """
    rows = []
    for label, start_col, end_col, target_key in PIPELINE_STAGES:
        if demands.empty or start_col not in demands.columns or end_col not in demands.columns:
            continue
        pair = demands[[start_col, end_col]].dropna()
        # A stage that has not finished yet cannot contribute a duration: a
        # go-live scheduled for next year would otherwise be measured as an
        # enormous - and entirely imaginary - cycle time.
        pair = pair[pair[end_col] <= _now()]
        # Backdated corrections produce negative durations; they are data entry
        # artefacts, not fast stages, so they are excluded rather than averaged in.
        days = (pair[end_col] - pair[start_col]).dt.total_seconds() / 86400.0
        days = days[days >= 0]
        target = METRIC_TARGETS[target_key]
        rows.append({
            "stage": label,
            "median_days": round(float(days.median()), 0) if not days.empty else None,
            "p85_days": round(float(days.quantile(0.85)), 0) if not days.empty else None,
            "target_days": target,
            "measured": len(days),
            "coverage_pct": round(100 * len(days) / len(demands), 1) if len(demands) else 0.0,
            "over_target": (bool(days.median() > target) if not days.empty else False),
        })
    return pd.DataFrame(rows)


def demand_bottleneck(stage_times: pd.DataFrame) -> dict | None:
    """The stage furthest past its SLA, in multiples of target - which is the
    fair comparison, since a 10-day and a 90-day stage are not comparable in
    absolute days."""
    if stage_times.empty or stage_times["median_days"].isna().all():
        return None
    table = stage_times.dropna(subset=["median_days"]).copy()
    table["ratio"] = table["median_days"] / table["target_days"]
    worst = table.sort_values("ratio", ascending=False).iloc[0]
    return {
        "stage": worst["stage"],
        "median_days": worst["median_days"],
        "target_days": worst["target_days"],
        "ratio": round(float(worst["ratio"]), 2),
    }


def demand_cancellation_waste(demands: pd.DataFrame) -> dict:
    """Cancellation rate plus the effort booked against work that never shipped.

    A rate alone invites a shrug; the hours attached to it are what make the
    number a decision - it is the cost of triaging demands that die.
    """
    total = len(demands)
    if not total:
        return {"cancelled": 0, "rate_pct": 0.0, "wasted_hours": 0.0, "estimated_share_pct": 0.0}
    cancelled = demands[demands["status_category"] == "Cancelled"]
    hours = cancelled["hours_estimate"].dropna() if "hours_estimate" in cancelled.columns else pd.Series(dtype=float)
    return {
        "cancelled": len(cancelled),
        "rate_pct": round(100 * len(cancelled) / total, 1),
        "wasted_hours": float(hours.sum()),
        "estimated_share_pct": round(100 * len(hours) / len(cancelled), 1) if len(cancelled) else 0.0,
    }


def demand_aging(demands: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Open demands bucketed by age. Demands carry no due date, so age since
    intake is the only honest measure of lateness."""
    now = now or _now()
    labels = ["0-30 days", "31-90 days", "91-180 days", "181-365 days", "365+ days"]
    open_demands = demands[~demands["status_category"].isin(["Done", "Cancelled"])]
    if open_demands.empty:
        return pd.DataFrame({"bucket": labels, "count": [0] * len(labels)})
    age = (now - open_demands["created"]).dt.total_seconds() / 86400.0
    bucket = pd.cut(age, bins=[-1, 30, 90, 180, 365, float("inf")], labels=labels)
    out = bucket.value_counts().reindex(labels).fillna(0).astype(int).reset_index()
    out.columns = ["bucket", "count"]
    return out


def demand_oldest_open(demands: pd.DataFrame, limit: int = 200,
                       now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or _now()
    open_demands = demands[~demands["status_category"].isin(["Done", "Cancelled"])].copy()
    if open_demands.empty:
        return open_demands
    open_demands["age_days"] = ((now - open_demands["created"]).dt.total_seconds() / 86400.0).round(0)
    cols = ["demand_key", "title", "requestor", "status", "assignment_group", "created", "age_days"]
    cols = [c for c in cols if c in open_demands.columns]
    return open_demands.sort_values("age_days", ascending=False)[cols].head(limit)


def demand_delay_reasons(demands: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """The `Delay Type` field - captured by the intake process and never once
    displayed. It is the literal answer to "why are we late"."""
    return _explode_counts(demands, "delay_type", top_n=top_n)


def demand_approval_backlog(demands: pd.DataFrame) -> pd.DataFrame:
    """Where demands sit in the investment-council approval flow. On the real
    data 1,593 of 1,866 are "Pending Review" - a governance queue that no view
    in the app previously surfaced."""
    return counts(demands, "ic_approval_status")


def demand_monthly_flow(demands: pd.DataFrame, months: int = 18) -> pd.DataFrame:
    """Intake vs completion vs cancellation per month."""
    if demands.empty:
        return pd.DataFrame(columns=["month", "created", "completed", "cancelled", "net"])
    frame = demands.dropna(subset=["created"]).copy()
    frame["month"] = frame["created"].dt.to_period("M").dt.to_timestamp()
    created = frame.groupby("month").size().rename("created")
    done = demands[demands["status_category"] == "Done"].dropna(subset=["go_live_date"]).copy()
    if done.empty:
        completed = pd.Series(dtype=int, name="completed")
    else:
        done["month"] = done["go_live_date"].dt.to_period("M").dt.to_timestamp()
        completed = done.groupby("month").size().rename("completed")
    killed = demands[demands["status_category"] == "Cancelled"].dropna(subset=["created"]).copy()
    killed["month"] = killed["created"].dt.to_period("M").dt.to_timestamp()
    cancelled = killed.groupby("month").size().rename("cancelled")

    out = pd.concat([created, completed, cancelled], axis=1).fillna(0).astype(int).reset_index()
    out.columns = ["month", "created", "completed", "cancelled"]
    out["net"] = out["created"] - out["completed"] - out["cancelled"]
    out = out[out["month"] <= _now().to_period("M").to_timestamp()]
    return out.sort_values("month").tail(months)


def demand_load_by_program(demands: pd.DataFrame, programs: pd.DataFrame,
                           top_n: int = 12) -> pd.DataFrame:
    """Which programs the intake queue is actually landing on."""
    if demands.empty or "program_id" not in demands.columns:
        return pd.DataFrame(columns=["program", "count"])
    names = dict(zip(programs["program_id"], programs["name"])) if not programs.empty else {}
    labelled = demands["program_id"].map(lambda p: names.get(p, "Unattached"))
    out = labelled.value_counts().reset_index()
    out.columns = ["program", "count"]
    return out.head(top_n)


def demand_request_type_breakdown(demands: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    return _explode_counts(demands, "request_type", top_n=top_n)


def demand_team_breakdown(demands: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    return _explode_counts(demands, "team_required", top_n=top_n)


def demand_status_category_breakdown(demands: pd.DataFrame) -> pd.DataFrame:
    out = counts(demands, "status_category")
    rank = {c: i for i, c in enumerate(DEMAND_STATUS_ORDER)}
    out["_o"] = out["status_category"].map(rank).fillna(99)
    return out.sort_values("_o").drop(columns="_o").reset_index(drop=True)


def demand_assignment_group_breakdown(demands: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    return counts(demands, "assignment_group", top_n)


# ----------------------------------------------------------------- agents ---
ROLLOUT_ORDER = ["Idea", "Scoping", "WIP", "UAT", "Live", "On Hold"]


def agent_funnel(board: pd.DataFrame) -> pd.DataFrame:
    """Agents by rollout stage, in rollout order.

    Ordering matters: the old alphabetical bar could not show that the board is
    bottom-heavy, which is the single most important thing about it.
    """
    out = counts(board, "status")
    if out.empty:
        return out
    rank = {s: i for i, s in enumerate(ROLLOUT_ORDER)}
    out["_o"] = out["status"].map(rank).fillna(99)
    return out.sort_values("_o").drop(columns="_o").reset_index(drop=True)


def agent_owner_concentration(board: pd.DataFrame, top: int = 2) -> dict:
    """How much of the board rests on its busiest few owners - a bus-factor
    reading. On the real board two people hold roughly two thirds of it."""
    owners = board["owner"].dropna() if "owner" in board.columns else pd.Series(dtype=object)
    if owners.empty:
        return {"share_pct": None, "top_owners": [], "distinct_owners": 0, "unowned": len(board)}
    tally = owners.value_counts()
    return {
        "share_pct": round(100 * tally.head(top).sum() / len(owners), 1),
        "top_owners": list(tally.head(top).index),
        "distinct_owners": int(tally.size),
        "unowned": int(len(board) - len(owners)),
    }


def agent_time_to_live(board: pd.DataFrame) -> dict:
    """Median days from an agent first appearing to going live."""
    if board.empty or "went_live" not in board.columns or "created" not in board.columns:
        return {"median_days": None, "measured": 0, "live": 0}
    live = board[board["went_live"].notna() & board["created"].notna()]
    if live.empty:
        return {"median_days": None, "measured": 0,
                "live": int((board.get("status") == "Live").sum())}
    days = (live["went_live"] - live["created"]).dt.total_seconds() / 86400.0
    return {"median_days": round(float(days.median()), 0), "measured": len(live),
            "live": int((board["status"] == "Live").sum()) if "status" in board.columns else len(live)}


def agent_stalled(board: pd.DataFrame, days: int | None = None,
                  now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Agents with no movement past the threshold and not yet live - the ones
    quietly consuming a slot on the board without progressing."""
    now = now or _now()
    days = days or METRIC_TARGETS["agent_stalled_days"]
    if board.empty or "updated" not in board.columns:
        return pd.DataFrame(columns=["name", "owner", "sub_domain", "status", "days_idle"])
    candidates = board[board["updated"].notna()].copy()
    if "status" in candidates.columns:
        candidates = candidates[candidates["status"] != "Live"]
    candidates["days_idle"] = ((now - candidates["updated"]).dt.total_seconds() / 86400.0).round(0)
    stalled = candidates[candidates["days_idle"] > days]
    cols = [c for c in ["name", "owner", "sub_domain", "status", "days_idle"] if c in stalled.columns]
    return stalled.sort_values("days_idle", ascending=False)[cols]


def agent_white_space(board: pd.DataFrame, demands: pd.DataFrame, programs: pd.DataFrame,
                      top_n: int = 12) -> pd.DataFrame:
    """Demand volume per program against how many agents serve it.

    The join is on `program_id`, not on names. An earlier version compared the
    board's sub-domain ("GOSC") against the intake queue's assignment group
    ("GOSC POD") - two different vocabularies - and so reported zero agents in
    areas that have 49. The registry attach rules are the only well-defined
    bridge between the two feeds, which is precisely what they are for.

    The question this answers is where the AI effort is *not* going: a program
    generating a lot of demand with no agents behind it is an opportunity.
    """
    columns = ["program", "agents", "demands", "agents_per_100_demands"]
    if demands.empty or "program_id" not in demands.columns:
        return pd.DataFrame(columns=columns)

    names = dict(zip(programs["program_id"], programs["name"])) if not programs.empty else {}
    agent_counts = (board["program_id"].value_counts() if "program_id" in board.columns
                    else pd.Series(dtype=int))
    demand_counts = demands["program_id"].value_counts()

    keys = [k for k in set(agent_counts.index) | set(demand_counts.index) if k != UNATTACHED]
    if not keys:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame({
        "program": [names.get(k, k) for k in keys],
        "agents": [int(agent_counts.get(k, 0)) for k in keys],
        "demands": [int(demand_counts.get(k, 0)) for k in keys],
    })
    # Normalised so a small program with no agents is comparable to a large one.
    # np.nan rather than pd.NA: the latter has no __round__ and blows up here.
    ratio = 100 * table["agents"] / table["demands"].replace(0, np.nan)
    table["agents_per_100_demands"] = ratio.round(1)
    # A program raising no demand cannot be white space - there is no unmet
    # need to leave uncovered - so it is excluded rather than ranked as NaN.
    table = table[table["demands"] > 0]
    return table.sort_values(["agents_per_100_demands", "demands"],
                             ascending=[True, False]).head(top_n)


def agent_demand_linkage(board: pd.DataFrame) -> dict:
    """Share of the board traceable to a formal demand rather than
    self-originated - a governance signal about whether the AI portfolio
    answers the business or itself."""
    total = len(board)
    if not total:
        return {"linked": 0, "share_pct": 0.0, "self_originated": 0}
    linked = int(board["demand_intake_number"].notna().sum()) if "demand_intake_number" in board.columns else 0
    return {
        "linked": linked,
        "share_pct": round(100 * linked / total, 1),
        "self_originated": total - linked,
    }


def agent_breakdown(board: pd.DataFrame, column: str, top_n: int = 15) -> pd.DataFrame:
    return counts(board, column, top_n)


# --------------------------------------------------------------- coverage ---
#: Fields whose emptiness silently breaks a metric, and the metric they break.
COVERAGE_FIELDS = {
    "work_items": [
        ("domain", "Segmenting delivery by business domain"),
        ("owner", "Workload and accountability views"),
        ("due_date", "Overdue and schedule-risk reporting"),
        ("completed", "Cycle time, throughput and forecasting"),
        ("effort_hours", "Effort-weighted progress and sizing"),
        ("workstream", "Workstream roll-up"),
    ],
    "demands": [
        ("estimation_approval_date", "Triage and estimation SLA"),
        ("development_start_date", "Resourcing queue time"),
        ("go_live_date", "End-to-end delivery time"),
        ("hours_estimate", "Cost of cancelled demand"),
        ("delay_type", "Root-cause analysis of late demands"),
        ("vp_leader", "Leadership attribution"),
    ],
    "board_items": [
        ("status", "Rollout funnel"),
        ("eta", "Time-to-live and late-agent detection"),
        ("owner", "Owner concentration and bus factor"),
        ("demand_intake_number", "Demand-linked vs self-originated split"),
        ("platform", "Platform mix"),
    ],
}


def field_coverage(frames: dict) -> pd.DataFrame:
    """How complete each metric-critical field is, per table, and what is lost
    when it is empty.

    This is the panel that turns eight blank charts into one governance
    backlog: instead of rendering an empty bar, the app names the field, the
    percentage, and the metric that cannot be computed without it.
    """
    rows = []
    for table, fields in COVERAGE_FIELDS.items():
        frame = frames.get(table)
        if frame is None or frame.empty:
            continue
        for column, enables in fields:
            if column not in frame.columns:
                pct = 0.0
            else:
                series = frame[column]
                populated = series.notna()
                if series.dtype == object:
                    populated &= series.astype(str).str.strip().ne("")
                pct = round(100 * float(populated.mean()), 1)
            rows.append({
                "table": table,
                "field": column,
                "coverage_pct": pct,
                "band": mx.coverage_band(pct),
                "enables": enables,
                "rows": len(frame),
            })
    out = pd.DataFrame(rows)
    return out.sort_values("coverage_pct") if not out.empty else out


def source_freshness(work_items: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Days since each source last showed activity - the check that stops a
    stale export being read as a stalled team."""
    now = now or _now()
    if work_items.empty:
        return pd.DataFrame(columns=["source_file", "source_system", "rows", "last_activity", "days_stale"])
    rows = []
    for (source_file, source_system), group in work_items.groupby(["source_file", "source_system"]):
        latest = mx.last_activity(group)
        rows.append({
            "source_file": source_file,
            "source_system": source_system,
            "rows": len(group),
            "last_activity": latest,
            "days_stale": round((now - latest).total_seconds() / 86400.0, 0) if latest is not None else None,
        })
    return pd.DataFrame(rows).sort_values("days_stale", ascending=False, na_position="first")


# ------------------------------------------------------- attention ranking ---
def attention_items(work_items: pd.DataFrame, demands: pd.DataFrame, board: pd.DataFrame,
                    scorecard: pd.DataFrame, now: pd.Timestamp | None = None,
                    limit: int = 60) -> pd.DataFrame:
    """One ranked list of what needs a decision, across all four activities.

    Managers do not want four dashboards to correlate by eye; they want to know
    what to do today. Severity is the ordering, and every row names the thing,
    why it is here, and where to go.
    """
    now = now or _now()
    rows = []

    if not scorecard.empty:
        for _, program in scorecard[scorecard["health"] == "Off Track"].iterrows():
            rows.append({
                "severity": 1, "area": "Program", "item": program["name"],
                "issue": f"Off track - {program['schedule_variance']:+.0f} pts behind plan",
                "detail": f"{program['pct_complete']:.0f}% delivered, "
                          f"{program['pct_elapsed']:.0f}% of the window elapsed",
                "link": f"?program={program['program_id']}",
            })
        for _, program in scorecard[(scorecard["blocked"] > 0)].nlargest(8, "blocked").iterrows():
            rows.append({
                "severity": 2, "area": "Program", "item": program["name"],
                "issue": f"{int(program['blocked'])} items blocked",
                "detail": "Work holding capacity while waiting on someone else",
                "link": f"?program={program['program_id']}",
            })

    if not demands.empty:
        threshold = METRIC_TARGETS["demand_aging_days"]
        oldest = demand_oldest_open(demands, limit=10, now=now)
        for _, demand in oldest.iterrows():
            if demand.get("age_days", 0) > threshold:
                rows.append({
                    "severity": 1 if demand["age_days"] > 365 else 2,
                    "area": "Demand", "item": demand.get("title") or demand.get("demand_key"),
                    "issue": f"Open {demand['age_days']:.0f} days",
                    "detail": f"{demand.get('status', '')} - {demand.get('assignment_group', '')}",
                    "link": "demands",
                })

    stalled = agent_stalled(board, now=now)
    for _, agent in stalled.head(8).iterrows():
        rows.append({
            "severity": 3, "area": "Agent", "item": agent.get("name"),
            "issue": f"No movement in {agent['days_idle']:.0f} days",
            "detail": f"{agent.get('status', '')} - owner {agent.get('owner') or 'unassigned'}",
            "link": "agents",
        })

    blocked = blocked_table(work_items, limit=10, now=now)
    for _, item in blocked.iterrows():
        if item.get("days_blocked", 0) > METRIC_TARGETS["work_item_blocked_days"]:
            rows.append({
                "severity": 2, "area": "Work item", "item": item.get("title"),
                "issue": f"Blocked {item['days_blocked']:.0f} days",
                "detail": f"{item.get('workstream') or ''} - owner {item.get('owner') or 'unassigned'}",
                "link": "programs",
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["severity", "area", "item", "issue", "detail", "link"])
    return out.sort_values(["severity", "area"]).head(limit).reset_index(drop=True)
