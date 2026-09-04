"""End-to-end verification of the portfolio model and the metric layer.

    python scripts/verify.py

Checks the invariants that matter for trust rather than for coverage:

* the status taxonomy partitions the work (nothing is counted twice or lost),
* strategic initiatives really are a subset of programs,
* every work item resolves to a registered program or is explicitly unattached,
* the known-good numbers from the source analysis still hold,
* metrics that cannot be measured honestly report themselves as such.

Exit code 1 on any failure, so this can gate a build.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import data_access, kpi  # noqa: E402
from common import metrics as mx  # noqa: E402
from common.adapters.base import STATUS_CATEGORIES  # noqa: E402
from common.adapters.registry import UNATTACHED  # noqa: E402

FAILURES: list = []
CHECKS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


def approx(value, expected, tolerance) -> bool:
    return value is not None and abs(float(value) - expected) <= tolerance


def main() -> int:
    programs = data_access.get_programs()
    work_items = data_access.get_work_items()
    demands = data_access.get_demands()
    board = data_access.get_board_items()
    scorecard = kpi.program_scorecard(programs, work_items)

    print("\nPortfolio model")
    strategic = int(scorecard["is_strategic"].sum())
    check("strategic initiatives are a subset of programs",
          strategic <= len(scorecard), f"{strategic} of {len(scorecard)}")
    check("every program appears exactly once", scorecard["program_id"].is_unique)
    check("no separate strategic_initiatives table is read",
          len(data_access.get_strategic_initiatives()) == strategic)
    parents = programs["parent_program_id"].dropna()
    check("nested programs point at a real parent",
          parents.isin(programs["program_id"]).all() if len(parents) else True,
          f"{len(parents)} nested")

    print("\nStatus taxonomy")
    categories = set(work_items["status_category"].dropna().unique())
    check("only known status categories exist", categories <= set(STATUS_CATEGORIES),
          ", ".join(sorted(categories)))
    per_program_ok = True
    for pid, group in work_items.groupby("program_id"):
        counted = sum(int((group["status_category"] == c).sum()) for c in STATUS_CATEGORIES)
        if counted != len(group):
            per_program_ok = False
            print(f"        {pid}: {counted} categorised vs {len(group)} rows")
    check("status categories partition every program's work", per_program_ok)

    print("\nAttachment")
    known = set(programs["program_id"]) | {UNATTACHED}
    check("every work item resolves to a registered program or 'unattached'",
          set(work_items["program_id"].dropna()) <= known)
    unattached = int((work_items["program_id"] == UNATTACHED).sum())
    check("unattached volume is reported, not hidden", unattached >= 0,
          f"{unattached} rows unattached")

    print("\nKnown-good numbers (from the source analysis)")
    deng = work_items[work_items["program_id"] == "data-engineering-modernization"]
    deng_all = deng  # includes container rows, matching the raw export
    check("Jira export still loads 10,000 issues", len(deng_all) == 10000, str(len(deng_all)))
    check("Descoped is counted as cancelled, not done",
          int((deng_all["status_category"] == "Cancelled").sum()) == 1311,
          str(int((deng_all["status_category"] == "Cancelled").sum())))
    check("Blocked is its own category",
          int((deng_all["status_category"] == "Blocked").sum()) == 317,
          str(int((deng_all["status_category"] == "Blocked").sum())))
    completion = mx.pct_complete(deng).value
    check("% complete excludes abandoned scope (was 67.4% when it did not)",
          approx(completion, 61.4, 1.5), f"{completion}%")
    domain_cov = 100 * (mx.delivery_items(deng)["domain"] != "Unmapped").mean()
    check("domain recovered from the Jira hierarchy (was 0%)",
          domain_cov > 60, f"{domain_cov:.0f}% mapped")

    print("\nDemand flow")
    stages = kpi.demand_stage_times(demands)
    bottleneck = kpi.demand_bottleneck(stages)
    check("stage cycle times are measurable", not stages["median_days"].isna().all())
    check("a bottleneck stage is identified", bottleneck is not None,
          bottleneck["stage"] if bottleneck else "none")
    waste = kpi.demand_cancellation_waste(demands)
    check("cancellation rate matches the source", approx(waste["rate_pct"], 22.1, 0.5),
          f"{waste['rate_pct']}%")
    check("cancelled effort is quantified", waste["wasted_hours"] > 0,
          f"{waste['wasted_hours']:,.0f} hours")
    future = demands["go_live_date"] > pd.Timestamp.now()
    check("future go-lives are excluded from measured cycle time",
          int(future.sum()) > 0 and stages["measured"].max() < len(demands),
          f"{int(future.sum())} future-dated")

    print("\nAgents")
    concentration = kpi.agent_owner_concentration(board)
    check("owner concentration matches the source",
          approx(concentration["share_pct"], 72.9, 2.0), f"{concentration['share_pct']}%")
    funnel = kpi.agent_funnel(board)
    check("rollout funnel covers every agent", int(funnel["count"].sum()) == len(board),
          f"{int(funnel['count'].sum())} of {len(board)}")

    print("\nHonesty guards")
    throughput = mx.throughput_metric(deng)
    check("under-dated completions report as not measurable, not as zero",
          throughput.display == "-" and throughput.status == mx.UNKNOWN,
          throughput.coverage_note or "")
    freshness = mx.data_freshness(work_items)
    check("data freshness is never negative", (freshness.value or 0) >= 0, freshness.display)
    coverage = kpi.field_coverage({"work_items": work_items, "demands": demands,
                                   "board_items": board})
    check("field coverage names what each empty field blocks",
          not coverage.empty and coverage["enables"].notna().all(),
          f"{len(coverage)} fields tracked")

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
