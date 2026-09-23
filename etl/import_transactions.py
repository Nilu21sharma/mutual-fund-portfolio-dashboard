"""
Load your buys and sells from a CSV file  (Step 5)
=================================================
What this file does:
    Reads your transactions from a CSV file and saves them
    in the Transactions table.

CSV columns (see data\\sample_transactions.csv):
    TxnDate     date, format YYYY-MM-DD                       (required)
    SchemeCode  AMFI code - fund must be added in Step 3      (required)
    TxnType     BUY or SELL                                   (required)
    Amount      rupees invested or redeemed                   (required)
    NAV         leave blank -> looked up in NAVHistory
    Units       leave blank -> Amount / NAV
                (if your statement shows exact units, type them - more accurate)
    Notes       anything you like                             (optional)

    Blank NAV on a holiday/weekend? The fund house uses the NEXT
    working day's NAV, so we do the same.

Safety rules:
    - Every row is checked first. If ANY row has a problem, NOTHING is saved.
    - A row with the same fund + date + type + amount as a saved one is skipped,
      so importing the same file twice does not double your investments.
    - You cannot sell more units than you hold.

How to run:
    .venv\\Scripts\\python.exe etl\\import_transactions.py data\\my_transactions.csv
    .venv\\Scripts\\python.exe etl\\import_transactions.py --list
"""

import argparse
from datetime import datetime

import pandas as pd

from db import get_connection, query_to_dataframe


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
REQUIRED_COLUMNS = ["TxnDate", "SchemeCode", "TxnType", "Amount"]
OPTIONAL_COLUMNS = ["NAV", "Units", "Notes"]


# ---------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------
def to_number(text):
    """'5000' -> 5000.0   |   'abc' or '' -> None"""
    try:
        return float(text)
    except ValueError:
        return None


def to_date(text):
    """'2024-01-31' -> date(2024, 1, 31)   |   anything else -> None"""
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def find_nav(cursor, fund_id, txn_date):
    """Return (nav_date, nav) of the first NAV on or after txn_date, or None if there is none."""
    cursor.execute(
        """
        SELECT TOP 1 NAVDate, NAV
        FROM dbo.NAVHistory
        WHERE FundID = ? AND NAVDate >= ?
        ORDER BY NAVDate
        """,
        fund_id, txn_date,
    )
    return cursor.fetchone()


def units_held(cursor, fund_id, on_date):
    """How many units of this fund do you hold on this date? (all buys minus all sells)"""
    cursor.execute(
        """
        SELECT SUM(CASE WHEN TxnType = 'BUY' THEN Units ELSE -Units END)
        FROM dbo.Transactions
        WHERE FundID = ? AND TxnDate <= ?
        """,
        fund_id, on_date,
    )
    total = cursor.fetchone()[0]
    if total is None:
        return 0.0
    return float(total)


def already_saved(cursor, row):
    """True if the same fund + date + type + amount is already in Transactions."""
    cursor.execute(
        """
        SELECT 1 FROM dbo.Transactions
        WHERE FundID = ? AND TxnDate = ? AND TxnType = ? AND Amount = ?
        """,
        row["fund_id"], row["date"], row["type"], row["amount"],
    )
    return cursor.fetchone() is not None


# ---------------------------------------------------------------
# Check one CSV row
# ---------------------------------------------------------------
def check_row(csv_row, line_number, fund_ids, cursor):
    """Check one CSV row.
    Returns (clean_row, None) if it is OK, or (None, "error message") if not."""

    where = f"Line {line_number}"

    # Check 1: date
    txn_date = to_date(csv_row["TxnDate"])
    if txn_date is None:
        return None, f"{where}: TxnDate '{csv_row['TxnDate']}' must look like 2024-01-31"

    # Check 2: fund must be in FundMaster
    code = csv_row["SchemeCode"]
    if not code.isdigit() or int(code) not in fund_ids:
        return None, f"{where}: SchemeCode '{code}' is not in FundMaster - add it with register_fund.py --add {code}"
    fund_id = fund_ids[int(code)]

    # Check 3: BUY or SELL
    txn_type = csv_row["TxnType"].upper()
    if txn_type != "BUY" and txn_type != "SELL":
        return None, f"{where}: TxnType must be BUY or SELL, not '{csv_row['TxnType']}'"

    # Check 4: amount
    amount = to_number(csv_row["Amount"])
    if amount is None or amount <= 0:
        return None, f"{where}: Amount '{csv_row['Amount']}' must be a number above 0"

    # Check 5: NAV - use the CSV value, or look it up
    nav_note = ""
    if csv_row["NAV"] == "":
        found = find_nav(cursor, fund_id, txn_date)
        if found is None:
            return None, f"{where}: no NAV found on/after {txn_date} - run backfill_history.py, or type the NAV in the CSV"
        nav_date = found[0]
        nav = float(found[1])
        if nav_date != txn_date:
            nav_note = f" (holiday - used NAV of {nav_date})"
    else:
        nav = to_number(csv_row["NAV"])
        if nav is None or nav <= 0:
            return None, f"{where}: NAV '{csv_row['NAV']}' must be a number above 0"

    # Check 6: units - use the CSV value, or calculate Amount / NAV
    if csv_row["Units"] == "":
        units = round(amount / nav, 4)
    else:
        units = to_number(csv_row["Units"])
        if units is None or units <= 0:
            return None, f"{where}: Units '{csv_row['Units']}' must be a number above 0"

    # All checks passed
    clean_row = {
        "line": line_number,
        "fund_id": fund_id,
        "code": int(code),
        "date": txn_date,
        "type": txn_type,
        "amount": amount,
        "nav": nav,
        "units": units,
        "notes": csv_row["Notes"] or None,
        "nav_note": nav_note,
    }
    return clean_row, None


# ---------------------------------------------------------------
# Main import
# ---------------------------------------------------------------
def import_file(csv_path):

    # STEP 1: read the CSV (everything as text; we convert it ourselves)
    csv_data = pd.read_csv(csv_path, dtype=str)
    csv_data = csv_data.fillna("")
    print(f"Read {len(csv_data)} row(s) from {csv_path}")

    for column in REQUIRED_COLUMNS:
        if column not in csv_data.columns:
            print(f"CSV is missing the column '{column}'. Nothing was saved.")
            return
    for column in OPTIONAL_COLUMNS:
        if column not in csv_data.columns:
            csv_data[column] = ""

    with get_connection() as conn:
        cursor = conn.cursor()

        # STEP 2: load all registered funds as {SchemeCode: FundID}
        fund_ids = {}
        cursor.execute("SELECT FundID, SchemeCode FROM dbo.FundMaster")
        for fund_id, scheme_code in cursor.fetchall():
            fund_ids[scheme_code] = fund_id

        # STEP 3: check every row
        good_rows = []
        errors = []
        for index, csv_row in csv_data.iterrows():
            line_number = index + 2          # +2 = header line + Excel counts from 1
            for column in csv_row.index:
                csv_row[column] = csv_row[column].strip()

            clean_row, error = check_row(csv_row, line_number, fund_ids, cursor)
            if error:
                errors.append(error)
            else:
                good_rows.append(clean_row)

        # STEP 4: skip rows that are already saved
        new_rows = []
        for row in good_rows:
            if already_saved(cursor, row):
                print(f"[EXISTS] Line {row['line']}: {row['date']} {row['type']} {row['amount']:,.2f} - already saved")
            else:
                new_rows.append(row)

        # STEP 5: stop here if any row had a problem
        if errors:
            print("\nNothing was saved. Please fix these rows and run again:")
            for error in errors:
                print(f"  - {error}")
            return

        # STEP 6: insert in date order (on the same day, BUY before SELL)
        def date_then_buy_first(row):
            return (row["date"], row["type"] == "SELL")
        new_rows.sort(key=date_then_buy_first)

        messages = []
        for row in new_rows:

            # A SELL must not be bigger than the units you hold on that date
            if row["type"] == "SELL":
                held = units_held(cursor, row["fund_id"], row["date"])
                if row["units"] > held + 0.001:
                    errors.append(f"Line {row['line']}: selling {row['units']:.4f} units on {row['date']} "
                                  f"but you only hold {held:.4f}")
                    continue

            cursor.execute(
                """
                INSERT INTO dbo.Transactions (FundID, TxnDate, TxnType, Amount, NAV, Units, Notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                row["fund_id"], row["date"], row["type"], row["amount"], row["nav"], row["units"], row["notes"],
            )
            messages.append(f"[ADDED]  Line {row['line']}: {row['date']} {row['type']:4} {row['code']} "
                            f"Rs {row['amount']:,.2f} @ {row['nav']:.4f} = {row['units']:.4f} units{row['nav_note']}")

        # STEP 7: save everything, or undo everything if a SELL was too big
        if errors:
            conn.rollback()
            print("\nNothing was saved. Please fix these rows and run again:")
            for error in errors:
                print(f"  - {error}")
            return

        conn.commit()
        for message in messages:
            print(message)
        print(f"\nDone: {len(new_rows)} new transaction(s) saved.")


def list_transactions():
    """Show every saved transaction."""
    transactions = query_to_dataframe(
        """
        SELECT t.TransactionID, t.TxnDate, f.SchemeCode, f.SchemeName,
               t.TxnType, t.Amount, t.NAV, t.Units
        FROM dbo.Transactions t
        JOIN dbo.FundMaster f ON f.FundID = t.FundID
        ORDER BY t.TxnDate, t.TransactionID
        """
    )

    if len(transactions) == 0:
        print("No transactions yet.")
    else:
        print(transactions.to_string(index=False))


# ---------------------------------------------------------------
# Runs only when you start this file directly
# ---------------------------------------------------------------
if __name__ == "__main__":

    # Read the options you typed after the script name
    parser = argparse.ArgumentParser(description="Import buy/sell transactions from a CSV file.")
    parser.add_argument("csv", nargs="?", help="path to your transactions CSV")
    parser.add_argument("--list", action="store_true", help="show saved transactions")
    args = parser.parse_args()

    # Do what was asked
    if args.list:
        list_transactions()
    elif args.csv:
        import_file(args.csv)
    else:
        parser.print_help()
