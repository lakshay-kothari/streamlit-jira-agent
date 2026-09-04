# Design system - Program Command Center

This is the single reference for how this app looks, is structured, and
behaves. Read it before adding a page, component, or feature so new work
matches everything else instead of drifting into its own style.

The short version: **configure, don't decorate.** Native Streamlit theming
and elements (`st.metric`, `st.badge`, `st.container(border=True)`,
`st.navigation`) do almost everything here. Custom CSS is limited to the one
thing native theming can't express (see [Theme tokens](#theme-tokens)).

## Information architecture

### The portfolio model

**A Strategic Initiative is a Program.** There is one entity - a program, one row
in the `programs` registry - and `is_strategic` is a boolean facet of it. This is
the whole answer to "all Strategic Initiatives are Programs, but not all Programs
are Strategic Initiatives", and it is load-bearing:

- The **Programs** page lists every row, with a Strategic badge and a filter.
- The **Strategic initiatives** page is the same rows at sponsor altitude,
  filtered to `is_strategic`. It reads no table of its own.
- Therefore the initiative count can never exceed the program count, and a
  program can never be counted twice in a portfolio total.

`data_access.get_strategic_initiatives()` is a *filter over programs*, not a
separate fetch. Never reintroduce a parallel table - that is exactly what let the
two pages report the same work as if it were disjoint.

Leaders/managers track 4 kinds of activity:

| Activity | Data source | Page |
|---|---|---|
| **Programs** | `programs` + `work_items` | [`app_pages/programs.py`](app_pages/programs.py) |
| **Agents** | `board_items` (AI/BI board) | [`app_pages/agents.py`](app_pages/agents.py) |
| **Strategic initiatives** | `programs` where `is_strategic` | [`app_pages/strategic_initiatives.py`](app_pages/strategic_initiatives.py) |
| **Demands** | `demands` (intake export) | [`app_pages/demands.py`](app_pages/demands.py) |

`common/config.ACTIVITIES` is the single source of truth for this table.

Three cross-cutting lenses sit outside the four activities, under `Insights`:
**Needs attention** (one ranked action list), **Team & workload**, and **Data
coverage** (which metrics can be trusted, and what to populate to earn the rest).

### Sources and adapters

Every program arrives from a different tool with different columns. So:

- `common/etl.py` only *discovers* files and decides which adapter owns each.
- `common/adapters/` holds one adapter per source shape - `jira`, `servicenow`,
  `board`, `demand_intake`, `milestone_sources` (Excel tracker / status report /
  Smartsheet / TrackWise) - each mapping its own columns onto one contract,
  `WORK_ITEM_COLUMNS` in `common/adapters/base.py`.
- **Adding a program on a new tool = writing one adapter.** It requires no change
  to `kpi.py`, `charts.py`, or any page.
- `data/raw/program_registry.csv` carries the **attach rules** (`source_files`,
  `jira_project_keys`, `demand_assignment_groups`, `agent_sub_domains`) that bind
  rows to a program. Unmatched rows land on `unattached` - visible and chaseable,
  never silently dropped.

### The status taxonomy

`To Do / In Progress / Blocked / Done / Cancelled / Unknown`. Two of these exist
because folding them away hid real problems:

- **Blocked** was inside In Progress, hiding 317 items waiting on someone else -
  the most actionable state in the dataset.
- **Cancelled** was inside Done (Jira files "Descoped" under the Done category),
  which counted 1,311 abandoned items as delivered and overstated completion by
  about five points. `% complete = Done / (Total - Cancelled)`.
- **Unknown** means the source recorded no status. It is never backfilled to a
  real state - 146 of 149 agents had a blank Status, and calling that "Not
  Started" reported missing data as a decision.

## Navigation

- Routing is native `st.navigation`/`st.Page` (see `streamlit_app.py`), not a
  hand-rolled button sidebar. Every page gets its own URL, and browser
  back/forward works.
- Pages are **direct scripts** in `app_pages/`, not functions called from a
  router with a `ctx` dict. A page may still use small private helper
  functions to organize a long body (e.g. `_render_hub()` / `_render_detail()`
  in `programs.py`), but the module-level script is what actually runs.
- Group pages in `st.navigation({...})` by intent, not by data source:
  `""` for Overview, `"Explore"` for the 4 activities, `"Insights"` for
  cross-cutting lenses like Team & workload.
- Each page fetches its own data via `common.data_access.get_issues()` /
  `get_board_items()` (cached with `st.cache_data`). Don't thread data through
  `st.session_state` between pages - the cache already makes repeat calls
  cheap, and pages stay independently testable.

## The hub + drill-down pattern

Both **Programs** and **Agents** follow the same two-level shape; use it for
any future page that needs a "list of things -> one thing in detail" flow:

1. **Hub view**: cards or charts summarizing every item at a glance.
2. **Detail view**: the full breakdown for one item, opened by clicking.
3. The selection lives in a **query param** (`st.query_params`), not just
   `st.session_state` - so the detail view has its own shareable URL and
   survives a page refresh. Query params are set manually here (not via
   `bind="query-params"`) because the trigger is a button click, and `bind=`
   only supports plain input widgets.
4. A `breadcrumb_back(label, param)` (from `common/components.py`) at the top
   of every detail view clears the param and returns to the hub.

```python
# Hub/detail toggle - the shape every drill-down page follows
selected = st.query_params.get("program")
if selected and selected in issues["program_name"].unique():
    _render_detail(issues[issues["program_name"] == selected], selected)
else:
    _render_hub()
```

**Agents** extends this with *chained, clickable KPI filters* instead of a
single selection: every chart is a real input, not decoration. Clicking a bar
adds a query param; each chart computes its own counts from every filter
*except its own dimension*, so all its bars stay clickable for re-selection
(true cross-filtering). See `app_pages/agents.py`'s `_apply()` helper and
`common.charts.bar_chart(..., highlight=...)`, which recolors the active bar
in the primary accent and mutes the rest.

When adding a new interactive chart, follow this shape:

```python
event = st.plotly_chart(fig, on_select="rerun", selection_mode="points", key="...")
if event.selection.points:
    clicked = event.selection.points[0].get("y")  # "y" holds the category for horizontal bars
    st.query_params[param] = str(clicked)
    st.rerun()
```

Always pair a clickable chart with `common.components.drill_caption()` so the
affordance is discoverable, and show active filters with
`common.components.filter_chip_row(active_filters)` so they're visible and
dismissible.

## Theme tokens

All color/font/radius/border tokens live in
[`.streamlit/config.toml`](.streamlit/config.toml) - **never** hard-code a hex
value in a component or page; reference the token instead (`primaryColor`,
named badge colors like `color="blue"`, etc.). This is what keeps a future
rebrand a one-file change.

This is a premium enterprise-executive palette (matches the Medtronic
reference dashboard look):

- **Main theme**: light, very light cool-gray page background (`#F4F6FB`),
  white cards, deep-navy text (`#0A1428`), vivid royal-blue primary
  (`#2432FF`) for buttons/links/active states, `Open Sans` body font paired
  with `Montserrat` headings (`headingFont`, with `headingFontSizes`/
  `headingFontWeights` tuned so h1 is a bold ~34px page title). Cards/
  containers use `baseRadius = 16px`; buttons use the tighter
  `buttonRadius = 12px` (spec: 16-20px card rounding, 10-12px button
  rounding).
- **Sidebar theme**: deep navy (`#08142A`), sampled from the Medtronic
  wordmark, with the *same* royal-blue accent (`#2432FF`) as the main theme
  so the active nav item and every primary action share one accent color -
  don't reintroduce a separate sidebar accent hue.
- **Semantic colors** are restrained on purpose: green `#16865B`
  (healthy/on-track/live), amber `#D98A15` (attention/WIP), red `#C9434F`
  (critical/at-risk), violet `#6557D8` (secondary/lavender). Declared once in
  `[theme]` and used everywhere via `st.badge(..., color=)` and
  `delta_color=` - don't invent new ad-hoc colors in markdown. Status pills
  get their soft tinted background/text automatically from these tokens
  (Streamlit auto-derives `<color>BackgroundColor`/`<color>TextColor`) - never
  hard-code a solid saturated badge background.
- **Charts are the one exception**: Plotly isn't theme-aware, so
  `common/theme.py::CHART_COLORWAY` / `STATUS_COLORS` / `CHART_FONT` hold the
  same font/hex values as the config, and `common/charts.py` applies them
  centrally. If you change a color or font in `config.toml`, update the
  matching constant in `theme.py` too.
### Cards: one look, keyed containers

Every card in the product is the same object: **white, 20px radius, 24px padding,
a hairline border and a very soft shadow**. Three kinds:

| Kind | Helper | Indicator |
|---|---|---|
| KPI card | `metric_card(result)` | status bar (green / amber / red / grey) |
| Tile | `program_card`, `initiative_card`, `activity_card` | none |
| Plain panel | `panel(title, icon, caption)`, list rows | none |

**Only KPI cards carry a status indicator.** A tile or a panel is a destination,
not a judgement, so it stays clean - putting a coloured bar on everything makes
the one place it means something stop reading as a signal.

The indicator is a small rounded bar **inside** the metric card, inset 20px from
the left, right and bottom so it lines up with the card's own content gutter.
It must not be pinned to the card's outer edge: there it reads as sitting on top
of the frame and clips unevenly against the corner radius. The metric's content
box carries `padding-bottom: 36px` to make room for it. The status word also
appears in the card's tooltip, so colour is a shortcut and never the only way to
read the card.

Nested stat chips (`metric_chip_row`) are a light blue-grey (`#EEF2FA`) well
inside the white card, so a tile reads as having depth rather than as a flat
white rectangle.

**How the CSS finds a card:** through its Streamlit container **key**, not
through a Streamlit internal. Prefixes live in `common/theme.py`
(`METRIC_CARD_KEY_PREFIX`, `TILE_KEY_PREFIX`, `PANEL_KEY_PREFIX`) and
`components.card_key()` builds them. A new card must be created with one of the
helpers above, or with `st.container(border=True, key=card_key(...))` - a bare
`st.container(border=True)` renders as a transparent, 13px-padded box and will
not pick up any of the card styling.

> This matters because the card CSS previously targeted
> `[data-testid="stVerticalBlock"][data-test-wrap="false"]`, an attribute that
> **does not exist in Streamlit 1.60** - so the entire block (padding, radius,
> white fill, shadow, card buttons) had silently stopped applying. If a card
> ever looks unstyled again, check the selector against the live DOM first.

**Sidebar:** nav rows must have identical vertical rhythm expanded and
collapsed. The collapsed rule centres the pill with `margin-left/right: auto` -
never the `margin: 0 auto` shorthand, which also zeroes Streamlit's own 1.75px
vertical margin and makes collapsed rows 3.5px tighter than expanded ones.

- **Custom CSS is a last resort**, but a few enterprise-dashboard details
  have no native theme token, so `common/theme.py::inject_global_css()`
  injects one small, consolidated block for exactly those cases: soft card
  shadows, uppercase nav-section-label letter-spacing (KPI/chip labels are
  *not* uppercase - sentence case, matching the reference design), the
  sidebar logo/spacing/padding, the solid `primaryColor` pill for the
  *selected* sidebar nav item - Streamlit's default is a thin, low-contrast
  tinted background - a compact icon-only rail when the sidebar is
  *collapsed* (Streamlit's default just hides it entirely) whose logo
  crossfades into the collapse/expand chevron on hover instead of reserving
  a separate row for it, the hidden native app header (`stHeader`)/redundant
  floating expand button, the white-filled/repositioned KPI card (see
  `kpi_metric`), the light-gray "chip" fill used by
  `common.components.metric_chip_row`, and the **wrap-instead-of-truncate +
  equal-height-row** rule (below) - plus the pre-existing rule keeping the
  sidebar collapse arrow visible. Anything else you're tempted to add with
  CSS almost certainly has a native Streamlit equivalent - check
  `references/theme.md` and `references/design.md` in the
  `developing-with-streamlit` skill first, and don't scatter new inline
  `st.markdown(..., unsafe_allow_html=True)` styles across pages; extend the
  one CSS block in `theme.py` instead.
- **Cards never truncate with "..."** - if a label/value/description doesn't
  fit, it wraps instead, and the card grows to fit it. Every other card in
  that row grows to match (`align-items: stretch` on every
  `stHorizontalBlock`, plus a `height: 100%` chain from `stColumn` down to
  the bordered card), so a long label in one card never leaves its siblings
  looking short. This is why `kpi_metric`/`activity_card`/`program_card` all
  pass `height="stretch"` rather than a fixed px height - the fixed height
  was the old (wrong) way of forcing equal rows, and it's what caused
  truncation in the first place. Chip labels (`metric_chip_row`) are the one
  exception - they're 1-2 words and forced to `nowrap` so 3 chips fit on one
  row like the reference design, instead of wrapping to 2 rows.

## Brand assets (`assets/`)

`st.logo()` (called once, in `streamlit_app.py`) takes two different images
for two different contexts, and mixing them up breaks visibility:

- **`image`** (`common.theme.logo_path()`, resolves to
  `assets/medtronic_logo.png`) - the full wordmark, shown in the *expanded*
  sidebar. It has a **transparent background**, which only looks right
  because the expanded sidebar itself is dark navy - the glyphs blend
  straight into it with no visible box, matching the reference design.
- **`icon_image`** (`common.theme.logo_icon_path()`, resolves to
  `assets/medtronic_icon.png`) - a compact square "M" badge with its **own
  opaque navy background**, shown in the *collapsed* sidebar's header. That
  header sits on the light main-content background, so a transparent white
  wordmark would be invisible there - the opaque badge is what keeps the
  brand visible regardless of sidebar state.

Both were generated once from `assets/Medtronic_wordmark.jpg` (background
detection + crop) rather than hand-designed - if the brand asset changes,
regenerate both rather than editing pixels directly.

## Icons

Material Symbols only (`:material/icon_name:`), never emoji, via
`common.icons.icon("semantic-name")`. Add new semantic names to the
`_MATERIAL_ICON_MAP` in `common/icons.py` rather than hard-coding
`:material/...:` strings inline, so a future icon swap is one line. Verify a
new icon name exists in Streamlit's bundled Material Symbols set before using
it (unsupported names raise an error).

## Component patterns (`common/components.py`)

Reach for these before writing new markup:

| Function | Use for |
|---|---|
| `page_header(title, subtitle, icon_name)` | Every page's title + one-line caption. Title is text-only (no icon) - `icon_name` is accepted but ignored. |
| `metric_card(result, trend)` / `metric_row(results)` | **Every KPI that should be judged.** Takes a `MetricResult` from `common/metrics.py`, so the card carries the value, an honest trend (or none), the "so what" insight, a status bar inside its bottom gutter, and a tooltip with the question + target + coverage caveat. `metric_row`'s `key` must start with `kpi_row` - the no-wrap/equal-width CSS matches that prefix. |
| `panel(title, icon_name, caption)` | Every bordered panel holding a chart, table or section. Use it instead of a bare `st.container(border=True)`, which renders unstyled. |
| `insight_note(text, tone)` | The one data-derived sentence under a KPI row or chart that says what the numbers mean. Use it where a reader would otherwise have to infer the conclusion. |
| `empty_metric_note(field, enables, coverage_pct)` | Where a chart would have rendered blank: names the unpopulated field and the metric it blocks, instead of showing an empty panel. |
| `kpi_metric(label, value, delta, icon_name, help_text, description)` | Plain KPI card for context numbers only (a filtered row count). Anything with a target belongs in `metric_card`. Always inside `st.container(horizontal=True, key="kpi_row")`, and always `height="stretch"` - the row never wraps a card onto its own line (`flex-wrap: nowrap`), and every card in it stretches to match the tallest one instead of clipping a long label/description. Card title has no icon (`icon_name` is accepted but ignored) and uses the card's own muted slate title color; `help_text` adds a small circular "!" icon pinned to the card's top-right corner (a CSS-recolored/reshaped version of the native help tooltip); `description` adds a one-line explanation under the value in the same muted color (shown even without a delta) - both should be filled in with a short, truthful clarification whenever one is useful. |
| `metric_chip_row(key, metrics)` | The compact, light-gray-filled stat row nested inside an already-bordered card (used by `activity_card`/`program_card`) - distinct from the bordered/shadowed top-level KPI cards from `kpi_metric`. `key` must be unique per call site. |
| `activity_card(...)` | One of the 4 top-level activity tiles on Overview. `height="stretch"` so all 4 match the tallest one in their row instead of a fixed px height. |
| `program_card(...)` | One program tile on the Programs hub. `height="stretch"`, same equal-height behavior as `activity_card`. |
| `breadcrumb_back(label, param)` | Top of every drill-down detail view. |
| `filter_chip_row(active_filters)` | Below the KPI row on any page with clickable/queryable filters. |
| `drill_caption()` | Directly above/below a clickable chart, as a discoverability hint. |
| `coming_soon(icon_name, title, description, bullets)` | Any activity/page without real data yet - keeps it intentional, not a dead end. |
| `inline_badge(text, color, icon_name)` | A status pill inside a markdown string (e.g. several badges on one line). |

General card/layout rules:
- `st.container(border=True)` for any visual grouping - a chart, a table, a
  card. Don't add `st.divider()`; the border already separates sections.
- `st.container(horizontal=True, key="kpi_row")` for every top-level KPI row -
  the shared `key="kpi_row"` is what the `flex-wrap: nowrap` CSS in
  `inject_global_css()` targets so the row never wraps a card onto its own
  full-width line; `st.columns(n)` only for fixed chart/card grids where you
  want equal column widths. Either way, every row of cards stretches to the
  tallest card automatically (see [Theme tokens](#theme-tokens)) - you don't
  need per-page CSS to keep a row's cards the same height.
- Charts: always `st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})`
  unless the chart is interactive (drill-down), in which case add
  `on_select="rerun", selection_mode="points", key="..."` (a unique key per
  chart is required for click handling to work).
- Tables: `st.dataframe(df, width="stretch", hide_index=True)`. Add
  `on_select="rerun", selection_mode="single-row"` when a row should open more
  detail (see the agent detail panel in `app_pages/agents.py`).

## The AI agent (SnowJira)

SnowJira is a **persistent sidebar chat panel**, not a modal dialog or a
standalone page - it should always be one click away regardless of which page
a manager is looking at. It lives in an `st.expander` at the bottom of the
sidebar (`streamlit_app.py`), rendered by `common/chat.py::render()`, which
owns its own conversation history in `st.session_state` and grounds every
answer in a JSON KPI snapshot (never invents numbers outside that snapshot).
It degrades to a deterministic offline template when no Snowflake connection
is configured, so the panel is always usable in local demos.

If a future feature needs its own AI-assisted view (not a quick Q&A), give it
a dedicated page rather than overloading this panel - but keep the same
"grounded in a JSON snapshot, degrades offline" contract from `common/chat.py`.

## Data & caching conventions

- `common/data_access.py` is the *only* place that reads Snowflake or SQLite.
  Pages never touch a connection or file path directly.
- `common/kpi.py` holds every aggregation (a page should not call
  `.groupby()`/`.value_counts()` directly on a raw table - add a function to
  `kpi.py` instead, so the same aggregation is reusable and testable).
- `common/metrics.py` holds every *judgement*: a `MetricResult` is a value plus
  the question it answers, its target (from `config.METRIC_TARGETS`), its
  coverage, and a generated insight. **A metric that cannot name a decision it
  informs does not belong on a page.**
- `common/snapshots.py` provides history. Completion, throughput and backlog are
  **rewound** from item dates - real history from day one, nothing stored. Values
  that cannot be rewound (blocked counts, health) are snapshotted per build, and
  show no delta until a second build exists. **Never render a fabricated trend.**

### Honesty rules

These are not style preferences; each one exists because the old app broke it.

1. **Declare coverage.** A metric measured on part of the data says so on the
   card. Cycle time runs on 23% of the real program's completed issues.
2. **Report "not measurable" rather than zero.** Under-dated completions make
   throughput read 0/wk, which says the team delivered nothing when it means a
   field is not being filled in. `throughput_metric` returns `-` with the reason.
3. **A future date is a plan, not activity.** Demand go-lives run into 2027;
   counting them made data freshness negative and drew a dead tail on flow charts.
4. **Never guess a status.** Blank stays `Unknown`.
5. **Derive, do not transcribe.** Initiative progress comes from linked delivery
   work; the PMO register's typed `% Complete` is deliberately unused.
6. **Escape money in markdown.** `$1M ... $2M` is parsed as LaTeX by Streamlit and
   silently swallowed - use `metrics.fmt_money_md` outside `st.metric` values.
- Cache the expensive load (`get_issues()` / `get_board_items()`, already
  `@st.cache_data(ttl=300)`), then apply cheap interactive filters (query
  params, `st.multiselect`) outside the cached function.

## Adding a new feature - checklist

0. **Does the metric answer a decision?** Write down the question first. If you
   cannot name one, do not add the number. Then give it a target in
   `config.METRIC_TARGETS` and return a `MetricResult` from `common/metrics.py`.
1. Does it belong to one of the 4 activities, or is it cross-cutting? Add/extend
   accordingly (new `ACTIVITIES` entry + `app_pages/<key>.py`, or a new page
   under the right `st.navigation` group). Remember a strategic initiative is a
   *program*, not a fifth activity.
2. Does it need a hub + detail split? Follow the [drill-down pattern](#the-hub--drill-down-pattern)
   with a query param, not just `st.session_state`.
3. Are all data-fetching and aggregation calls going through
   `common/data_access.py` and `common/kpi.py`? Don't inline pandas logic in
   a page.
4. Are you reusing `common/components.py` helpers for headers, KPIs, cards,
   and empty states instead of writing new markup?
5. Are colors/fonts coming from `.streamlit/config.toml` tokens (or
   `common/theme.py`'s chart constants), not hard-coded hex in your code?
6. Are icons Material Symbols via `common.icons.icon()`, not emoji or inline
   `:material/...:` strings?
7. If it's genuinely not ready for real data yet, use `coming_soon()` rather
   than leaving a blank or broken page.
8. Is the field it depends on actually populated? Check the Data coverage page.
   If it is under-populated, add it to `kpi.COVERAGE_FIELDS` with the metric it
   blocks rather than shipping a chart that renders empty.
9. Run `python scripts/verify.py` - it asserts the taxonomy partitions the work,
   the strategic subset invariant holds, and the known-good source numbers
   still reconcile.
