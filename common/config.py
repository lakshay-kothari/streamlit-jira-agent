"""Static app configuration: paths, Snowflake account facts, branding constants."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
# Synthetic demo sources live in their own subfolder so they are never confused
# with (or accidentally overwritten by) the real exports sitting in RAW_DIR.
# Delete the folder and rebuild to return the app to real-data-only.
GENERATED_DIR = RAW_DIR / "generated"
SQLITE_PATH = DATA_DIR / "pm_agent.db"
ASSETS_DIR = ROOT_DIR / "assets"

APP_TITLE = "Program Command Center"
APP_SUBTITLE = "AI-Assisted Program & Demand Tracking"

# Snowflake + Jira, combined - the AI Agent's persona name shown in the UI.
AGENT_NAME = "SnowJira"
AGENT_TAGLINE = "Your AI Agent for programs & demands"

# Snowflake account facts (from the org's account admin) - display-only unless
# secrets.toml / SiS session supplies live credentials.
SNOWFLAKE_ACCOUNT_IDENTIFIER = "MDTPLC-AWSUSE1P1"
SNOWFLAKE_DATA_SHARING_IDENTIFIER = "MDTPLC.AWSUSE1P1"
SNOWFLAKE_ORG_NAME = "MDTPLC"
SNOWFLAKE_ACCOUNT_NAME = "AWSUSE1P1"
SNOWFLAKE_ACCOUNT_URL = "MDTPLC-AWSUSE1P1.snowflakecomputing.com"
SNOWFLAKE_LOGIN_NAME = "MS68@MEDTRONIC.COM"
SNOWFLAKE_ROLE = "PUBLIC"
SNOWFLAKE_ACCOUNT_LOCATOR = "MDTPLCPROD"
SNOWFLAKE_CLOUD_PLATFORM = "AWS"
SNOWFLAKE_EDITION = "Business Critical"

# Database/schema the app looks for once tables are provisioned in Snowflake
# (see sql/snowflake_setup.sql). Local dev falls back to SQLite automatically.
SNOWFLAKE_DATABASE = "PM_AGENT"
SNOWFLAKE_SCHEMA = "PUBLIC"

# Cortex COMPLETE models to offer in the UI. Availability depends on region /
# cross-region inference settings on the account.
CORTEX_MODELS = [
    "claude-4-sonnet",
    "llama3.1-70b",
    "mistral-large2",
    "snowflake-arctic",
]
DEFAULT_CORTEX_MODEL = CORTEX_MODELS[0]

TABLE_PROGRAMS = "programs"
TABLE_WORK_ITEMS = "work_items"
TABLE_SNAPSHOTS = "snapshots"
TABLE_ISSUES = "issues"
TABLE_BOARD_ITEMS = "board_items"
TABLE_DEMANDS = "demands"
TABLE_STRATEGIC_INITIATIVES = "strategic_initiatives"
TABLE_GENERIC_ITEMS = "generic_items"
TABLE_PROGRAMS_META = "programs_meta"

# ---------------------------------------------------------------------------
# The 4 top-level activity types leaders/managers track in this app. This is
# the single source of truth for the Overview page's cards *and* for wiring
# up st.Page/st.navigation in streamlit_app.py - add an entry here (plus its
# app_pages/<key>.py) to extend the app; nothing else needs to change for it
# to show up consistently in nav and on the Overview page.
# ---------------------------------------------------------------------------
ACTIVITIES = [
    {
        "key": "programs",
        "label": "Programs",
        "icon": "folder_open",
        "tagline": "Every delivery program in the portfolio - strategic ones included.",
        "path": "app_pages/programs.py",
        "live": True,
    },
    {
        "key": "agents",
        "label": "Agents",
        "icon": "smart_toy",
        "tagline": "AI/BI board - every agent being built, and its rollout status.",
        "path": "app_pages/agents.py",
        "live": True,
    },
    {
        "key": "strategic_initiatives",
        "label": "Strategic initiatives",
        "icon": "rocket_launch",
        "tagline": "The strategic subset of programs, seen at sponsor level.",
        "path": "app_pages/strategic_initiatives.py",
        "live": True,
    },
    {
        "key": "demands",
        "label": "Demands",
        "icon": "inbox",
        "tagline": "Incoming business asks, from intake through triage.",
        "path": "app_pages/demands.py",
        "live": True,
    },
]


# ---------------------------------------------------------------------------
# Targets & thresholds. A metric without a baseline is just a number - these
# are what let the UI render a judgement ("18d vs a 10d target") instead of a
# bare value. Tune them here; no page or KPI function hard-codes a threshold.
# ---------------------------------------------------------------------------
METRIC_TARGETS = {
    # Demand intake pipeline SLAs, in calendar days per stage.
    "demand_triage_days": 10,          # created -> estimation approved
    "demand_resourcing_days": 15,      # estimation approved -> development start
    "demand_delivery_days": 90,        # development start -> go live
    "demand_end_to_end_days": 120,     # created -> go live
    "demand_cancellation_rate_pct": 10.0,
    "demand_aging_days": 120,          # an open demand older than this is "aging"

    # Delivery work items.
    "work_item_stale_days": 14,        # no update in this long while not done
    "work_item_blocked_days": 7,       # blocked longer than this needs escalation
    "descope_rate_pct": 5.0,           # share of scope abandoned rather than delivered

    # Program & initiative health. Schedule variance = %complete - %time elapsed.
    "schedule_variance_at_risk_pct": -10.0,   # below this -> At risk
    "schedule_variance_off_track_pct": -25.0,  # below this -> Off track
    "burn_efficiency_at_risk": 1.2,    # $ burned per unit of scope delivered

    # Agents / AI-BI board.
    "agent_stalled_days": 60,          # no status movement in this long
    "agent_owner_concentration_pct": 40.0,  # top-2 owners holding more than this is a bus-factor risk

    # Flow. Arrivals divided by completions over the trailing window.
    "net_flow_ratio": 1.0,             # above 1.0 the backlog is growing
    "flow_window_days": 90,

    # Below this share of populated rows, a metric is reported as unreliable
    # rather than silently averaged over a biased sample.
    "min_coverage_pct": 60.0,
}

# Coverage bands used by the Data coverage page and the KPI card's coverage note.
COVERAGE_BANDS = [(90.0, "Good"), (60.0, "Partial"), (0.0, "Unreliable")]
