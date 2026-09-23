"""
Database connection
===================
What this file does:
    Keeps the SQL Server settings in ONE place.
    Every other script imports get_connection() from here,
    so if the server name ever changes you only edit this file.
"""

import pandas as pd
import pyodbc


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------
SERVER = "NILU"
DATABASE = "MFPortfolioDB"
DRIVER = "ODBC Driver 17 for SQL Server"

# Trusted_Connection=yes means Windows Authentication (no username/password)
CONNECTION_STRING = (
    "DRIVER={" + DRIVER + "};"
    "SERVER=" + SERVER + ";"
    "DATABASE=" + DATABASE + ";"
    "Trusted_Connection=yes;"
)

# Seconds to wait for the login. Our local server is sometimes slow to answer.
LOGIN_TIMEOUT_SECONDS = 60


def get_connection():
    """Open a connection to MFPortfolioDB.

    Use it like this:
        with get_connection() as conn:
            cursor = conn.cursor()
            ...
    """
    return pyodbc.connect(CONNECTION_STRING, timeout=LOGIN_TIMEOUT_SECONDS)


def query_to_dataframe(sql, params=()):
    """Run a SELECT query and return the result as a pandas table (DataFrame)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)

        # cursor.description has one entry per column; the first item is the column name
        column_names = []
        for column in cursor.description:
            column_names.append(column[0])

        rows = []
        for row in cursor.fetchall():
            rows.append(tuple(row))

    return pd.DataFrame(rows, columns=column_names)
