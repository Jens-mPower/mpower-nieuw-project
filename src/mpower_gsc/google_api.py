"""Dunne laag rond de Google Search Console- en Sheets-API (alleen lezen)."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]

DIMENSIONS = {"query", "page", "country", "device", "date", "searchAppearance"}
SEARCH_TYPES = {"web", "image", "video", "news", "discover", "googleNews"}
FILTER_OPERATORS = {
    "contains", "equals", "notContains", "notEquals", "includingRegex", "excludingRegex",
}
MAX_ROW_LIMIT = 25000

# De meest recente dagen in Search Console zijn vaak nog niet definitief,
# daarom eindigt de standaardperiode een paar dagen voor vandaag.
DEFAULT_END_OFFSET_DAYS = 3
DEFAULT_PERIOD_DAYS = 28


class ConfigError(Exception):
    """Er ontbreekt configuratie (credentials of klantenlijst)."""


def load_credentials():
    """Service-account-credentials uit een bestand of uit een JSON-string."""
    from google.oauth2 import service_account

    raw_json = os.getenv("GSC_SERVICE_ACCOUNT_JSON")
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if raw_json:
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ConfigError("GSC_SERVICE_ACCOUNT_JSON bevat geen geldige JSON.") from exc
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    if path:
        if not os.path.exists(path):
            raise ConfigError(f"Het sleutelbestand '{path}' bestaat niet op deze machine.")
        return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    raise ConfigError(
        "Geen credentials gevonden. Zet GOOGLE_APPLICATION_CREDENTIALS (pad naar de JSON-sleutel) "
        "of GSC_SERVICE_ACCOUNT_JSON (de inhoud van de sleutel)."
    )


def build_services(credentials) -> tuple[Any, Any]:
    from googleapiclient.discovery import build

    gsc = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return gsc, sheets


def read_sheet_rows(sheets, spreadsheet_id: str, cell_range: str) -> list[list[str]]:
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=cell_range
    ).execute()
    return result.get("values", [])


def default_period(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    end = today - timedelta(days=DEFAULT_END_OFFSET_DAYS)
    start = end - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    return start.isoformat(), end.isoformat()


def build_query_body(
    start_date: str | None,
    end_date: str | None,
    dimensions: list[str],
    row_limit: int,
    start_row: int,
    search_type: str,
    filters: list[dict] | None,
    today: date | None = None,
) -> dict:
    default_start, default_end = default_period(today)
    start = start_date or default_start
    end = end_date or default_end
    for label, value in (("start_date", start), ("end_date", end)):
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} moet de vorm JJJJ-MM-DD hebben, kreeg '{value}'.") from exc
    if start > end:
        raise ValueError("start_date ligt na end_date.")

    unknown = [d for d in dimensions if d not in DIMENSIONS]
    if unknown:
        raise ValueError(f"Onbekende dimensie(s): {unknown}. Kies uit {sorted(DIMENSIONS)}.")
    if search_type not in SEARCH_TYPES:
        raise ValueError(f"Onbekend search_type '{search_type}'. Kies uit {sorted(SEARCH_TYPES)}.")
    if not 1 <= row_limit <= MAX_ROW_LIMIT:
        raise ValueError(f"row_limit moet tussen 1 en {MAX_ROW_LIMIT} liggen.")

    body: dict[str, Any] = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "startRow": start_row,
        "type": search_type,
    }
    if filters:
        api_filters = []
        for f in filters:
            dimension = f.get("dimension")
            operator = f.get("operator", "contains")
            expression = f.get("expression")
            if dimension not in DIMENSIONS or operator not in FILTER_OPERATORS or not expression:
                raise ValueError(
                    "Elk filter heeft 'dimension', 'operator' en 'expression' nodig. "
                    f"Operators: {sorted(FILTER_OPERATORS)}. Ongeldig filter: {f}"
                )
            api_filters.append(
                {"dimension": dimension, "operator": operator, "expression": expression}
            )
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": api_filters}]
    return body


def format_rows(dimensions: list[str], rows: list[dict]) -> list[dict]:
    formatted = []
    for row in rows:
        item = dict(zip(dimensions, row.get("keys", [])))
        item.update(
            clicks=row.get("clicks", 0),
            impressions=row.get("impressions", 0),
            ctr_pct=round(row.get("ctr", 0.0) * 100, 2),
            position=round(row.get("position", 0.0), 1),
        )
        formatted.append(item)
    return formatted


def search_analytics(gsc, site_url: str, body: dict) -> list[dict]:
    response = gsc.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return format_rows(body["dimensions"], response.get("rows", []))


def inspect_url(gsc, site_url: str, url: str, language: str = "nl-NL") -> dict:
    body = {"inspectionUrl": url, "siteUrl": site_url, "languageCode": language}
    return gsc.urlInspection().index().inspect(body=body).execute().get("inspectionResult", {})


def list_sitemaps(gsc, site_url: str) -> list[dict]:
    return gsc.sitemaps().list(siteUrl=site_url).execute().get("sitemap", [])


def list_sites(gsc) -> list[dict]:
    return gsc.sites().list().execute().get("siteEntry", [])
