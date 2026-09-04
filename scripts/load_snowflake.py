"""
Admin/one-time script: parse data/raw/*.csv and load the normalized tables
into real Snowflake tables (for Streamlit-in-Snowflake deployment).

Run this with a role that has USAGE/CREATE on the target database & schema,
e.g. the role that ran sql/snowflake_setup.sql.

Required environment variables:
  SNOWFLAKE_ACCOUNT     e.g. MDTPLC-AWSUSE1P1
  SNOWFLAKE_USER        e.g. MS68@MEDTRONIC.COM
  SNOWFLAKE_AUTHENTICATOR  (default: externalbrowser)  OR SNOWFLAKE_PASSWORD
  SNOWFLAKE_ROLE        (default: PUBLIC - override with a role that can write)
  SNOWFLAKE_WAREHOUSE   (default: PM_AGENT_WH)
  SNOWFLAKE_DATABASE    (default: PM_AGENT)
  SNOWFLAKE_SCHEMA      (default: PUBLIC)

Usage:  python scripts/load_snowflake.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.etl import discover_and_load  # noqa: E402


def _connection_params() -> dict:
    params = {
        "account": os.environ.get("SNOWFLAKE_ACCOUNT", "MDTPLC-AWSUSE1P1"),
        "user": os.environ.get("SNOWFLAKE_USER", "MS68@MEDTRONIC.COM"),
        "role": os.environ.get("SNOWFLAKE_ROLE", "PUBLIC"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "PM_AGENT_WH"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "PM_AGENT"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    }
    if os.environ.get("SNOWFLAKE_PASSWORD"):
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    else:
        params["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
    return params


def main() -> None:
    import snowflake.connector
    from snowflake.connector.pandas_tools import write_pandas

    result = discover_and_load()
    tables = {
        # PROGRAMS and WORK_ITEMS first: they are the portfolio spine every
        # metric reads from, and the source-specific tables only feed drill-downs.
        "PROGRAMS": result.programs,
        "WORK_ITEMS": result.work_items,
        "ISSUES": result.issues,
        "BOARD_ITEMS": result.board_items,
        "DEMANDS": result.demands,
        "GENERIC_ITEMS": result.generic_items,
        "PROGRAMS_META": result.programs_meta,
    }

    params = _connection_params()
    print(f"Connecting to {params['account']} as {params['user']} (role={params['role']})...")
    conn = snowflake.connector.connect(**params)
    try:
        for name, df in tables.items():
            frame = df.copy()
            for col in frame.columns:
                if str(frame[col].dtype).startswith("datetime"):
                    frame[col] = frame[col].astype(str)
            success, nchunks, nrows, _ = write_pandas(
                conn, frame, name,
                database=params["database"], schema=params["schema"],
                auto_create_table=True, overwrite=True, quote_identifiers=False,
            )
            print(f"{name}: success={success} rows={nrows}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
