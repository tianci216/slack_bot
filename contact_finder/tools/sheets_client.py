"""
Google Sheets client for appending contact data.

Uses gspread with service account credentials.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SHEET_HEADERS = [
    "Company", "Domain", "Contact Name", "Title",
    "Email", "Email Status", "LinkedIn", "Phone", "Source",
]


def _get_worksheet():
    """Get or create the worksheet, initializing headers if needed."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not creds_path or not sheet_id:
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(sheet_id)

    # Use first worksheet or create one named "Contacts"
    try:
        worksheet = spreadsheet.worksheet("Contacts")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title="Contacts", rows=1000, cols=len(SHEET_HEADERS)
        )
        worksheet.append_row(SHEET_HEADERS, value_input_option="RAW")

    # Ensure headers exist
    first_row = worksheet.row_values(1)
    if not first_row:
        worksheet.append_row(SHEET_HEADERS, value_input_option="RAW")

    return worksheet


def check_duplicates(emails: list[str]) -> set[str]:
    """
    Check which emails already exist in the sheet.

    Args:
        emails: List of email addresses to check

    Returns:
        Set of emails that already exist in the sheet
    """
    try:
        worksheet = _get_worksheet()
        if not worksheet:
            return set()

        # Email is in column 5 (index 4, but gspread is 1-indexed → col 5)
        existing_emails = worksheet.col_values(5)
        existing_set = {e.lower().strip() for e in existing_emails if e}

        return {e for e in emails if e and e.lower().strip() in existing_set}

    except Exception as e:
        logger.error(f"Error checking duplicates in sheet: {e}")
        return set()


def append_contacts_batch(rows: list[list[str]]) -> dict:
    """
    Append multiple contact rows to the sheet in a single batch.

    Args:
        rows: List of row data (each matching SHEET_HEADERS order)

    Returns:
        {"added": count} or {"error": "..."}
    """
    if not rows:
        return {"added": 0}

    try:
        worksheet = _get_worksheet()
        if not worksheet:
            return {"error": "Google Sheets not configured"}

        worksheet.append_rows(rows, value_input_option="RAW")
        return {"added": len(rows)}

    except Exception as e:
        logger.error(f"Error appending to sheet: {e}")
        return {"error": f"Sheet append failed: {e}"}


def is_configured() -> bool:
    """Check if Google Sheets credentials are available."""
    return bool(os.getenv("GOOGLE_CREDENTIALS_PATH") and os.getenv("GOOGLE_SHEET_ID"))
