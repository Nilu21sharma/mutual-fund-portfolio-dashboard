"""
Download helper with automatic retries
======================================
What this file does:
    Free websites (AMFI, mfapi.in) sometimes time out for a moment.
    Instead of failing straight away, we wait a few seconds and try again.

    Attempt 1 fails -> wait 5 seconds  -> attempt 2
    Attempt 2 fails -> wait 10 seconds -> attempt 3
    Attempt 3 fails -> give up and raise the error
"""

import logging
import time

import requests

log = logging.getLogger(__name__)


def get_with_retry(url, attempts=3, timeout=30):
    """Download a web page / file and return the response."""

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=timeout)

            # Turn "404 Not Found" / "500 Server Error" into a Python error
            response.raise_for_status()

            # Success - hand the response back
            return response

        except requests.RequestException as error:
            # Was this the last attempt? Then give up.
            if attempt == attempts:
                raise

            wait_seconds = 5 * attempt
            error_name = type(error).__name__
            log.warning(f"    attempt {attempt} failed ({error_name}), retrying in {wait_seconds}s ...")
            time.sleep(wait_seconds)
