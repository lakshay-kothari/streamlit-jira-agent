"""Small shared helpers: safe number formatting."""
from __future__ import annotations


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_pct(n, decimals: int = 0) -> str:
    try:
        return f"{float(n):.{decimals}f}%"
    except (TypeError, ValueError):
        return "0%"
