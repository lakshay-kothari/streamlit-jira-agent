"""Material Symbols icon shortcodes for use in Streamlit markdown/labels/icon params.

Streamlit bundles the Material Symbols font itself, so icons render natively via
the `:material/<name>:` shortcode anywhere markdown is supported (page headers,
badges, buttons, metrics, captions) - no custom SVG and no network request needed.
"""
from __future__ import annotations

# Semantic name -> Material Symbols ligature name, used across the app.
_MATERIAL_ICON_MAP: dict[str, str] = {
    "dashboard": "space_dashboard",
    "folder": "folder_open",
    "folders": "folder_copy",
    "users": "groups",
    "user-x": "person_off",
    "bot": "smart_toy",
    "database": "database",
    "settings": "tune",
    "chevron-right": "chevron_right",
    "alert-triangle": "warning",
    "check-circle": "check_circle",
    "clock": "schedule",
    "circle-dot": "radio_button_checked",
    "trending-up": "trending_up",
    "target": "target",
    "flag": "flag",
    "layers": "stacks",
    "zap": "bolt",
    "search": "search",
    "refresh-cw": "refresh",
    "upload": "upload",
    "download": "download",
    "filter": "filter_list",
    "list": "list",
    "shield-check": "verified_user",
    "compass": "explore",
    "bar-chart": "bar_chart",
    "pie-chart": "pie_chart",
    "link": "link",
    "calendar": "calendar_today",
    "activity": "monitoring",
    "sparkles": "auto_awesome",
    "building": "domain",
    "info": "info",
    "circle": "circle",
    "send": "send",
    # Navigation / drill-down
    "back": "arrow_back",
    "forward": "arrow_forward",
    "chat": "forum",
    "close": "close",
    # Activity categories (Overview page)
    "strategic": "rocket_launch",
    "demands": "inbox",
    "programs": "folder_open",
    "agents": "smart_toy",
    "workload": "groups",
    "soon": "hourglass_top",
    # Portfolio model + metric semantics
    "flow": "trending_up",
    "health": "monitoring",
    "money": "payments",
    "budget": "account_balance_wallet",
    "warning": "warning",
    "blocked": "block",
    "coverage": "fact_check",
    "attention": "priority_high",
    "funnel": "filter_alt",
    "timeline": "timeline",
    "sponsor": "supervisor_account",
    "apps": "apps",
    "explore": "explore",
    "stacks": "stacks",
    "schedule": "schedule",
    "bar_chart": "bar_chart",
    "trend": "trending_up",
    "cancel": "remove_circle",
    "approval": "approval",
    "idea": "lightbulb",
    "source": "dataset",
}


def icon(name: str) -> str:
    """Return a `:material/<name>:` shortcode for a semantic icon name.

    Unknown names pass through as literal Material Symbols names, so callers
    can also use an exact Material Symbols name directly.
    """
    resolved = _MATERIAL_ICON_MAP.get(name, name.replace("-", "_"))
    return f":material/{resolved}:"

