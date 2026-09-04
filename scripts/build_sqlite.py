"""Rebuild the local SQLite dataset from data/raw/ (and data/raw/generated/).

Usage:  python scripts/build_sqlite.py

Also appends today's metric snapshot, which is what makes week-over-week deltas
possible - without it every trend arrow in the UI would be invented.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.adapters.registry import UNATTACHED  # noqa: E402
from common.etl import build_and_save_sqlite  # noqa: E402

if __name__ == "__main__":
    result = build_and_save_sqlite()

    programs = result.programs
    strategic = int(programs["is_strategic"].sum()) if len(programs) else 0
    work = result.work_items
    attached = int((work["program_id"] != UNATTACHED).sum()) if len(work) else 0

    print(f"programs:      {len(programs)} ({strategic} strategic, "
          f"{len(programs) - strategic} standard)")
    print(f"work_items:    {len(work)} ({attached} attached to a program, "
          f"{len(work) - attached} unattached)")
    print(f"issues:        {len(result.issues)}")
    print(f"board_items:   {len(result.board_items)}")
    print(f"demands:       {len(result.demands)}")
    print(f"generic_items: {len(result.generic_items)}")
    print(f"sources:       {len(result.programs_meta)}")

    errors = result.programs_meta[result.programs_meta["kind"] == "error"]
    for _, row in errors.iterrows():
        print(f"  ! {row['source_file']}: {row['detail']}")
