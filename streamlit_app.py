"""Program Command Center - main Streamlit entry point.

Run locally:  streamlit run streamlit_app.py
Deploy:       see sql/snowflake_setup.sql + README.md for Streamlit-in-Snowflake.

Routing only: st.navigation defines the available pages (see app_pages/) and
this file owns the few things that must run before every page - page config,
global theme/branding, and the floating SnowJira AI launcher. Every page is
a direct script; see DESIGN_SYSTEM.md for the conventions they all follow.
"""
from __future__ import annotations

import streamlit as st

from common import chat, data_access, theme
from common.config import APP_TITLE

st.set_page_config(page_title=APP_TITLE, page_icon=":material/insights:", layout="wide",
                    initial_sidebar_state="expanded")
theme.inject_global_css()

logo = theme.logo_path()
if logo:
    st.logo(logo, size="large", icon_image=theme.logo_icon_path() or logo)

pages = st.navigation(
    {
        "": [
            st.Page("app_pages/overview.py", title="Overview", url_path="",
                     icon=":material/space_dashboard:", default=True),
        ],
        "Explore": [
            st.Page("app_pages/programs.py", title="Programs", url_path="programs",
                     icon=":material/folder_open:"),
            st.Page("app_pages/agents.py", title="Agents", url_path="agents",
                     icon=":material/smart_toy:"),
            st.Page("app_pages/strategic_initiatives.py", title="Strategic initiatives",
                     url_path="strategic-initiatives", icon=":material/rocket_launch:"),
            st.Page("app_pages/demands.py", title="Demands", url_path="demands",
                     icon=":material/inbox:"),
        ],
        "Insights": [
            st.Page("app_pages/attention.py", title="Needs attention",
                     url_path="needs-attention", icon=":material/priority_high:"),
            st.Page("app_pages/team_workload.py", title="Team & workload",
                     url_path="team-workload", icon=":material/groups:"),
            st.Page("app_pages/data_coverage.py", title="Data coverage",
                     url_path="data-coverage", icon=":material/fact_check:"),
        ],
    },
)

# Loaded once (cached) so every page and the chat panel share the same data
# without re-querying Snowflake/SQLite per page switch.
programs_all = data_access.get_programs()
work_items_all = data_access.get_work_items()
board_all = data_access.get_board_items()
demands_all = data_access.get_demands()

chat.render_floating_button(programs_all, work_items_all, board_all, demands_all)

pages.run()

