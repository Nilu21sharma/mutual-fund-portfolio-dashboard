"""
Download today's NAV from AMFI  (Step 2)
========================================
What this file does:
    Downloads the latest NAV of EVERY mutual fund scheme from AMFI
    and turns it into a clean table (pandas DataFrame).

How the AMFI file looks:
    It is NOT a normal CSV. It mixes 3 kinds of lines:

    Open Ended Schemes(Equity Scheme - Large Cap Fund)      <- category heading
    HDFC Mutual Fund                                        <- fund house (AMC) heading
    119018;INF179K01XQ0;-;HDFC Large Cap Fund;Direct Plan;Growth Option;1234.5678;23-Sep-2026
                                                            <- scheme row: 8 values split by ";"

    So we read the file line by line. When we see a heading we remember it,
    and we attach the remembered category + AMC to every scheme row below it.

How to run:
    .venv\\Scripts\\python.exe etl\\amfi_client.py
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from http_utils import get_with_retry


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------

# www.amfiindia.com does not respond from our network,
# so we use AMFI's "portal" website, which serves the same file.
NAV_ALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"

# Folder where we save a copy of the downloaded data (ignored by git)
RAW_DATA_FOLDER = Path(__file__).resolve().parent.parent / "data" / "raw"


# ---------------------------------------------------------------
# Functions
# ---------------------------------------------------------------

def download_nav_text():
    """Download the AMFI file and return it as one big piece of text."""
    response = get_with_retry(NAV_ALL_URL, timeout=60)   # the file is ~1.5 MB, so allow more time

    # Tell Python the file is UTF-8, otherwise names like "Children's" look broken
    response.encoding = "utf-8"

    return response.text


def is_category_line(line):
    """True for heading lines like 'Open Ended Schemes(Equity Scheme - Large Cap Fund)'."""
    if line.startswith("Open Ended Schemes"):
        return True
    if line.startswith("Close Ended Schemes"):
        return True
    if line.startswith("Interval Fund Schemes"):
        return True
    return False


def dash_to_none(value):
    """AMFI writes '-' when there is no value. We store that as None (empty)."""
    value = value.strip()
    if value == "-" or value == "":
        return None
    return value


def parse_nav_text(text):
    """Turn the raw AMFI text into a table with one row per scheme."""

    rows = []   # we collect one dictionary per scheme in this list

    # These remember the last headings we saw while reading from top to bottom
    current_scheme_type = None   # e.g. "Open Ended Schemes"
    current_category = None      # e.g. "Equity Scheme - Large Cap Fund"
    current_amc = None           # e.g. "HDFC Mutual Fund"

    for line in text.splitlines():
        line = line.strip()

        # Skip empty lines and the column-header line at the top
        if line == "" or line.startswith("Scheme Code"):
            continue

        # Kind 1: category heading  ->  remember scheme type + category
        if is_category_line(line):
            # "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
            #  text before "(" = scheme type, text inside ( ) = category
            bracket_position = line.index("(")
            current_scheme_type = line[:bracket_position].strip()
            current_category = line[bracket_position + 1:].rstrip(")").strip()
            continue

        # Kind 2: fund house heading (a text line without ";")  ->  remember AMC
        if ";" not in line:
            current_amc = line
            continue

        # Kind 3: scheme row  ->  split into its 8 values
        parts = line.split(";")
        if len(parts) != 8:
            continue   # broken line, ignore it

        scheme_code = parts[0].strip()
        if not scheme_code.isdigit():
            continue   # not a real scheme row, ignore it

        rows.append({
            "SchemeCode": int(scheme_code),
            "ISINGrowth": dash_to_none(parts[1]),
            "ISINReinvest": dash_to_none(parts[2]),
            "SchemeName": parts[3].strip(),
            "Plan": parts[4].strip(),
            "Option": parts[5].strip(),
            "NAV": parts[6].strip(),
            "NAVDate": parts[7].strip(),
            "AMC": current_amc,
            "SchemeType": current_scheme_type,
            "Category": current_category,
        })

    # Turn the list of dictionaries into a table
    nav_table = pd.DataFrame(rows)

    # NAV: text -> number. Values like "N.A." become empty (NaN).
    nav_table["NAV"] = pd.to_numeric(nav_table["NAV"], errors="coerce")

    # NAVDate: text "23-Sep-2026" -> real date
    nav_table["NAVDate"] = pd.to_datetime(nav_table["NAVDate"], format="%d-%b-%Y", errors="coerce")
    nav_table["NAVDate"] = nav_table["NAVDate"].dt.date

    # Remove rows with no NAV / no date, or a NAV of 0
    nav_table = nav_table.dropna(subset=["NAV", "NAVDate"])
    nav_table = nav_table[nav_table["NAV"] > 0]
    nav_table = nav_table.reset_index(drop=True)

    return nav_table


def get_latest_nav():
    """Download + clean in one call. Other scripts use this function."""
    text = download_nav_text()
    nav_table = parse_nav_text(text)
    return nav_table


# ---------------------------------------------------------------
# Runs only when you start this file directly
# ---------------------------------------------------------------
if __name__ == "__main__":

    # STEP 1: download and clean the data
    print(f"Downloading NAV file from {NAV_ALL_URL} ...")
    nav_table = get_latest_nav()

    # STEP 2: print a short summary
    print(f"Schemes with a valid NAV : {len(nav_table):,}")
    print(f"Fund houses (AMCs)       : {nav_table['AMC'].nunique()}")
    print(f"Categories               : {nav_table['Category'].nunique()}")
    print(f"Latest NAV date          : {nav_table['NAVDate'].max()}")

    # STEP 3: show the first 5 rows
    print("\nFirst 5 rows:")
    columns_to_show = ["SchemeCode", "SchemeName", "Plan", "Option", "AMC", "NAV", "NAVDate"]
    print(nav_table[columns_to_show].head().to_string(index=False))

    # STEP 4: save a CSV copy so you can open it in Excel
    RAW_DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    output_file = RAW_DATA_FOLDER / f"nav_{today}.csv"
    nav_table.to_csv(output_file, index=False)
    print(f"\nSaved to {output_file}")
