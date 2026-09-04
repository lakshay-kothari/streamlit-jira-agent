# Program Command Center

A portfolio dashboard for the leaders and managers running a Data+AI
organisation. It tracks four kinds of activity - Programs (of which Strategic
Initiatives are the flagged subset), Demands and Agents - across sources that
each arrive from a different tool, and answers the questions a leader actually
has: where do I intervene, will we make the year, are we taking on more than we
finish, and what is quietly rotting.

**SnowJira**, a Snowflake Cortex-powered AI agent, sits in the sidebar grounded
in the same metric snapshot the pages render.

Built to run two ways with **zero code changes**:
- **Local demo mode** - reads a local SQLite file built from `data/raw/*.csv`.
  No Snowflake account needed to explore the UI.
- **Snowflake / Streamlit-in-Snowflake (SiS)** - once tables are provisioned
  (see below), the exact same app reads live Snowflake tables and calls
  `SNOWFLAKE.CORTEX.COMPLETE` for AI insights, using the session's native
  connection automatically.

## Project layout

```
streamlit_app.py         Entry point - page config, theme, st.logo branding, st.navigation
                          router, and the persistent sidebar AI chat panel
DESIGN_SYSTEM.md          The portfolio model, design tokens, component patterns, the
                          honesty rules every metric follows, and the new-feature checklist
common/
  config.py               Paths, Snowflake facts, ACTIVITIES, and METRIC_TARGETS - the
                          targets/SLAs that turn each number into a judgement
  adapters/               One adapter per source shape. base.py holds the work_items
                          contract + status taxonomy; registry.py the program registry
                          and its attach rules; jira / servicenow / board /
                          demand_intake / milestone_sources the per-tool mappings
  etl.py                  Source discovery + dispatch to adapters (no column mapping)
  metrics.py              MetricResult: value + question + target + coverage + insight
  kpi.py                  Every aggregation, computed over work_items
  snapshots.py            History: rewound from item dates where possible, stored only
                          where it cannot be
  charts.py               Shared Plotly builders (health matrix, funnel, flow, forecast)
  components.py           metric_card/metric_row, program & initiative cards, page chrome
  chat.py                 SnowJira sidebar chat, grounded in a metric-shaped snapshot
  cortex.py               st.connection("snowflake") wrapper + Cortex COMPLETE
  data_access.py          Unified table reader (SQLite <-> Snowflake)
app_pages/                Overview, Programs (hub + detail), Agents, Strategic initiatives
                          (hub + detail), Demands, Needs attention, Team & workload,
                          Data coverage
scripts/
  build_sqlite.py         Rebuild the local SQLite dataset from data/raw/ (+ generated/)
  generate_demo_data.py   Seeded synthetic portfolio - 16 programs across 6 source shapes
  load_snowflake.py       Push parsed tables into real Snowflake tables
  verify.py               23 invariant + regression checks; exit 1 on failure
sql/snowflake_setup.sql   DDL: database/schema/warehouse/tables/stage/app
data/raw/                 Real source exports + program_registry.csv
data/raw/generated/       Synthetic demo portfolio (delete it to run on real data alone)
assets/                   Brand images picked up automatically by st.logo()
```

## The portfolio model

**A Strategic Initiative is a Program.** One entity, one row in the `programs`
registry, with `is_strategic` as a facet of it. The Programs page lists them all;
the Strategic initiatives page is the same rows at sponsor altitude. The
initiative count is therefore always a subset of the program count, and no
program is ever counted twice.

Each program can arrive from a different tool. `data/raw/program_registry.csv`
holds one row per program plus the **attach rules** that bind delivery work,
demands and agents to it:

| Column | Binds by |
|---|---|
| `source_files` | filename (one file, one program) |
| `jira_project_keys` | Jira project key (one file hosting several programs) |
| `demand_assignment_groups` | the intake queue's assignment group |
| `agent_sub_domains` | the AI/BI board's sub-domain |

Anything unmatched lands on `unattached` - visible on the Data coverage page,
never silently dropped.

## Adding a program on a new tool

1. Drop the export into `data/raw/`.
2. Add a row to `data/raw/program_registry.csv` with an attach rule.
3. If the shape is new, add an adapter in `common/adapters/` mapping its columns
   onto `WORK_ITEM_COLUMNS` (see `base.py`). Nothing in `kpi.py`, `charts.py` or
   any page changes.
4. `python scripts/build_sqlite.py && python scripts/verify.py`

## Demo data

```powershell
python scripts\generate_demo_data.py     # writes data
aw\generatedpython scriptsuild_sqlite.py
```

16 synthetic programs across six deliberately different source shapes (Jira,
ServiceNow, an Excel milestone tracker, a weekly status report, a Smartsheet WBS,
a validated-system export), each with its own size, cadence and characteristic
failure mode. Reproducible for a given `--seed` and `--today`. **The four real
files in `data/raw/` are never modified** - delete `data/raw/generated/` and
rebuild to return the app to real data only.

## Run it locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\generate_demo_data.py   # optional: synthetic multi-program portfolio
python scripts\build_sqlite.py         # builds data\pm_agent.db from data\raw\
python scripts\verify.py               # 23 invariant + regression checks
streamlit run streamlit_app.py
```

Without any Snowflake credentials configured, the app runs entirely against
the local SQLite database and clearly labels Cortex features as "Offline
Mode" (they show a deterministic, data-grounded template instead of an LLM
response, so the whole UI stays fully usable for a demo).

### Connecting to Snowflake locally (optional)

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill
in real values under `[connections.snowflake]` (account `MDTPLC-AWSUSE1P1`, your
login, a warehouse that can run Cortex). The app uses Streamlit's official
`st.connection("snowflake")` - the same call works locally (via secrets) and
inside Streamlit-in-Snowflake (via the native session), so there's no manual
mode-switching code.

## Source detection

Drop a file into `data/raw/` and re-run the build - there is no in-app upload UI.
The adapter is chosen from the columns present:

| Signature | Adapter |
|---|---|
| `Issue key` | Jira export |
| `sys_id` / `u_state` / `assignment_group` | ServiceNow |
| `Architects` + `Sub-Domain` | AI/BI board |
| `Requestor` + `IC Approval Status` | Demand intake (.csv or .xlsx) |
| `Milestone ID` + `Baseline Finish` + `RAG` | Excel PM tracker |
| `Record ID` + `Record State` + `Gate` | TrackWise |
| `Row ID` + `Outline Level` + `Predecessors` | Smartsheet |
| `Ref` + `Deliverable` + `Committed Date` | Weekly status report |
| `Executive Sponsor` + `Phase` + `Health` | PMO register -> becomes program rows |
| anything else | generic fallback (still counted and listed) |

A generated file can also *supersede* a real one rather than add to it - see
`etl.SUPERSEDED_BY`, which is how the enriched agent board replaces the original
without either being loaded twice or the original file being modified.

## Deploying to Snowflake (Streamlit-in-Snowflake)

Your account: **MDTPLC-AWSUSE1P1** (org `MDTPLC`, account `AWSUSE1P1`, AWS
us-east-1, Business Critical edition). The default login role is `PUBLIC`,
which normally cannot create databases/warehouses/Streamlit apps - get an
account admin (or a role with `CREATE DATABASE`/`CREATE WAREHOUSE`/
`CREATE STREAMLIT`) to run the one-time setup:

1. **Provision objects**: run [`sql/snowflake_setup.sql`](sql/snowflake_setup.sql)
   in a Snowflake worksheet. This creates the `PM_AGENT` database, tables,
   a warehouse, and the `PROGRAM_COMMAND_CENTER` Streamlit app object.
2. **Load data**: run `python scripts\load_snowflake.py` (set
   `SNOWFLAKE_ACCOUNT` / `SNOWFLAKE_USER` / `SNOWFLAKE_ROLE` / etc. env vars
   first - see the script's docstring) to push the parsed CSV tables into
   Snowflake. Re-run any time `data/raw/` changes.
3. **Upload the app files**: easiest via Snowsight -> Projects -> Streamlit ->
   your app -> point it at this folder (or `PUT` the files into `@APP_STAGE`
   per the commands documented at the bottom of `snowflake_setup.sql`).
4. Open the app in Snowsight. It will detect the active Snowpark session
   automatically, read the live tables, and call Cortex for real insights -
   no secrets file needed in this mode.

## Metrics

Every KPI is a `MetricResult` carrying four things a bare number does not: the
**question** it answers, a **target** from `config.METRIC_TARGETS`, its
**coverage** (the share of rows that could actually be measured), and a generated
**insight**. A metric that cannot name a decision it informs does not go on a page.

**Portfolio (Overview):** programs off track, initiatives forecast to miss their
date, net flow (arrivals / completions), ageing work, spend vs progress.

**Program:** % complete (cancelled scope excluded from the denominator), schedule
variance (progress minus time elapsed - the single most useful program number),
blocked work and blocked age, descope rate, throughput vs its 12-week rate, cycle
time with its coverage stated, forecast vs target, burn efficiency, stale and
unowned work. Plus a health matrix, workstream roll-up, and domain progress -
domain being recovered from the Jira hierarchy, since the Domain field itself is
empty on all 10,000 rows.

**Demands:** intake vs completion, stage cycle times against their SLA with the
bottleneck named, cancellation rate *and the effort behind it*, ageing
distribution, delay reasons, and the investment-council approval backlog.

**Agents:** rollout funnel in pipeline order, owner concentration (bus factor),
time-to-live, stalled agents, demand-linked vs self-originated, and white space -
business areas generating demand with no agents behind them.

**Data coverage:** per field, how complete it is and which metric it blocks - so
an unpopulated source field becomes a governance to-do rather than a blank chart.

### Honesty rules

The dashboard reports what the data can support, and says so when it cannot:

- coverage is declared on any metric measured on part of the data;
- under-dated completions report **not measurable** rather than 0/wk;
- future-dated go-lives are plans, excluded from activity and flow;
- a blank status stays `Unknown` and is never backfilled to a real state;
- initiative progress is **derived** from linked delivery work, never transcribed;
- no trend arrow is ever shown that history cannot support.

Run `python scripts/verify.py` to assert these hold (23 checks).

## Design

Inspired by two references: the team's Medtronic EHS Product Risk Mapper app
(native-Streamlit-theming-first, minimal custom CSS) and modern SaaS dashboard
aesthetics. Colors, fonts, radii, and borders all come from
[`.streamlit/config.toml`](.streamlit/config.toml) - a light main theme paired
with a dark navy `[theme.sidebar]` (colors sampled directly from
`assets/Medtronic_wordmark.jpg`, `#140E4A`). `common/theme.py` injects custom
CSS for exactly one thing native theming can't express: keeping the sidebar's
collapse/expand arrow always visible instead of hover-only. The logo itself
uses native `st.logo()`.

Icons are Google Material Symbols (`:material/icon_name:`) throughout -
native to Streamlit's markdown/badge/button/metric rendering, no custom SVG
and no network calls. KPI cards are native `st.metric(..., border=True,
height="stretch")` inside `st.container(horizontal=True)` rows, so every card
in a row is exactly the same height regardless of label length. Status
indicators use `st.badge` / inline `:color-badge[]` markdown instead of
custom HTML pills.

See [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) for the full set of tokens, component
patterns, and conventions (navigation, drill-down, chat panel) this app follows.
