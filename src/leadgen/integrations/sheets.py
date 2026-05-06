"""Google Sheets sink — appends enriched leads as rows."""
from __future__ import annotations

import json
import logging
from typing import Any

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


def _get_client():
    """Return an authenticated gspread client or None if not configured."""
    creds_json = get_settings().google_sheets_service_account_json
    if not creds_json:
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        creds_data = json.loads(creds_json)
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
        return gspread.authorize(creds)
    except Exception:
        logger.warning("sheets: failed to create gspread client", exc_info=True)
        return None


_HEADERS = [
    "Name", "Category", "Address", "Phone", "Website",
    "Rating", "Reviews", "Score", "Tags", "Email", "Status",
]


async def append_leads_to_sheet(
    spreadsheet_id: str,
    leads: list[dict[str, Any]],
) -> int:
    """Append *leads* to the first sheet of *spreadsheet_id*.

    Returns the number of rows appended. Errors are logged, never raised.
    """
    if not spreadsheet_id or not leads:
        return 0

    client = _get_client()
    if client is None:
        return 0

    try:
        import asyncio

        sh = await asyncio.to_thread(client.open_by_key, spreadsheet_id)
        ws = sh.sheet1

        # Ensure header row
        existing = await asyncio.to_thread(ws.row_values, 1)
        if not existing:
            await asyncio.to_thread(ws.append_row, _HEADERS)

        rows = []
        for lead in leads:
            meta = lead.get("website_meta") or {}
            emails = meta.get("emails") or []
            tags = lead.get("tags") or []
            rows.append([
                lead.get("name", ""),
                lead.get("category", ""),
                lead.get("address", ""),
                lead.get("phone", ""),
                lead.get("website", ""),
                lead.get("rating", ""),
                lead.get("reviews_count", ""),
                lead.get("score_ai", ""),
                ", ".join(tags),
                emails[0] if emails else "",
                lead.get("lead_status", "new"),
            ])

        await asyncio.to_thread(ws.append_rows, rows)
        logger.info("sheets: appended %d rows to %s", len(rows), spreadsheet_id)
        return len(rows)

    except Exception:
        logger.warning("sheets: append failed spreadsheet_id=%s", spreadsheet_id, exc_info=True)
        return 0
