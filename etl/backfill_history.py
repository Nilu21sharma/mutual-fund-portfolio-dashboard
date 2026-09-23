"""
Load past NAVs (history)  (Step 4)
=================================
What this file does:
    The AMFI file from Step 2 only has TODAY's NAV.
    For the dashboard we also need older NAVs (month-start NAV,
    NAV on the day you bought, ...).

    mfapi.in is a free website that gives the full NAV history of a fund:
        https://api.mfapi.in/mf/122639
        -> {"meta": {...}, "data": [{"date": "23-09-2026", "nav": "90.26860"}, ...]}

    We only insert dates that are NOT in NAVHistory yet,
    so it is safe to run this again at any time.

How to run:
    .venv\\Scripts\\python.exe etl\\backfill_history.py                 (all active funds)
    .venv\\Scripts\\python.exe etl\\backfill_history.py --code 122639   (one fund only)
"""

import argparse
import logging

import pandas as pd
import requests

from db import get_connection
from http_utils import get_with_retry

# log.info(...) works like print(...), but daily_etl.py can also send it to a log file
log = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
MFAPI_URL = "https://api.mfapi.in/mf/"


# ---------------------------------------------------------------
# Functions
# ---------------------------------------------------------------
def download_history(scheme_code):
    """Download the full NAV history of one fund. Returns a table with NAVDate and NAV."""

    # STEP 1: download the JSON data
    response = get_with_retry(MFAPI_URL + str(scheme_code))
    json_data = response.json()
    records = json_data.get("data", [])

    history = pd.DataFrame(records)
    if len(history) == 0:
        return pd.DataFrame(columns=["NAVDate", "NAV"])

    # STEP 2: convert text to real dates and numbers
    history["NAVDate"] = pd.to_datetime(history["date"], format="%d-%m-%Y", errors="coerce")
    history["NAVDate"] = history["NAVDate"].dt.date
    history["NAV"] = pd.to_numeric(history["nav"], errors="coerce")

    # STEP 3: remove bad rows and duplicate dates
    history = history.dropna(subset=["NAVDate", "NAV"])
    history = history[history["NAV"] > 0]
    history = history.drop_duplicates(subset="NAVDate")

    return history[["NAVDate", "NAV"]]


def get_funds_to_load(cursor, only_code):
    """Return the active funds from FundMaster (or just one, if only_code is given)."""
    if only_code is None:
        cursor.execute("SELECT FundID, SchemeCode, SchemeName FROM dbo.FundMaster WHERE IsActive = 1")
    else:
        cursor.execute(
            "SELECT FundID, SchemeCode, SchemeName FROM dbo.FundMaster WHERE IsActive = 1 AND SchemeCode = ?",
            only_code,
        )
    return cursor.fetchall()


def get_dates_already_saved(cursor, fund_id):
    """Return a set of the NAV dates we already have for this fund."""
    cursor.execute("SELECT NAVDate FROM dbo.NAVHistory WHERE FundID = ?", fund_id)

    saved_dates = set()
    for row in cursor.fetchall():
        saved_dates.add(row[0])
    return saved_dates


def backfill(only_code=None):
    """Load missing history for all active funds.
    Returns two numbers: (rows inserted, funds that failed)."""

    total_inserted = 0
    funds_failed = 0

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.fast_executemany = True   # send thousands of rows in one go (much faster)

        # STEP 1: which funds do we need history for?
        funds = get_funds_to_load(cursor, only_code)
        if len(funds) == 0:
            log.info("No matching active funds in FundMaster. Add funds first with register_fund.py --add <SchemeCode>.")
            return total_inserted, funds_failed

        for fund_id, scheme_code, scheme_name in funds:
            log.info(f"{scheme_code} {scheme_name}")

            # STEP 2: download this fund's full history
            try:
                history = download_history(scheme_code)
            except requests.RequestException as error:
                log.error(f"    [ERROR] download failed: {error}")
                funds_failed += 1
                continue

            if len(history) == 0:
                log.info("    no history returned")
                continue

            # STEP 3: keep only the dates we don't have yet
            saved_dates = get_dates_already_saved(cursor, fund_id)
            is_new_date = ~history["NAVDate"].isin(saved_dates)   # ~ means "NOT"
            new_rows = history[is_new_date]

            # STEP 4: insert the new rows
            if len(new_rows) > 0:
                rows_to_insert = []
                for nav_date, nav in zip(new_rows["NAVDate"], new_rows["NAV"]):
                    rows_to_insert.append((fund_id, nav_date, float(nav)))

                cursor.executemany(
                    "INSERT INTO dbo.NAVHistory (FundID, NAVDate, NAV) VALUES (?, ?, ?)",
                    rows_to_insert,
                )
                conn.commit()
                total_inserted += len(new_rows)

            # STEP 5: report what happened
            first_day = history["NAVDate"].min()
            last_day = history["NAVDate"].max()
            log.info(f"    {len(history):,} days available ({first_day} to {last_day}), "
                     f"{len(new_rows):,} new rows inserted")

    return total_inserted, funds_failed


# ---------------------------------------------------------------
# Runs only when you start this file directly
# ---------------------------------------------------------------
if __name__ == "__main__":

    # Show log messages on the screen
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Read the options you typed after the script name
    parser = argparse.ArgumentParser(description="Load historical NAVs from mfapi.in into NAVHistory.")
    parser.add_argument("--code", type=int, help="only this SchemeCode (default: all active funds)")
    args = parser.parse_args()

    backfill(args.code)
