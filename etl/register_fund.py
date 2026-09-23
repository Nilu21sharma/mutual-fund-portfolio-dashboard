"""
Find your funds and add them to FundMaster  (Step 3)
===================================================
What this file does:
    1. --search  : find a fund's SchemeCode by typing part of its name
    2. --add     : add one or more funds to the FundMaster table
    3. --list    : show the funds you are tracking

How to run:
    .venv\\Scripts\\python.exe etl\\register_fund.py --search "parag parikh flexi"
    .venv\\Scripts\\python.exe etl\\register_fund.py --add 122639 118989
    .venv\\Scripts\\python.exe etl\\register_fund.py --add 122639 --threshold -5
    .venv\\Scripts\\python.exe etl\\register_fund.py --list

About --threshold:
    The dashboard shows "BUY" when a fund's NAV has fallen this many %
    below its month-start NAV. Default is -3 (3% below).
"""

import argparse

from amfi_client import get_latest_nav
from db import get_connection, query_to_dataframe


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
DEFAULT_THRESHOLD = -3.0     # buy signal when NAV is 3% below month-start
MAX_SEARCH_RESULTS = 30      # don't flood the screen


# ---------------------------------------------------------------
# 1. Search
# ---------------------------------------------------------------
def search_funds(search_text):
    """Print every scheme whose name contains ALL the words you typed."""

    # STEP 1: download today's list of all schemes
    all_schemes = get_latest_nav()

    # STEP 2: keep only names that contain every word (upper/lower case doesn't matter)
    matches = all_schemes
    for word in search_text.lower().split():
        name_has_word = matches["SchemeName"].str.lower().str.contains(word, regex=False)
        matches = matches[name_has_word]

    # STEP 3: show the result
    if len(matches) == 0:
        print(f'No scheme found for "{search_text}". Try fewer or different words.')
        return

    print(f'{len(matches)} match(es) for "{search_text}"')
    if len(matches) > MAX_SEARCH_RESULTS:
        print(f"(showing the first {MAX_SEARCH_RESULTS})")

    columns_to_show = ["SchemeCode", "SchemeName", "Plan", "Option", "AMC", "NAV"]
    print(matches[columns_to_show].head(MAX_SEARCH_RESULTS).to_string(index=False))
    print("\nTip: most investors hold the Direct Plan + Growth version. Check your account statement.")


# ---------------------------------------------------------------
# 2. Add
# ---------------------------------------------------------------
def add_funds(scheme_codes, threshold):
    """Look up each SchemeCode in today's AMFI data and insert it into FundMaster."""

    # STEP 1: download today's list of all schemes, indexed by SchemeCode for quick lookup
    all_schemes = get_latest_nav()
    all_schemes = all_schemes.set_index("SchemeCode")

    with get_connection() as conn:
        cursor = conn.cursor()

        for code in scheme_codes:

            # STEP 2: does this code exist at AMFI?
            if code not in all_schemes.index:
                print(f"[SKIP]   {code}: not found in today's AMFI file - check the code with --search")
                continue

            # STEP 3: is it already in FundMaster?
            cursor.execute("SELECT FundID FROM dbo.FundMaster WHERE SchemeCode = ?", code)
            already_there = cursor.fetchone()
            if already_there:
                print(f"[EXISTS] {code}: already in FundMaster")
                continue

            # STEP 4: insert the fund
            fund = all_schemes.loc[code]
            cursor.execute(
                """
                INSERT INTO dbo.FundMaster
                    (SchemeCode, SchemeName, AMC, Category, PlanType, OptionType,
                     SchemeType, ISIN, BuyThresholdPct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                code,
                fund["SchemeName"],
                fund["AMC"],
                fund["Category"],
                fund["Plan"],
                fund["Option"],
                fund["SchemeType"],
                fund["ISINGrowth"],
                threshold,
            )
            print(f"[ADDED]  {code}: {fund['SchemeName']} - {fund['Plan']} - {fund['Option']}")

        # STEP 5: save all inserts
        conn.commit()


# ---------------------------------------------------------------
# 3. List
# ---------------------------------------------------------------
def list_funds():
    """Show everything in FundMaster."""
    funds = query_to_dataframe(
        """
        SELECT FundID, SchemeCode, SchemeName, PlanType, OptionType, AMC, BuyThresholdPct, IsActive
        FROM dbo.FundMaster
        ORDER BY FundID
        """
    )

    if len(funds) == 0:
        print("FundMaster is empty. Add funds with --add <SchemeCode>.")
    else:
        print(funds.to_string(index=False))


# ---------------------------------------------------------------
# Runs only when you start this file directly
# ---------------------------------------------------------------
if __name__ == "__main__":

    # Read the options you typed after the script name
    parser = argparse.ArgumentParser(description="Search for and register mutual funds.")
    parser.add_argument("--search", metavar="TEXT", help="find schemes by name")
    parser.add_argument("--add", metavar="CODE", type=int, nargs="+", help="add fund(s) by SchemeCode")
    parser.add_argument("--list", action="store_true", help="show tracked funds")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="buy-signal threshold in %% (default -3)")
    args = parser.parse_args()

    # Do what was asked
    if args.search:
        search_funds(args.search)
    elif args.add:
        add_funds(args.add, args.threshold)
    elif args.list:
        list_funds()
    else:
        parser.print_help()
