-- =====================================================================
-- Program Command Center - Snowflake provisioning
-- Run as a role with CREATE DATABASE / CREATE WAREHOUSE / CREATE STREAMLIT
-- privileges (the PUBLIC role from the app's default config normally does
-- NOT have these - use ACCOUNTADMIN or a dedicated admin role once, then
-- hand out USAGE grants to whoever needs to use the app).
-- =====================================================================

-- 1. Core objects -----------------------------------------------------
CREATE DATABASE IF NOT EXISTS PM_AGENT
    COMMENT = 'Program Command Center - demand/program tracking dashboard';

CREATE SCHEMA IF NOT EXISTS PM_AGENT.PUBLIC;

CREATE WAREHOUSE IF NOT EXISTS PM_AGENT_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Warehouse for the Program Command Center Streamlit app + Cortex calls';

USE DATABASE PM_AGENT;
USE SCHEMA PUBLIC;
USE WAREHOUSE PM_AGENT_WH;

-- 2. Normalized tables (mirrors common/etl.py output) ------------------
CREATE TABLE IF NOT EXISTS ISSUES (
    issue_key               STRING,
    issue_id                STRING,
    summary                 STRING,
    issue_type              STRING,
    status                  STRING,
    status_category         STRING,
    project_key             STRING,
    project_name            STRING,
    priority                STRING,
    resolution              STRING,
    assignee                STRING,
    reporter                STRING,
    creator                 STRING,
    parent_key              STRING,
    parent_summary          STRING,
    team_name               STRING,
    created                 TIMESTAMP_NTZ,
    updated                 TIMESTAMP_NTZ,
    resolved                TIMESTAMP_NTZ,
    due_date                TIMESTAMP_NTZ,
    solution_architect      STRING,
    story_points            FLOAT,
    sprint                  STRING,
    domain                  STRING,
    original_estimate_sec   FLOAT,
    remaining_estimate_sec  FLOAT,
    time_spent_sec          FLOAT,
    estimate_hours          FLOAT,
    source_file             STRING,
    program_name            STRING
);

CREATE TABLE IF NOT EXISTS BOARD_ITEMS (
    item_key                STRING,
    name                    STRING,
    description             STRING,
    owner                   STRING,
    domain                  STRING,
    sub_domain              STRING,
    status                  STRING,
    origin                  STRING,
    demand_intake_number    STRING,
    platform                STRING,
    link                    STRING,
    eta                     STRING,
    comment                 STRING,
    source_file             STRING,
    program_name            STRING
);

CREATE TABLE IF NOT EXISTS GENERIC_ITEMS (
    name                    STRING,
    status                  STRING,
    owner                   STRING,
    category                STRING,
    raw_row_json            STRING,
    source_file             STRING,
    program_name            STRING
);

CREATE TABLE IF NOT EXISTS PROGRAMS_META (
    source_file             STRING,
    kind                    STRING,
    row_count               NUMBER,
    detail                  STRING
);

-- The portfolio spine ---------------------------------------------------
-- PROGRAMS is the single registry: a strategic initiative is a row here with
-- IS_STRATEGIC = TRUE, not a table of its own. That is what stops the two ever
-- disagreeing, or the same work being counted twice.
CREATE TABLE IF NOT EXISTS PROGRAMS (
    program_id                  STRING,
    name                        STRING,
    is_strategic                BOOLEAN,
    parent_program_id           STRING,
    portfolio                   STRING,
    domain                      STRING,
    executive_sponsor           STRING,
    program_owner               STRING,
    delivery_lead               STRING,
    phase                       STRING,
    start_date                  STRING,
    target_date                 STRING,
    target_quarter              STRING,
    budget_usd                  FLOAT,
    spent_usd                   FLOAT,
    source_system               STRING,
    source_files                STRING,
    jira_project_keys           STRING,
    demand_assignment_groups    STRING,
    agent_sub_domains           STRING,
    key_risks                   STRING
);

-- WORK_ITEMS is one normalized row per unit of work, whatever tool it came
-- from, so every metric is computed once over one table. STATUS_CATEGORY is the
-- shared taxonomy: To Do / In Progress / Blocked / Done / Cancelled / Unknown.
CREATE TABLE IF NOT EXISTS WORK_ITEMS (
    program_id          STRING,
    item_key            STRING,
    title               STRING,
    item_type           STRING,
    workstream          STRING,
    domain              STRING,
    owner               STRING,
    status_raw          STRING,
    status_category     STRING,
    priority            STRING,
    created             STRING,
    started             STRING,
    due_date            STRING,
    completed           STRING,
    updated             STRING,
    effort_hours        FLOAT,
    is_leaf             BOOLEAN,
    source_system       STRING,
    source_file         STRING
);

-- Only for values that cannot be recovered by rewinding item dates (blocked
-- counts, health bands). Completion and throughput history is derived on the
-- fly - see common/snapshots.py - and needs nothing stored.
CREATE TABLE IF NOT EXISTS SNAPSHOTS (
    snapshot_date       STRING,
    program_id          STRING,
    metric_key          STRING,
    value               FLOAT
);

CREATE TABLE IF NOT EXISTS DEMANDS (
    demand_key                  STRING,
    request_number              STRING,
    title                       STRING,
    description                 STRING,
    requestor                   STRING,
    request_type                STRING,
    status                      STRING,
    status_category             STRING,
    assignment_group            STRING,
    team_required               STRING,
    solution_architect          STRING,
    manager                     STRING,
    vp_leader                   STRING,
    ic_approval_status          STRING,
    resource_status             STRING,
    delay_type                  STRING,
    project_status              STRING,
    release                     STRING,
    created                     STRING,
    go_live_date                STRING,
    cancellation_date           STRING,
    development_start_date      STRING,
    estimation_approval_date    STRING,
    hours_estimate              FLOAT,
    cost_estimate_usd           FLOAT,
    program_id                  STRING,
    program_name                STRING,
    source_file                 STRING
);

-- 3. Stage for CSVs + the Streamlit app source files -------------------
CREATE STAGE IF NOT EXISTS RAW_CSV_STAGE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Drop new program CSVs here, then run scripts/load_snowflake.py or a COPY INTO';

CREATE STAGE IF NOT EXISTS APP_STAGE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Streamlit-in-Snowflake app source files (streamlit_app.py, common/, views/, environment.yml)';

-- Upload the app source files to APP_STAGE, e.g. via SnowSQL:
--   PUT file://streamlit_app.py       @PM_AGENT.PUBLIC.APP_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
--   PUT file://common/*.py            @PM_AGENT.PUBLIC.APP_STAGE/common AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
--   PUT file://views/*.py             @PM_AGENT.PUBLIC.APP_STAGE/views AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
--   PUT file://environment.yml        @PM_AGENT.PUBLIC.APP_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- ...or use Snowsight: Projects > Streamlit > + Streamlit App > "Upload files" and point at this repo folder.

-- 4. The Streamlit app object ------------------------------------------
CREATE STREAMLIT IF NOT EXISTS PROGRAM_COMMAND_CENTER
    ROOT_LOCATION = '@PM_AGENT.PUBLIC.APP_STAGE'
    MAIN_FILE = 'streamlit_app.py'
    QUERY_WAREHOUSE = 'PM_AGENT_WH'
    COMMENT = 'Manager-facing program/demand tracking dashboard with Cortex insights';

-- 5. Grants (adjust role name to whoever should access the app) --------
-- GRANT USAGE ON DATABASE PM_AGENT TO ROLE <your_role>;
-- GRANT USAGE ON SCHEMA PM_AGENT.PUBLIC TO ROLE <your_role>;
-- GRANT USAGE ON WAREHOUSE PM_AGENT_WH TO ROLE <your_role>;
-- GRANT SELECT ON ALL TABLES IN SCHEMA PM_AGENT.PUBLIC TO ROLE <your_role>;
-- GRANT USAGE ON STREAMLIT PM_AGENT.PUBLIC.PROGRAM_COMMAND_CENTER TO ROLE <your_role>;
-- Cortex functions run under SNOWFLAKE.CORTEX and generally just need the
-- account to have Cortex enabled in this region; no extra grant beyond
-- warehouse USAGE is normally required for SNOWFLAKE.CORTEX.COMPLETE.
