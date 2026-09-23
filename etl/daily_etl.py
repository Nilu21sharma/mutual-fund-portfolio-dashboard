"""
Daily update  (Step 6)
======================
What this file does:
    Keeps NAVHistory up to date for all active funds, in 2 parts:

    Part 1 - catch up (mfapi.in)
        Fills any missing past days, e.g. if your PC was off for a week.
        mfapi.in is usually 2-3 days behind, so it can't give the latest day.

    Part 2 - latest NAV (AMFI)
        Adds the most recent NAV from AMFI's daily file (same as Step 2).

    Both parts only insert missing days, so running it twice is harmless.
    Messages go to the screen AND to logs\\daily_etl_YYYYMMDD.log

How to run:
    By hand :  .venv\\Scripts\\python.exe etl\\daily_etl.py
    Daily   :  see scripts\\schedule_daily_etl.ps1 (Windows Task Scheduler)
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from amfi_client import get_latest_nav
from backfill_history import backfill
from db import get_connection


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
LOG_FOLDER = Path(__file__).resolve().parent.parent / "logs"

log = logging.getLogger("daily_etl")


# ---------------------------------------------------------------
# Functions
# ---------------------------------------------------------------
def setup_logging():
    """Send log messages to the screen AND to today's log file. Returns the log file path."""
    LOG_FOLDER.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    log_file = LOG_FOLDER / f"daily_etl_{today}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),                   # screen
            logging.FileHandler(log_file, encoding="utf-8"),     # file
        ],
    )
    return log_file


def load_latest_amfi_nav():
    """Insert AMFI's latest NAV for every active fund.
    Returns two numbers: (rows inserted, funds already up to date)."""

    # STEP 1: download today's AMFI data
    all_schemes = get_latest_nav()
    all_schemes = all_schemes.set_index("SchemeCode")
    log.info(f"AMFI file: {len(all_schemes):,} schemes, latest date {all_schemes['NAVDate'].max()}")

    inserted = 0
    already_up_to_date = 0

    with get_connection() as conn:
        cursor = conn.cursor()

        # STEP 2: get our active funds
        cursor.execute("SELECT FundID, SchemeCode, SchemeName FROM dbo.FundMaster WHERE IsActive = 1")
        funds = cursor.fetchall()

        for fund_id, scheme_code, scheme_name in funds:

            # STEP 3: find this fund in the AMFI data
            if scheme_code not in all_schemes.index:
                log.warning(f"{scheme_code} {scheme_name}: not in today's AMFI file (scheme closed or merged?)")
                continue

            nav_date = all_schemes.at[scheme_code, "NAVDate"]
            nav = float(all_schemes.at[scheme_code, "NAV"])

            # STEP 4: skip if we already have this date
            cursor.execute("SELECT 1 FROM dbo.NAVHistory WHERE FundID = ? AND NAVDate = ?", fund_id, nav_date)
            if cursor.fetchone():
                already_up_to_date += 1
                continue

            # STEP 5: insert the new NAV
            cursor.execute(
                "INSERT INTO dbo.NAVHistory (FundID, NAVDate, NAV) VALUES (?, ?, ?)",
                fund_id, nav_date, nav,
            )
            inserted += 1
            log.info(f"{scheme_code} {scheme_name}: {nav_date} NAV {nav:.4f} added")

        # STEP 6: save
        conn.commit()

    return inserted, already_up_to_date


def main():
    log_file = setup_logging()
    start_time = time.time()
    everything_ok = True

    log.info("===== Daily ETL started =====")

    # PART 1: catch up missing days from mfapi.in
    log.info("--- Part 1: catch up missing days (mfapi.in) ---")
    try:
        rows_added, funds_failed = backfill()
        log.info(f"Catch-up: {rows_added:,} rows added, {funds_failed} fund(s) failed")
        if funds_failed > 0:
            everything_ok = False
    except Exception:
        log.exception("Catch-up step crashed")      # also writes the full error details
        everything_ok = False

    # PART 2: latest NAV from AMFI
    log.info("--- Part 2: latest NAV (AMFI) ---")
    try:
        inserted, already_up_to_date = load_latest_amfi_nav()
        log.info(f"AMFI: {inserted} added, {already_up_to_date} already up to date")
    except Exception:
        log.exception("AMFI step crashed")
        everything_ok = False

    # Finish
    seconds = time.time() - start_time
    if everything_ok:
        log.info(f"===== Daily ETL finished OK in {seconds:.1f}s =====")
    else:
        log.info(f"===== Daily ETL finished WITH ERRORS in {seconds:.1f}s =====")
    log.info(f"Log file: {log_file}")

    # Exit code 0 = success, 1 = failed. Task Scheduler shows this as "Last Run Result".
    if everything_ok:
        return 0
    return 1


# ---------------------------------------------------------------
# Runs only when you start this file directly
# ---------------------------------------------------------------
if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
