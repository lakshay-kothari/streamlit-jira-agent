"""
Theming: colors, fonts, radii, and borders all come from `.streamlit/config.toml`
(native Streamlit theming - see DESIGN_SYSTEM.md and the theme reference in the
developing-with-streamlit skill). This module injects a small, deliberate set of
CSS rules for the handful of enterprise-dashboard details native theming can't
express (soft card shadows, metric "chip" fills, uppercase nav section labels,
the solid-pill selected nav state) - see the "Theme tokens" section of
DESIGN_SYSTEM.md for the full list.
"""
from __future__ import annotations

import streamlit as st

from common.config import ASSETS_DIR

# Plotly isn't theme-aware, so charts.py needs explicit hex values. Kept in sync
# with [theme] in .streamlit/config.toml.
CHART_COLORWAY = ["#2432FF", "#0A1B3D", "#16865B", "#D98A15", "#C9434F",
                   "#6557D8", "#7CA0E8", "#9E9FF0", "#3FA5C4", "#B7BDD6"]
CHART_FONT = "Open Sans, Inter, Segoe UI, sans-serif"
# Blocked and Cancelled are first-class states in the taxonomy, so they need
# their own colors: red for blocked (it needs an intervention) and a muted grey
# for cancelled (it is out of scope, not a warning).
STATUS_COLORS = {"To Do": "#98A2B3", "In Progress": "#D98A15", "Blocked": "#C9434F",
                 "Done": "#16865B", "Cancelled": "#CDD2DE", "Unknown": "#E4E7EF"}
HEALTH_COLORS = {"On Track": "#16865B", "At Risk": "#D98A15", "Off Track": "#C9434F",
                 "Delayed": "#C9434F", "Unknown": "#98A2B3"}
#: Rollout stages for the AI/BI board funnel, cold (idea) to warm (live).
FUNNEL_COLORS = {"Idea": "#CDD2DE", "Scoping": "#98A2B3", "WIP": "#D98A15",
                 "UAT": "#6557D8", "Live": "#16865B", "On Hold": "#C9434F"}
#: Metric status colors, matching the badge colors in common/components.py.
METRIC_STATUS_COLORS = {"good": "#16865B", "watch": "#D98A15", "bad": "#C9434F",
                        "unknown": "#98A2B3"}

# Prefer a pre-cropped, transparent-background wordmark (see scripts/ - cropped
# tight to the "Medtronic" glyphs so st.logo renders it large and crisp instead
# of shrunk inside the original asset's huge padding) over the original raw jpg.
_LOGO_PREFERRED = ("medtronic_logo.png", "medtronic_logo.svg", "medtronic_logo.jpg", "medtronic_wordmark.jpg")

# Reusable prefix for `st.container(key=f"{METRIC_CHIP_KEY_PREFIX}<unique>")` -
# see `common.components.metric_chip_row`. CSS below targets every container
# whose key starts with this prefix via a `[class*=...]` substring match, since
# each chip row needs its own unique Streamlit key but they all share one style.
METRIC_CHIP_KEY_PREFIX = "chip_row__"

# A KPI card shows its status as a small colored bar inside the card rather than
# as a badge, which changed the card's proportions. The status is encoded in the
# Streamlit container key (e.g. "metriccard__good__pct_complete") so the CSS can
# color that bar without any inline HTML. See `metric_card` in
# common/components.py. Only KPI cards carry an indicator.
METRIC_CARD_KEY_PREFIX = "metriccard__"
#: Every bordered card shares one look and none of them carries a status
#: indicator. Two flavours, distinguished only so a tile's tagline can read
#: larger than a chart panel's explanatory caption.
PANEL_KEY_PREFIX = "pcccard_panel__"   # a chart, a table, a list row
TILE_KEY_PREFIX = "pcccard_tile__"     # an activity / program / initiative tile

# common.components.card_grid's container key. A grid replaces a fixed
# st.columns(N) for any row of repeating tiles (programs, initiatives,
# activities): CSS Grid's auto-fit/minmax (below) reflows the column count by
# available width - 4+ on a wide screen, 1 on a narrow one - so a tile's
# content (a metric_chip_row's nowrap labels, in particular) never gets
# squeezed into overflow the way a fixed 3-column layout could.
CARD_GRID_KEY_PREFIX = "card_grid__"

# common.chat.render_floating_button's container key - the only fixed-position
# element in the app, so it gets one dedicated, narrowly-scoped CSS block below
# rather than a new stylesheet.
FLOATING_AGENT_KEY = "snowjira_fab"


def logo_path() -> str | None:
    """Path to the brand logo file dropped into assets/, for `st.logo()`'s
    main `image` (shown in the expanded sidebar, which has a dark navy
    background - safe for a transparent-background wordmark).
    Returns None if no image is present, so the caller can skip st.logo entirely."""
    if not ASSETS_DIR.exists():
        return None
    candidates = sorted(ASSETS_DIR.glob("*"), key=lambda p: p.name.lower() not in _LOGO_PREFERRED)
    for p in candidates:
        if p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg"):
            return str(p)
    return None


def logo_icon_path() -> str | None:
    """Path to the compact icon-only mark for `st.logo()`'s `icon_image`,
    shown in place of the full wordmark once the sidebar is collapsed (native
    `st.logo` behavior - it swaps automatically, no extra wiring needed) and
    doubling as the collapsed rail's first icon (see `inject_global_css`)."""
    candidate = ASSETS_DIR / "medtronic_icon.png"
    return str(candidate) if candidate.exists() else None


def inject_global_css() -> None:
    # The trailing <svg><filter id="carbon-icon-bold">...</filter></svg> below
    # (0x0, visually invisible) defines a feMorphology "dilate" filter that
    # the Carbon Design System icons in this stylesheet reference via
    # `filter: url(#carbon-icon-bold)` - Carbon's icons are flat path shapes
    # with no separate weight/thickness variant, so a touch of extra
    # boldness is done by growing the icon's painted pixels slightly rather
    # than scaling the whole glyph up. It must come AFTER </style>: Streamlit
    # renders this whole string as one Markdown block, and <style>...</style>
    # is the one HTML tag Markdown always treats as raw/opaque regardless of
    # blank lines inside it - putting arbitrary HTML like <svg> *before* it
    # made the parser stop treating the rest of the string (including the
    # stylesheet) as raw HTML at the first blank line inside the CSS, which
    # rendered the entire stylesheet as visible page text instead of CSS.
    st.markdown(
        """
        <style>
        #MainMenu, footer {visibility: hidden;}
        /* Streamlit's top app header bar (Deploy button, etc.) - not part of
           the reference design. */
        [data-testid="stHeader"] {
            display: none !important;
        }
        /* The sidebar's own collapse arrow (visible while expanded) is
           otherwise hover-only. */
        [data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] * {
            opacity: 1 !important;
            visibility: visible !important;
        }
        /* The floating expand button Streamlit renders in the main header
           once collapsed is redundant now that the collapsed rail's own
           logo doubles as the expand control on hover (see the
           collapsed-sidebar block below). */
        [data-testid="stExpandSidebarButton"] {
            display: none !important;
        }

        /* Tighter margins around the main page content than Streamlit's
           fairly wide default - no top padding (the app header bar above it
           is hidden, so there's no header height to leave room for) and a
           left/right gutter that keeps the title clear of the sidebar. */
        [data-testid="stMainBlockContainer"] {
            padding-top: 0;
            padding-left: 40px;
            padding-right: 40px;
        }
        /* Page title: Medtronic dark navy, matching the sidebar background.
           Streamlit's own heading padding-top (anchor-link spacing) is
           dropped to 0 - the page header is the first thing on every page,
           so there's nothing above it to space away from. */
        [data-testid="stMainBlockContainer"] h1 {
            color: #08142A;
            padding-top: 0;
        }

        /* --- Enterprise-dashboard polish native theming can't express --- */

        /* Extremely light card shadow on every bordered card/metric (KPI cards,
           st.container(border=True) panels, charts, dataframes) - config.toml
           has no shadow token. */
        [data-testid="stMetric"], [data-testid="stVerticalBlock"][class*="st-key-pcccard_"],
        div[data-testid="stDataFrame"], div[data-testid="stExpander"] {
            box-shadow: 0 2px 8px rgba(15, 30, 60, 0.04);
        }
        /* st.error/st.warning/st.info/st.success alert boxes: same shadow as
           every other card, plus a thin border colored to match the alert's
           own severity (the same red/orange/green/blue used for the metric
           card indicator rail). Both go on stAlertContainer, not the outer
           stAlert wrapper - the wrapper has no border-radius of its own
           (0px), so a shadow/border applied there rendered as a square
           behind the container's actually-rounded (16px) colored box. */
        [data-testid="stAlertContainer"] {
            box-shadow: 0 2px 8px rgba(15, 30, 60, 0.04);
            border: 1px solid #DCE2ED;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
            border-color: #C9434F;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {
            border-color: #D98A15;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
            border-color: #16865B;
        }
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {
            border-color: #2432FF;
        }
        /* Unified card look for every bordered card - activity and program
           tiles, chart panels, attention rows. Streamlit's own bordered
           container is a transparent 13px-padded box, which left cards
           reading as part of the page rather than as objects on it. */
        [data-testid="stVerticalBlock"][class*="st-key-pcccard_"] {
            padding: 24px;
            border-radius: 20px;
            background-color: #FFFFFF;
        }
        [data-testid="stMainBlockContainer"] h4 {
            font-size: 24px;
        }
        /* Tile tagline (activity_card's caption under the title) reads bigger
           and less muted than a normal caption. Scoped to the status tiles -
           a chart panel's explanatory caption stays at caption size. */
        [data-testid="stVerticalBlock"][class*="st-key-pcccard_tile__"] [data-testid="stCaptionContainer"] p {
            font-size: 15px;
            color: #5B657A;
        }

        /* KPI cards (common.components.kpi_metric): white fill (the native
           metric border has no background of its own), uniform/slightly
           bigger padding on every side, and a title in the card's own muted
           slate color - no per-title icon anymore (removed at the Python
           level; see components.py). The label row is forced to flex so the
           native help-tooltip icon pins to the card's top-right corner,
           parallel to the title, instead of sitting right next to the title
           text. The KPI row itself (`key="kpi_row"` in every page) is forced
           to never wrap - Streamlit's default content-based flex-basis let
           the last card drop to its own full-width row once the 4-5 cards'
           natural content width slightly exceeded the row's width. */
        [data-testid="stHorizontalBlock"][class*="st-key-kpi_row"] {
            flex-wrap: nowrap;
        }
        [data-testid="stHorizontalBlock"][class*="st-key-kpi_row"] > [data-testid="stElementContainer"],
        [data-testid="stHorizontalBlock"][class*="st-key-kpi_row"] > [data-testid="stVerticalBlock"],
        [data-testid="stHorizontalBlock"][class*="st-key-kpi_row"] > [data-testid="stVerticalBlockBorderWrapper"] {
            flex: 1 1 0;
            min-width: 0;
        }
        /* Every card row (KPI row, activity cards, program cards, chart
           panels, ...) stretches all its cards to match the tallest one -
           combined with the height:100% chain below, a card that grows from
           wrapped text makes its whole row grow with it instead of leaving
           its neighbors short. Streamlit's own default is top-aligned. */
        [data-testid="stHorizontalBlock"] {
            align-items: stretch;
        }
        [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
            height: 100%;
        }
        [data-testid="stColumn"] [data-testid="stLayoutWrapper"] {
            height: 100%;
        }
        [data-testid="stColumn"] [data-testid="stVerticalBlock"][class*="st-key-pcccard_"] {
            height: 100%;
            box-sizing: border-box;
        }

        /* Responsive card grid (common.components.card_grid): a fixed
           st.columns(3) never reflows - on a narrower screen every card just
           gets thinner, squeezing metric_chip_row's nowrap labels into
           overflow. CSS Grid's auto-fit/minmax instead fits as many
           `minmax()`-wide columns as the container has room for and wraps
           the rest - 4+ tiles wide on a big screen, 1 on a small one - with
           every tile in a row still stretched to equal height/width the way
           the stColumn rules above do it for a fixed grid. */
        [data-testid="stVerticalBlock"][class*="st-key-card_grid__"] {
            display: grid !important;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            align-items: stretch;
        }
        [class*="st-key-card_grid__"] > [data-testid="stElementContainer"],
        [class*="st-key-card_grid__"] > [data-testid="stVerticalBlock"] {
            height: 100%;
        }
        [class*="st-key-card_grid__"] [data-testid="stLayoutWrapper"] {
            height: 100%;
        }
        [class*="st-key-card_grid__"] [data-testid="stVerticalBlock"][class*="st-key-pcccard_"] {
            height: 100%;
            box-sizing: border-box;
        }
        /* Overview's 4 activity cards specifically: capped at 2 columns
           normally, 3 only once the screen is wide enough that a 3-across
           row still leaves each metric_chip_row's labels room to sit on one
           line - the generic grid's 300px minimum was letting 3 columns
           form before there was really space for 3, forcing those labels to
           wrap. A wider per-card minimum (440px) pushes that 3rd column out
           to a wider breakpoint, and a max-width on the grid itself stops
           auto-fit from ever reaching a 4th column on very wide screens. */
        /* Same specificity as the generic rule above (both a [data-testid]
           + a [class*=...] attribute selector) so source order - this rule
           comes later - is what decides the tie, rather than the generic
           rule winning outright on selector count and this override
           silently never applying. */
        [data-testid="stVerticalBlock"][class*="st-key-card_grid__activities"] {
            grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
            max-width: 1400px;
        }
        [data-testid="stMetric"] {
            background-color: #FFFFFF;
        }
        [data-testid="stMetric"] > div:first-child {
            padding: 20px;
        }
        [data-testid="stMetricLabel"] {
            display: flex !important;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        [data-testid="stMetricLabel"] p {
            font-size: 11px;
            font-weight: 700;
            color: #5B657A;
            white-space: normal;
            overflow-wrap: break-word;
        }
        [data-testid="stMetricValue"] p {
            font-weight: 700;
            color: #08142A;
            white-space: normal;
            overflow-wrap: break-word;
        }
        /* Wrap instead of clip/ellipsis when a label or value doesn't fit -
           the card grows (see the equal-height-row rules below) instead of
           truncating text. */
        [data-testid="stMetric"] {
            overflow: visible;
        }
        [data-testid="stMetricDeltaDescription"] {
            color: #556485;
            height: auto;
            overflow: visible;
            white-space: normal;
        }
        [data-testid="stMetricDeltaDescription"] div {
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: normal !important;
            height: auto !important;
        }
        [data-testid="stMetricDeltaDescription"] p {
            white-space: normal !important;
            overflow-wrap: break-word;
        }
        /* Help tooltip: Streamlit's own circle-question-mark glyph is hidden
           and replaced with the Carbon Design System "Information" icon
           (https://carbondesignsystem.com/elements/icons/library/), painted
           via CSS mask so it inherits the title's own muted slate color
           instead of needing the SVG's fill hand-edited. A dedicated,
           stronger dilate (`carbon-icon-bold-strong`, well past the subtle
           one used elsewhere) plus a darker fill than the title's own
           color is what actually reads as "thicker" at this icon's small
           size - the lighter fill was legible but visually weak next to
           the bold title text beside it. */
        [data-testid="stTooltipIcon"] button {
            color: #33415C;
            position: relative;
        }
        [data-testid="stTooltipIcon"] svg {
            visibility: hidden;
        }
        [data-testid="stTooltipIcon"] button::after {
            content: "";
            position: absolute;
            inset: 0;
            margin: auto;
            width: 12px;
            height: 12px;
            background-color: #33415C;
            -webkit-mask-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PHBhdGggZD0iTTguNSAxMSA4LjUgNi41IDYuNSA2LjUgNi41IDcuNSA3LjUgNy41IDcuNSAxMSA2IDExIDYgMTIgMTAgMTIgMTAgMTF6Ii8+PHBhdGggZD0iTTgsMy41Yy0wLjQsMC0wLjgsMC4zLTAuOCwwLjhTNy42LDUsOCw1YzAuNCwwLDAuOC0wLjMsMC44LTAuOFM4LjQsMy41LDgsMy41eiIvPjxwYXRoIGQ9Ik04LDE1Yy0zLjksMC03LTMuMS03LTdzMy4xLTcsNy03czcsMy4xLDcsN1MxMS45LDE1LDgsMTV6IE04LDJDNC43LDIsMiw0LjcsMiw4czIuNyw2LDYsNnM2LTIuNyw2LTZTMTEuMywyLDgsMnoiLz48L3N2Zz4=");
            mask-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNiAxNiI+PHBhdGggZD0iTTguNSAxMSA4LjUgNi41IDYuNSA2LjUgNi41IDcuNSA3LjUgNy41IDcuNSAxMSA2IDExIDYgMTIgMTAgMTIgMTAgMTF6Ii8+PHBhdGggZD0iTTgsMy41Yy0wLjQsMC0wLjgsMC4zLTAuOCwwLjhTNy42LDUsOCw1YzAuNCwwLDAuOC0wLjMsMC44LTAuOFM4LjQsMy41LDgsMy41eiIvPjxwYXRoIGQ9Ik04LDE1Yy0zLjksMC03LTMuMS03LTdzMy4xLTcsNy03czcsMy4xLDcsN1MxMS45LDE1LDgsMTV6IE04LDJDNC43LDIsMiw0LjcsMiw4czIuNyw2LDYsNnM2LTIuNyw2LTZTMTEuMywyLDgsMnoiLz48L3N2Zz4=");
            -webkit-mask-repeat: no-repeat;
            mask-repeat: no-repeat;
            -webkit-mask-size: contain;
            mask-size: contain;
            -webkit-mask-position: center;
            mask-position: center;
            filter: url(#carbon-icon-bold-strong);
        }

        /* Metric "chip" style used for the compact stat row inside activity/
           program cards (see common.components.metric_chip_row): a light gray
           fill instead of a bordered card, since these are sub-stats nested
           inside an already-bordered parent card. Higher specificity than the
           KPI-card rules above, so chips keep their own compact sizing/fill
           instead of inheriting the bigger white-card padding/background. */
        [class*="chip_row__"] {
            flex-wrap: nowrap !important;
        }
        [class*="chip_row__"] > [data-testid="stElementContainer"] {
            flex: 1 1 0;
            min-width: 0;
        }
        [class*="chip_row__"] [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #EEF0F6;
            border-radius: 14px;
            padding: 16px 12px;
            box-shadow: none;
        }
        [class*="chip_row__"] [data-testid="stMetric"] > div:first-child {
            padding: 0;
        }
        /* Chip labels/values are short (1-2 words), so they read fine on one
           line at a comfortable card width - but forcing `nowrap` let a
           label overflow past its chip (and the card's own edge) once a
           narrower card (see the responsive card_grid) left less than a
           1-2 word label's width to work with. `normal` wraps at the space
           between words when it must - the labels here are never a single
           long word, so this can't hyphen-break mid-word the way the
           general wrap-long-text rule (above) would risk. */
        [class*="chip_row__"] [data-testid="stMetricLabel"] p,
        [class*="chip_row__"] [data-testid="stMetricValue"] p {
            white-space: normal;
            overflow-wrap: break-word;
            overflow: visible;
            text-overflow: clip;
        }
        [class*="chip_row__"] [data-testid="stMetricLabel"] div,
        [class*="chip_row__"] [data-testid="stMetricValue"] div {
            overflow: visible !important;
            text-overflow: clip !important;
        }
        [class*="chip_row__"] [data-testid="stMetricLabel"] p {
            font-size: 13px;
        }

        /* Sidebar: slightly smaller logo and tighter left/right padding than
           Streamlit's default so nav content sits closer to the edges. */
        [data-testid="stSidebarHeader"] {
            padding-top: max(50px, -10px + 1.25rem);
        }
        [data-testid="stSidebarLogo"] {
            height: 34px;
        }
        [data-testid="stSidebarContent"] {
            padding-left: 15px;
            padding-right: 15px;
        }
        /* Extra breathing room between the logo and the first nav item. */
        [data-testid="stSidebarNav"] {
            margin-top: 28px;
        }

        /* Uppercase nav section labels ("EXPLORE", "INSIGHTS") with letter-spacing.
           Color+opacity live on the header itself (not just the <p>) so the
           expand/collapse arrow next to it inherits the exact same muted
           color/weight instead of rendering darker/bolder than the label.
           The left padding matches the nav links' own padding below so the
           label text lines up with their icons, not the sidebar edge. */
        [data-testid="stNavSectionHeader"] {
            padding-left: 14px;
            color: #889AC2;
            opacity: 0.6;
        }
        [data-testid="stNavSectionHeader"] p {
            font-size: 9px;
            font-weight: 500;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        [data-testid="stNavSectionHeader"] [data-testid="stIconMaterial"] {
            font-weight: 500;
        }

        /* Sidebar nav rows: give every item (selected or not) the same
           comfortable pill height/padding/radius - Streamlit's default has
           none - and a muted slate-blue color at rest. The icon and label
           each carry their own explicit (native) text color, so both need
           overriding directly - setting `color` on the link itself doesn't
           cascade down to them. Label weight matches the section headers
           above (500) so items and labels read as the same thickness. */
        [data-testid="stSidebarNavLink"] {
            padding: 6px 14px;
            border-radius: 8px;
            height: 44px;
        }
        [data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"],
        [data-testid="stSidebarNavLink"] p {
            color: #889AC2;
        }
        [data-testid="stSidebarNavLink"]:not([aria-current="page"]) p {
            font-weight: 500;
        }
        /* Keep the icon's stroke weight identical in the selected and default
           states - Streamlit otherwise bolds it along with the label text. */
        [data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {
            font-weight: 400 !important;
        }

        /* Selected nav item: solid primaryColor pill with white text/icon,
           replacing Streamlit's default thin, low-contrast tinted background. */
        [data-testid="stSidebarNavLink"][aria-current="page"] {
            background-color: #2432FF !important;
        }
        [data-testid="stSidebarNavLink"][aria-current="page"],
        [data-testid="stSidebarNavLink"][aria-current="page"] * {
            color: #FFFFFF !important;
        }

        /* Collapsed sidebar: a compact icon-only rail instead of Streamlit's
           default fully-hidden state, so nav stays one click away. Only the
           nav icons (and the selected pill) fit at this width - item labels
           are hidden. The logo swaps
           to Medtronic's icon mark automatically (native `st.logo(icon_image=)`
           behavior) and becomes the rail's first icon; hovering it reveals
           the real collapse/expand toggle (`stSidebarCollapseButton`, still
           functional while collapsed - only its own icon is stale and
           always points left, so it's flipped with `scaleX(-1)`) in the same
           spot instead of a separate reserved row. Section labels become
           thin divider lines instead of disappearing, so nothing below them
           shifts vertically when collapsing (no icon to show there instead).

           Streamlit sizes stSidebarUserContent/stSidebarNav/nav links etc via
           JS (not plain CSS width), so overriding their width directly gets
           silently fought/reverted. Instead, stSidebarContent (which *does*
           reliably honor a plain CSS width) is turned into a centered flex
           column: whatever narrower width those inner elements insist on,
           they - and everything inside them (nav icons, dividers) - render
           as one horizontally-centered block within the rail. */
        /* Streamlit's own collapse mechanism is a full off-canvas slide (a
           `transform: translateX()` by the sidebar's *expanded* width) -
           without a constant override it slides a "72px-wide" rail
           completely out of view, since the translate distance is still
           calculated for the full width. Kept unconditional (not scoped to
           `[aria-expanded="false"]`) rather than toggled: toggling it made
           the override newly start matching at the exact instant
           `aria-expanded` flips, snapping any transform Streamlit had
           in flight to "none" mid-slide - a visible reset - before the
           width shrink (which *is* smoothly transitioned) finished the
           rest of the motion. Applying it constantly means there's no such
           instant for the rule to newly kick in on. */
        [data-testid="stSidebar"] {
            transform: none !important;
        }
        /* No `overflow: hidden` here (used to be set !important on this
           selector) - Streamlit's own resize-drag handle is a sibling of
           stSidebarContent, straddling the sidebar's right edge, and the
           outer section's `overflow: hidden` clipped it out of hit-testing
           entirely, so the collapsed rail couldn't be drag-expanded.
           stSidebarContent below still clips its own contents, which is
           all this rule was really needed for. */
        html body [data-testid="stSidebar"][aria-expanded="false"] {
            width: 72px !important;
            min-width: 72px !important;
            max-width: 72px !important;
        }
        /* Expanded sidebar: capped so a drag-resize can't stretch it past a
           sane width. Streamlit sets width via inline style during a drag,
           which max-width still overrides regardless of the inline value. */
        [data-testid="stSidebar"][aria-expanded="true"] {
            max-width: 420px !important;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"] {
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow: hidden;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarNavLink"] span[label] {
            display: none !important;
        }
        /* Tighter than the expanded header's spacing (which is aligned to the
           main content's title) - collapsed mode has no title to align to, so
           the rail can sit closer to the icon, matching the reference design. */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"] {
            padding-top: 50px;
            padding-bottom: 0;
            margin-bottom: 0;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarNav"] {
            margin-top: 28px;
        }
        /* Nav pill is a fixed square, centered in the rail, with the same
           left/right padding as the expanded sidebar's own nav links (14px)
           so the icon sits at the same inset from the pill's edge in both
           states. `margin: 0 auto` centers the fixed-width link within its
           wider container regardless of `justify-content` (Streamlit's own
           rule otherwise wins that one). */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarNavLinkContainer"] {
            display: flex !important;
            justify-content: center !important;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarNavLink"] {
            justify-content: center !important;
            width: 44px !important;
            height: 44px !important;
            padding: 0 14px !important;
            box-sizing: border-box !important;
            flex: none !important;
            /* Horizontal centering only. A shorthand `margin: 0 auto` also
               zeroed the link's own 1.75px vertical margin, which Streamlit
               applies in both states - so collapsed rows sat 3.5px tighter
               than expanded ones and the rail read as differently spaced.
               Setting the two axes separately keeps the vertical rhythm
               identical whichever state the sidebar is in. */
            margin-left: auto !important;
            margin-right: auto !important;
        }
        /* Logo <-> expand button swap: the real collapse/expand toggle
           (`stSidebarCollapseButton`) still works while collapsed - only its
           icon is stale (always points left) - so it's kept in place instead
           of relying on the separate floating header button, and reused as
           the hover-revealed expand control right over the logo. This means
           no dedicated row/space is reserved for it: at rest only the logo
           icon shows, and hovering the header crossfades logo -> chevron. */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"] {
            position: relative;
            justify-content: center;
            width: 100%;
        }
        /* Positioned to match the logo's own box exactly (50px header
           padding-top, then centered like the logo within the header's
           fixed 52.5px height - measured at top:29.26px, i.e. the same
           34.26px as the logo minus half of this button's own 44->34px
           size increase below, so its center stays put), rather than the
           header box's own center - which sits visibly higher than the logo
           once padding-bottom was tightened to 0 for the collapsed rail.
           Box size (44px) and padding (0 14px) intentionally match the
           selected-page pill exactly (see [aria-current="page"] above) so
           the icon sits with the same inset from its edge in both. */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            align-items: center;
            justify-content: center;
            position: absolute;
            top: 29.26px;
            left: 50%;
            transform: translateX(-50%);
            width: 44px;
            height: 44px;
            padding: 0 14px;
            box-sizing: border-box;
            margin: 0;
            border-radius: 8px;
            background-color: transparent;
            opacity: 0 !important;
            pointer-events: none;
            transition: opacity 120ms ease, background-color 120ms ease;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {
            transform: scaleX(-1);
            color: #2432FF !important;
            font-size: 14px !important;
            width: 14px !important;
            height: 14px !important;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"]:hover [data-testid="stSidebarCollapseButton"] {
            opacity: 1 !important;
            pointer-events: auto;
            background-color: #F1F4F9;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"]:hover [data-testid="stSidebarLogo"] {
            opacity: 0;
        }
        /* Section labels ("EXPLORE", "INSIGHTS"): a centered thin divider
           line in place of the text/arrow, same reserved height as before. */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stNavSectionHeader"] {
            position: relative;
            padding-left: 0;
            justify-content: center;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stNavSectionHeader"] > * {
            visibility: hidden;
        }
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stNavSectionHeader"]::after {
            content: "";
            position: absolute;
            top: 50%;
            left: 50%;
            width: 28px;
            height: 1px;
            transform: translate(-50%, -50%);
            background: rgba(136, 154, 194, 0.35);
        }
        /* Streamlit still floats a duplicate logo+expand-arrow in the main
           header when the sidebar collapses - redundant now that the logo
           stays visible (as the icon mark) inside the rail itself. */
        [data-testid="stHeaderLogo"] {
            display: none !important;
        }

        /* Buttons/nav/cards: short, restrained hover transitions instead of
           an abrupt state change. */
        .stButton > button, [data-testid="stSidebarNavLink"] {
            transition: filter 120ms ease, box-shadow 120ms ease, background-color 120ms ease;
        }
        .stButton > button:hover {
            filter: brightness(1.02);
        }
        [data-testid="stBaseButton-primary"] {
            font-weight: 700;
        }
        /* Card CTA button (activity_card/program_card "Open ..." button):
           taller, bigger text than a typical inline button, matching the
           reference design's full-width footer button. */
        [data-testid="stVerticalBlock"][class*="st-key-pcccard_"] [data-testid="stBaseButton-primary"] {
            padding: 14px 20px;
            font-size: 16px;
            border-radius: 14px;
        }

        /* st.segmented_control (Programs' "Show" scope filter, Needs
           attention's area filter): Streamlit's own unstyled default fills
           the *unselected* segments with the page background color, which
           reads as an unfinished/transparent control rather than a button.
           White + the same thin border every other input/card uses at
           rest; the selected segment gets a solid primaryColor fill (not
           Streamlit's default pale tint) to match the solid-pill selected
           state used everywhere else in the app (sidebar nav, KPI status). */
        [data-testid="stButtonGroup"] button[data-variant="segmented_control"] {
            background-color: #FFFFFF;
            border: 1px solid #DCE2ED;
            color: #0A1428;
        }
        [data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-checked="true"] {
            background-color: #2432FF;
            border-color: #2432FF;
            color: #FFFFFF;
        }

        /* st.selectbox / st.multiselect (Programs' "Sort by", Team &
           workload's "Filter by program"): both are filter controls, never
           meant to claim the full page width the way a bare Streamlit
           widget does by default - capped so each sizes to what it actually
           needs to show. The dropdown popover (rendered in a portal, not
           inside the widget's own DOM, hence the separate selector) came
           out of the box filled with the page's own background gray with a
           border of the same color - effectively invisible - rather than
           the white/thin-border look every other input in the app has;
           menu items also sat almost flush against the left edge. Both get
           a touch of left padding to match the closed control's own input
           text inset instead of crowding the edge. */
        [data-testid="stSelectbox"] {
            max-width: 260px;
        }
        /* Grows to fit its selected tags (a fixed width either wastes space
           empty or clips full) up to the widest it can be without spanning
           the page, then wraps its tags onto another line rather than
           overflowing - both are the BaseWeb control's own native behavior
           once it isn't pinned to a fixed width. */
        [data-testid="stMultiSelect"] {
            width: fit-content;
            min-width: 240px;
            max-width: 100%;
        }
        [data-testid="stMultiSelect"] [data-baseweb="select"],
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            width: auto;
            flex-wrap: wrap;
        }
        [data-testid="stSelectbox"] input[role="combobox"] {
            padding-left: 12px;
        }
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            padding-left: 8px;
        }
        /* st.selectbox's dropdown is its own react-aria popover
           (stSelectboxVirtualDropdown); st.multiselect is still on the older
           BaseWeb Select, whose popover reuses that same testid on its
           inner <ul> - but is wrapped in a [data-baseweb="popover"] div (and
           an inner div) that carry the page-gray background themselves, so
           the fix has to cover both layers or the outer one shows through
           as a gray ring around the white list. The inner <ul> then had to
           lose its own border for multiselect specifically - it and the
           popover it sits inside both drew one, reading as a double/nested
           border - while plain st.selectbox (no popover wrapper) still
           needs the border on its own dropdown, so only the nested case is
           unset. */
        [data-testid="stSelectboxVirtualDropdown"], [data-baseweb="popover"] {
            background-color: #FFFFFF !important;
            border: 1px solid #DCE2ED !important;
        }
        [data-baseweb="popover"] [data-testid="stSelectboxVirtualDropdown"] {
            border: none !important;
        }
        [data-testid="stSelectboxVirtualDropdown"] [role="option"] {
            padding-left: 12px !important;
        }
        /* st.multiselect's "Select all" pinned first row is set off from the
           real options with a divider - Streamlit draws it in the same
           translucent dark-navy used nowhere else in the app; recolored to
           the same grey every other card/input border uses. */
        [data-testid="stSelectboxVirtualDropdown"] li:first-child::after {
            background-color: #DCE2ED !important;
        }

        /* st.dataframe: white fill everywhere, including the tables that sit
           directly on the page background (a "Blocked"/"Stale"/"Overdue" tab,
           for instance) rather than inside a `panel()` card - those otherwise
           picked up the page's own light-gray background. A table already
           nested inside a white `panel()` renders identically either way, so
           this is safe to apply everywhere rather than needing to special-
           case which call sites are already inside a card. */
        [data-testid="stDataFrame"] {
            background-color: #FFFFFF;
        }

        /* ---------------------------------------------------------------
           Status rule: a colored rail down a card's left edge.

           A KPI needs to show whether it is on or off target, but a badge
           inside the card changed its proportions and made KPI cards look
           unlike every other card in the app. Instead the status is encoded
           in the container key (metric_card__<status>__<id>) and painted
           here as a wide left border - a plain CSS border already bends
           around the card's own border-radius at the top-left/bottom-left
           corners, so the rail needs no separate positioning/rounding of
           its own and can never overflow the card's curvature. The other
           three edges keep the card's normal thin border untouched.
           --------------------------------------------------------------- */
        [class*="metriccard__"] {
            gap: 0 !important;
            height: 100%;
        }
        [class*="metriccard__"] > [data-testid="stElementContainer"] {
            height: 100%;
        }
        [class*="metriccard__"] [data-testid="stMetric"] {
            position: relative;
            border-left-width: 8px;
            border-left-style: solid;
            border-left-color: #98A2B3;
        }
        /* Extra breathing room next to the thicker left rail - the other
           three sides keep the shared 20px card padding. Only KPI cards
           carry a rail; activity tiles, program tiles and panels are
           destinations, not judgements, and stay clean. */
        [class*="metriccard__"] [data-testid="stMetric"] > div:first-child {
            padding-left: 26px;
        }
        [class*="metriccard__good"] [data-testid="stMetric"] {
            border-left-color: #16865B;
        }
        [class*="metriccard__watch"] [data-testid="stMetric"] {
            border-left-color: #D98A15;
        }
        [class*="metriccard__bad"] [data-testid="stMetric"] {
            border-left-color: #C9434F;
        }
        [class*="metriccard__unknown"] [data-testid="stMetric"] {
            border-left-color: #CDD2DE;
        }

        /* Nested stat chips (metric_chip_row) read as recessed wells inside an
           already-white card: a light blue-grey fill drawn from the page
           background, no border. Previously they were white-on-white with a
           hairline border, which left the parent card looking flat. */
        [class*="chip_row__"] [data-testid="stMetric"] {
            background: #EEF2FA !important;
            border: 1px solid transparent !important;
            box-shadow: none !important;
        }
        [class*="chip_row__"] [data-testid="stMetricLabel"] p {
            color: #5B657A;
        }
        [class*="chip_row__"] [data-testid="stMetricValue"] p {
            color: #08142A;
        }

        /* ---------------------------------------------------------------
           SnowJira floating chat panel (common.chat.render_floating_button):
           ordinary page content pinned via `position: fixed`, exactly like
           the launcher button itself - deliberately NOT an st.dialog, which
           renders as a full-viewport modal and would block every other page
           element (the sidebar included) while open. Floats with equal
           margin from the top/right/bottom edges rather than going full-
           bleed/full-height, rounded corners and this app's own color/
           border/shadow/radius language throughout (a compact widget, not a
           drawer). Only the message list scrolls - the panel itself and its
           header/input never do (`overflow: hidden` on the panel clips to
           its own rounded corners; the message list gets its own nested
           `overflow-y: auto`). stVerticalBlock (what `st.container` renders
           as) is already a flex column by default, so the header/badge/
           messages/input stack correctly with no extra display rule needed
           here - only the message list's own `flex: 1` to claim the
           leftover height. */
        [class*="st-key-snowjira_fab_panel"] {
            position: fixed;
            top: 24px;
            right: 24px;
            bottom: 24px;
            width: 400px;
            max-width: calc(100vw - 48px);
            z-index: 1000;
            background-color: #FFFFFF !important;
            border: 1px solid #DCE2ED;
            border-radius: 20px;
            box-shadow: 0 16px 48px rgba(8, 20, 42, 0.22);
            padding: 20px !important;
            box-sizing: border-box;
            overflow: hidden;
            animation: snowjira-panel-in 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes snowjira-panel-in {
            from { opacity: 0; transform: translateY(10px) scale(0.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        [class*="st-key-snowjira_fab_header"] {
            justify-content: space-between;
            gap: 8px;
        }
        [class*="st-key-snowjira_fab_header"] [data-testid="stMarkdownContainer"] h5 {
            margin: 0;
            color: #08142A;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        /* Close button: a small round icon button, not a full-size default
           secondary button. */
        [class*="st-key-snowjira_fab_close"] [data-testid="stBaseButton-secondary"] {
            width: 30px;
            height: 30px;
            padding: 0;
            border-radius: 999px;
            border-color: #DCE2ED;
            flex-shrink: 0;
        }
        /* Message list: the one scrolling region. `min-height: 0` overrides
           a flex item's default `min-height: auto`, which otherwise refuses
           to shrink below its content size and silently breaks
           `overflow-y: auto` in a constrained flex column - a common CSS
           gotcha, not an optional nicety here. */
        [class*="st-key-snowjira_fab_messages"] {
            flex: 1 1 auto;
            min-height: 0;
            overflow-y: auto;
            margin-top: 8px;
        }
        /* "@ Reference" trigger + attached chips, directly above the input -
           compact and left-aligned rather than the default full-size/full-
           width button, and wrapping onto more than one line if several
           references are attached instead of overflowing. */
        [class*="st-key-snowjira_fab_refs"] {
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 10px;
        }
        [class*="st-key-snowjira_fab_refs"] [data-testid="stPopover"] button,
        [class*="st-key-snowjira_fab_refs"] > [data-testid="stElementContainer"] [data-testid="stBaseButton-secondary"] {
            padding: 4px 10px;
            font-size: 12px;
            border-radius: 999px;
            border-color: #DCE2ED;
            color: #33415C;
        }
        [class*="st-key-snowjira_fab_panel"] [data-testid="stChatMessage"] {
            padding: 4px 0;
        }
        [class*="st-key-snowjira_fab_panel"] [class*="st-key-agent_chat_input"] {
            margin-top: 12px;
        }

        /* ---------------------------------------------------------------
           SnowJira floating launcher (common.chat.render_floating_button):
           a fixed bottom-right pill, always available regardless of which
           page or sidebar state is active - matches the reference design's
           floating assistant button. The container itself is pulled out of
           normal document flow; only its button gets the pill treatment
           (bigger radius/padding/shadow than an ordinary primary button).
           --------------------------------------------------------------- */
        /* Exact-token `.st-key-snowjira_fab` (not `[class*=...]`) throughout
           this block, deliberately - the panel and its header/messages/close
           sub-containers below are keyed "snowjira_fab_panel"/"_header"/etc,
           and a *substring* match on "st-key-snowjira_fab" catches those too
           (it's a literal prefix of all of them), which put this button's
           own fixed-corner positioning and pill styling onto the panel and
           every element inside it as well. A plain class selector matches
           only the exact space-separated token Streamlit actually renders
           ("st-key-snowjira_fab" on the button's container alone), not one
           that merely starts with it. */
        .st-key-snowjira_fab {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999;
            width: auto;
        }
        .st-key-snowjira_fab [data-testid="stBaseButton-primary"] {
            border-radius: 999px;
            padding: 14px 24px;
            font-size: 15px;
            box-shadow: 0 6px 18px rgba(36, 50, 255, 0.28);
        }
        .st-key-snowjira_fab [data-testid="stBaseButton-primary"]:hover {
            filter: brightness(1.08);
        }
        /* The label's actual font-weight lives on Streamlit's own <p>, which
           sets it explicitly (400) rather than inheriting from the button -
           a font-weight set on the button itself is silently overridden, so
           it has to be pinned here instead. */
        .st-key-snowjira_fab [data-testid="stMarkdownContainer"] p {
            font-weight: 800 !important;
        }
        /* This one button's icon is a Carbon Design System glyph ("AiAgent",
           https://carbondesignsystem.com/elements/icons/library/) rather
           than the Material Symbols the rest of the app uses - the only icon
           in the app rendered this way, by explicit request. Streamlit's
           icon= param only accepts an emoji or a Material Symbols shortcode
           (no arbitrary SVG), so the Material glyph common.icons still
           renders here (kept as a semantic fallback) is hidden and the
           Carbon SVG is painted over it as a CSS mask - mask-image traces
           the SVG's shape and lets `background-color` fill it, so it
           inherits the button's white exactly like a real icon would,
           instead of needing the SVG's own fill hand-edited. Dilated very
           slightly bolder (see `carbon-icon-bold` above) to match the
           button label's own bolded weight. */
        .st-key-snowjira_fab [data-testid="stIconMaterial"] {
            font-size: 0 !important;
            display: inline-block !important;
            width: 19px !important;
            height: 19px !important;
            /* Streamlit's own icon-slot wrapper around this span is a flex
               container fixed to its native (smaller) icon width, and a flex
               child with no real content shrinks to fit that regardless of
               its own width - flex-shrink/flex-basis here make it hold its
               full 19px instead of collapsing back to Streamlit's 14px. */
            flex: none !important;
            background-color: #FFFFFF;
            -webkit-mask-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiI+PHBhdGggZD0iTTE2LDMxYy0xLjY1NDMsMC0zLTEuMzQ1Ny0zLTMsMC0xLjMwMzcuODM1OS0yLjQxNiwyLTIuODI5MXYtNC42MTA0Yy0uMTQ3OS0uMDg1OS0uMjg3Ni0uMTkxNC0uNDE0MS0uMzE4NGwtLjcwMTItLjcwMTItMy4xNzM4LDMuMTc0OGMuMTg1NS4zODk2LjI4OTEuODI1Mi4yODkxLDEuMjg0MiwwLDEuNjU0My0xLjM0NTcsMy0zLDNzLTMtMS4zNDU3LTMtMywxLjM0NTctMywzLTNjLjQ2NTgsMCwuOTA3Mi4xMDY0LDEuMzAwOC4yOTY5bDMuMTY5NC0zLjE2OTktLjcxMjktLjcxMjljLS4xMjY1LS4xMjYtLjIzMjQtLjI2NTYtLjMxNzktLjQxNDFoLTQuNjEwOGMtLjQxMjYsMS4xNjQxLTEuNTI0OSwyLTIuODI4NiwyLTEuNjU0MywwLTMtMS4zNDU3LTMtM3MxLjM0NTctMywzLTNjMS4zMDM3LDAsMi40MTYuODM1OSwyLjgyODYsMmg0LjYxMDRjLjA4NTktLjE0NzkuMTkxOS0uMjg3Ni4zMTg0LS40MTQxbC43MDYxLS43MDYxLTMuMTcxOS0zLjE3MjRjLS4zOTE2LjE4NzUtLjgyOTYuMjkyNS0xLjI5MTUuMjkyNS0xLjY1NDMsMC0zLTEuMzQ1Ny0zLTNzMS4zNDU3LTMsMy0zLDMsMS4zNDU3LDMsM2MwLC40NjI5LS4xMDU1LjkwMTktLjI5MzUsMS4yOTM5bDMuMTcwOSwzLjE3MTkuNzA4NS0uNzA4NWMuMTI2NS0uMTI2NS4yNjYxLS4yMzI0LjQxNDEtLjMxODR2LTQuNjEwNGMtMS4xNjQxLS40MTI2LTItMS41MjQ5LTItMi44Mjg2LDAtMS42NTQzLDEuMzQ1Ny0zLDMtM3MzLDEuMzQ1NywzLDNjMCwxLjMwMzctLjgzNTksMi40MTYtMiwyLjgyODZ2NC42MTA0Yy4xNDg0LjA4NTkuMjg3MS4xOTE5LjQxNDEuMzE4NGwuNzEyOS43MTI5LDMuMTY5OS0zLjE2OTRjLS4xOTA0LS4zOTM2LS4yOTY5LS44MzUtLjI5NjktMS4zMDA4LDAtMS42NTQzLDEuMzQ1Ny0zLDMtM3MzLDEuMzQ1NywzLDMtMS4zNDU3LDMtMywzYy0uNDU5LDAtLjg5NDUtLjEwMzUtMS4yODQyLS4yODkxbC0zLjE3NDgsMy4xNzM4LjcwMTIuNzAxMmMuMTI3LjEyNjUuMjMyNC4yNjYxLjMxODQuNDE0MWg0LjYxMDRjLjQxMzEtMS4xNjQxLDEuNTI1NC0yLDIuODI5MS0yLDEuNjU0MywwLDMsMS4zNDU3LDMsM3MtMS4zNDU3LDMtMywzYy0xLjMwMzcsMC0yLjQxNi0uODM1OS0yLjgyOTEtMmgtNC42MTA0Yy0uMDg1OS4xNDg0LS4xOTE0LjI4NzEtLjMxODQuNDE0MWwtLjcwOC43MDgsMy4xNzE5LDMuMTcxOWMuMzkxNi0uMTg4NS44MzExLS4yOTM5LDEuMjkzOS0uMjkzOSwxLjY1NDMsMCwzLDEuMzQ1NywzLDNzLTEuMzQ1NywzLTMsMy0zLTEuMzQ1Ny0zLTNjMC0uNDYxOS4xMDQ1LS45MDA0LjI5Mi0xLjI5MWwtMy4xNzE5LTMuMTcyOS0uNzA2MS43MDYxYy0uMTI3LjEyNy0uMjY1Ni4yMzI0LS40MTQxLjMxODR2NC42MTA0YzEuMTY0MS40MTMxLDIsMS41MjU0LDIsMi44MjkxLDAsMS42NTQzLTEuMzQ1NywzLTMsM1pNMTYsMjdjLS41NTEzLDAtMSwuNDQ4Mi0xLDFzLjQ0ODcsMSwxLDEsMS0uNDQ4MiwxLTEtLjQ0ODctMS0xLTFaTTI0LDIzYy0uNTUxOCwwLTEsLjQ0ODItMSwxcy40NDgyLDEsMSwxLDEtLjQ0ODIsMS0xLS40NDgyLTEtMS0xWk04LDIzYy0uNTUxMywwLTEsLjQ0ODItMSwxcy40NDg3LDEsMSwxLDEtLjQ0ODIsMS0xLS40NDg3LTEtMS0xWk0xNiwxMy4xNzE0bC0yLjgyODYsMi44Mjg2LDIuODI4NiwyLjgyODEsMi44MjgxLTIuODI4MS0yLjgyODEtMi44Mjg2Wk0yOCwxNWMtLjU1MTgsMC0xLC40NDg3LTEsMXMuNDQ4MiwxLDEsMSwxLS40NDg3LDEtMS0uNDQ4Mi0xLTEtMVpNNCwxNWMtLjU1MTMsMC0xLC40NDg3LTEsMXMuNDQ4NywxLDEsMSwxLS40NDg3LDEtMS0uNDQ4Ny0xLTEtMVpNMjQsN2MtLjU1MTgsMC0xLC40NDg3LTEsMXMuNDQ4MiwxLDEsMSwxLS40NDg3LDEtMS0uNDQ4Mi0xLTEtMVpNOCw3Yy0uNTUxMywwLTEsLjQ0ODctMSwxcy40NDg3LDEsMSwxLDEtLjQ0ODcsMS0xLS40NDg3LTEtMS0xWk0xNiwzYy0uNTUxMywwLTEsLjQ0ODctMSwxcy40NDg3LDEsMSwxLDEtLjQ0ODctMS0xLS40NDg3LTEtMS0xWiIvPjwvc3ZnPg==");
            mask-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAzMiAzMiI+PHBhdGggZD0iTTE2LDMxYy0xLjY1NDMsMC0zLTEuMzQ1Ny0zLTMsMC0xLjMwMzcuODM1OS0yLjQxNiwyLTIuODI5MXYtNC42MTA0Yy0uMTQ3OS0uMDg1OS0uMjg3Ni0uMTkxNC0uNDE0MS0uMzE4NGwtLjcwMTItLjcwMTItMy4xNzM4LDMuMTc0OGMuMTg1NS4zODk2LjI4OTEuODI1Mi4yODkxLDEuMjg0MiwwLDEuNjU0My0xLjM0NTcsMy0zLDNzLTMtMS4zNDU3LTMtMywxLjM0NTctMywzLTNjLjQ2NTgsMCwuOTA3Mi4xMDY0LDEuMzAwOC4yOTY5bDMuMTY5NC0zLjE2OTktLjcxMjktLjcxMjljLS4xMjY1LS4xMjYtLjIzMjQtLjI2NTYtLjMxNzktLjQxNDFoLTQuNjEwOGMtLjQxMjYsMS4xNjQxLTEuNTI0OSwyLTIuODI4NiwyLTEuNjU0MywwLTMtMS4zNDU3LTMtM3MxLjM0NTctMywzLTNjMS4zMDM3LDAsMi40MTYuODM1OSwyLjgyODYsMmg0LjYxMDRjLjA4NTktLjE0NzkuMTkxOS0uMjg3Ni4zMTg0LS40MTQxbC43MDYxLS43MDYxLTMuMTcxOS0zLjE3MjRjLS4zOTE2LjE4NzUtLjgyOTYuMjkyNS0xLjI5MTUuMjkyNS0xLjY1NDMsMC0zLTEuMzQ1Ny0zLTNzMS4zNDU3LTMsMy0zLDMsMS4zNDU3LDMsM2MwLC40NjI5LS4xMDU1LjkwMTktLjI5MzUsMS4yOTM5bDMuMTcwOSwzLjE3MTkuNzA4NS0uNzA4NWMuMTI2NS0uMTI2NS4yNjYxLS4yMzI0LjQxNDEtLjMxODR2LTQuNjEwNGMtMS4xNjQxLS40MTI2LTItMS41MjQ5LTItMi44Mjg2LDAtMS42NTQzLDEuMzQ1Ny0zLDMtM3MzLDEuMzQ1NywzLDNjMCwxLjMwMzctLjgzNTksMi40MTYtMiwyLjgyODZ2NC42MTA0Yy4xNDg0LjA4NTkuMjg3MS4xOTE5LjQxNDEuMzE4NGwuNzEyOS43MTI5LDMuMTY5OS0zLjE2OTRjLS4xOTA0LS4zOTM2LS4yOTY5LS44MzUtLjI5NjktMS4zMDA4LDAtMS42NTQzLDEuMzQ1Ny0zLDMtM3MzLDEuMzQ1NywzLDMtMS4zNDU3LDMtMywzYy0uNDU5LDAtLjg5NDUtLjEwMzUtMS4yODQyLS4yODkxbC0zLjE3NDgsMy4xNzM4LjcwMTIuNzAxMmMuMTI3LjEyNjUuMjMyNC4yNjYxLjMxODQuNDE0MWg0LjYxMDRjLjQxMzEtMS4xNjQxLDEuNTI1NC0yLDIuODI5MS0yLDEuNjU0MywwLDMsMS4zNDU3LDMsM3MtMS4zNDU3LDMtMywzYy0xLjMwMzcsMC0yLjQxNi0uODM1OS0yLjgyOTEtMmgtNC42MTA0Yy0uMDg1OS4xNDg0LS4xOTE0LjI4NzEtLjMxODQuNDE0MWwtLjcwOC43MDgsMy4xNzE5LDMuMTcxOWMuMzkxNi0uMTg4NS44MzExLS4yOTM5LDEuMjkzOS0uMjkzOSwxLjY1NDMsMCwzLDEuMzQ1NywzLDNzLTEuMzQ1NywzLTMsMy0zLTEuMzQ1Ny0zLTNjMC0uNDYxOS4xMDQ1LS45MDA0LjI5Mi0xLjI5MWwtMy4xNzE5LTMuMTcyOS0uNzA2MS43MDYxYy0uMTI3LjEyNy0uMjY1Ni4yMzI0LS40MTQxLjMxODR2NC42MTA0YzEuMTY0MS40MTMxLDIsMS41MjU0LDIsMi44MjkxLDAsMS42NTQzLTEuMzQ1NywzLTMsM1pNMTYsMjdjLS41NTEzLDAtMSwuNDQ4Mi0xLDFzLjQ0ODcsMSwxLDEsMS0uNDQ4MiwxLTEtLjQ0ODctMS0xLTFaTTI0LDIzYy0uNTUxOCwwLTEsLjQ0ODItMSwxcy40NDgyLDEsMSwxLDEtLjQ0ODIsMS0xLS40NDgyLTEtMS0xWk04LDIzYy0uNTUxMywwLTEsLjQ0ODItMSwxcy40NDg3LDEsMSwxLDEtLjQ0ODIsMS0xLS40NDg3LTEtMS0xWk0xNiwxMy4xNzE0bC0yLjgyODYsMi44Mjg2LDIuODI4NiwyLjgyODEsMi44MjgxLTIuODI4MS0yLjgyODEtMi44Mjg2Wk0yOCwxNWMtLjU1MTgsMC0xLC40NDg3LTEsMXMuNDQ4MiwxLDEsMSwxLS40NDg3LDEtMS0uNDQ4Mi0xLTEtMVpNNCwxNWMtLjU1MTMsMC0xLC40NDg3LTEsMXMuNDQ4NywxLDEsMSwxLS40NDg3LDEtMS0uNDQ4Ny0xLTEtMVpNMjQsN2MtLjU1MTgsMC0xLC40NDg3LTEsMXMuNDQ4MiwxLDEsMSwxLS40NDg3LDEtMS0uNDQ4Mi0xLTEtMVpNOCw3Yy0uNTUxMywwLTEsLjQ0ODctMSwxcy40NDg3LDEsMSwxLDEtLjQ0ODcsMS0xLS40NDg3LTEtMS0xWk0xNiwzYy0uNTUxMywwLTEsLjQ0ODctMSwxcy40NDg3LDEsMSwxLDEtLjQ0ODctMS0xLS40NDg3LTEtMS0xWiIvPjwvc3ZnPg==");
            -webkit-mask-repeat: no-repeat;
            mask-repeat: no-repeat;
            -webkit-mask-size: contain;
            mask-size: contain;
            -webkit-mask-position: center;
            mask-position: center;
            filter: url(#carbon-icon-bold);
        }
        </style>

        <svg width="0" height="0" style="position: absolute; overflow: hidden;">
            <filter id="carbon-icon-bold" x="-30%" y="-30%" width="160%" height="160%">
                <feMorphology operator="dilate" radius="0.5"></feMorphology>
            </filter>
            <filter id="carbon-icon-bold-strong" x="-50%" y="-50%" width="200%" height="200%">
                <feMorphology operator="dilate" radius="1.2"></feMorphology>
            </filter>
        </svg>
        """,
        unsafe_allow_html=True,
    )
