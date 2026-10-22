"""mPower-uitbreiding op gsc_server.py (AminForou/mcp-gsc).

gsc_server.py blijft ongewijzigd, zodat updates van upstream eenvoudig over te
nemen zijn. Deze module voegt toe:

* Proxymodus (GSC_AUTH_VIA_PROXY=1): verzoeken gaan zonder sleutel de deur uit en
  de proxy van een Claude Code-cloudomgeving voegt het Google-token toe
  (netwerkgeheim van het type "GCP access token"). De sleutel staat nooit in de sessie.
* Alleen-lezen als standaard (GSC_READ_ONLY=1): leesscope en geen schrijftools.
* list_clients: klantnamen uit een Google Sheet of CSV, gekoppeld aan de
  Search Console-properties waar het service account toegang toe heeft.
"""

from __future__ import annotations

import csv
import json
import os
import time
from typing import Callable

import httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build

import gsc_server
from gsc_server import mcp

READ_ONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

# Tools die iets wijzigen in Search Console. In alleen-lezen-modus worden ze niet
# aangeboden. manage_sitemaps hoort erbij omdat het ook submit/delete kan; lezen
# kan via list_sitemaps_enhanced, get_sitemap_details en get_sitemaps.
WRITE_TOOLS = ("add_site", "delete_site", "submit_sitemap", "delete_sitemap", "manage_sitemaps")

INACTIVE_VALUES = {"nee", "no", "false", "0", "uit", "inactief"}
NAME_HEADERS = {"klant", "naam", "klantnaam", "client", "name"}
PROPERTY_HEADERS = {"property", "site", "site_url", "gsc property", "gsc-property"}
ACTIVE_HEADERS = {"actief", "active"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja"}


PROXY_MODE = env_flag("GSC_AUTH_VIA_PROXY")
READ_ONLY = env_flag("GSC_READ_ONLY", default=True)


# --- Authenticatie ---------------------------------------------------------

def use_proxy() -> bool:
    """Proxymodus, tenzij er expliciet een sleutelbestand is ingesteld."""
    return PROXY_MODE and not gsc_server.GSC_CREDENTIALS_PATH


def proxy_http() -> httplib2.Http:
    # Per aanroep een nieuwe verbinding: httplib2 is niet thread-safe en
    # batch_url_inspection roept get_gsc_service() vanuit meerdere threads aan.
    return httplib2.Http(timeout=60)


_upstream_get_gsc_service = gsc_server.get_gsc_service


def get_gsc_service():
    if use_proxy():
        return build("searchconsole", "v1", http=proxy_http(), cache_discovery=False)
    return _upstream_get_gsc_service()


def get_sheets_service():
    if use_proxy():
        return build("sheets", "v4", http=proxy_http(), cache_discovery=False)
    path = gsc_server.GSC_CREDENTIALS_PATH
    if not path or not os.path.exists(path):
        raise RuntimeError(
            "De klanten-Sheet lezen kan alleen met een service account "
            "(GSC_CREDENTIALS_PATH) of in proxymodus. Gebruik anders GSC_CLIENTS_CSV."
        )
    creds = service_account.Credentials.from_service_account_file(path, scopes=[SHEETS_SCOPE])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


# --- Klantenlijst ----------------------------------------------------------

def _find_column(header: list[str], options: set[str]) -> int | None:
    for index, value in enumerate(header):
        if str(value).strip().lower() in options:
            return index
    return None


def parse_client_rows(rows: list[list[str]]) -> list[dict]:
    """Zet rijen (eerste rij = kopteksten) om naar klanten."""
    if not rows:
        raise ValueError("De klantenlijst is leeg.")
    header = rows[0]
    name_col = _find_column(header, NAME_HEADERS)
    property_col = _find_column(header, PROPERTY_HEADERS)
    active_col = _find_column(header, ACTIVE_HEADERS)
    if name_col is None or property_col is None:
        raise ValueError(
            f"De klantenlijst mist de kolom 'Klant' of 'Property'. Gevonden kopteksten: {header}"
        )

    def cell(row: list[str], col: int | None) -> str:
        if col is None or col >= len(row):
            return ""
        return str(row[col]).strip()

    clients = []
    for row in rows[1:]:
        name, prop = cell(row, name_col), cell(row, property_col)
        if name and prop:
            active = cell(row, active_col).lower() not in INACTIVE_VALUES
            clients.append({"klant": name, "property": prop, "actief": active})
    return clients


def read_csv_rows(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def load_client_rows() -> list[list[str]] | None:
    """Ruwe rijen uit de Sheet of CSV, of None als er geen klantenlijst is ingesteld."""
    sheet_id = os.environ.get("GSC_CLIENTS_SHEET_ID", "").strip()
    csv_path = os.environ.get("GSC_CLIENTS_CSV", "").strip()
    if sheet_id:
        cell_range = os.environ.get("GSC_CLIENTS_SHEET_RANGE", "Klanten!A:C")
        result = get_sheets_service().spreadsheets().values().get(
            spreadsheetId=sheet_id, range=cell_range
        ).execute()
        return result.get("values", [])
    if csv_path:
        return read_csv_rows(csv_path)
    return None


class ClientCache:
    """Houdt de klantenlijst kort vast, zodat niet elke vraag de Sheet leest."""

    def __init__(self, loader: Callable[[], list[list[str]] | None], ttl_seconds: float,
                 clock: Callable[[], float] = time.monotonic):
        self._loader, self._ttl, self._clock = loader, ttl_seconds, clock
        self._value: list[dict] | None = None
        self._loaded_at: float | None = None

    def get(self, refresh: bool = False) -> list[dict] | None:
        now = self._clock()
        if refresh or self._loaded_at is None or now - self._loaded_at > self._ttl:
            rows = self._loader()
            self._value = None if rows is None else parse_client_rows(rows)
            self._loaded_at = now
        return self._value


client_cache = ClientCache(
    load_client_rows, ttl_seconds=float(os.environ.get("GSC_CLIENTS_CACHE_SECONDS", "300"))
)


def build_client_overview(clients: list[dict] | None, sites: list[dict]) -> dict:
    access = {s.get("siteUrl"): s.get("permissionLevel") for s in sites}
    if clients is None:
        return {
            "bron": "Search Console (geen klantenlijst ingesteld)",
            "klanten": [
                {"klant": None, "property": url, "actief": True, "toegang": level}
                for url, level in sorted(access.items())
            ],
            "properties_zonder_klant": [],
        }
    listed = {c["property"] for c in clients}
    return {
        "bron": "klantenlijst",
        "klanten": [
            {**c, "toegang": access.get(c["property"], "geen toegang")} for c in clients
        ],
        "properties_zonder_klant": sorted(url for url in access if url not in listed),
    }


@mcp.tool()
async def list_clients(refresh: bool = False) -> str:
    """
    List mPower Digital's clients with their exact Search Console property (site_url)
    and whether the service account has access. Call this FIRST when the user names a
    client, then pass the 'property' value as site_url to the other tools.

    Args:
        refresh: true to re-read the client sheet now (otherwise cached for 5 minutes).
    """
    try:
        clients = client_cache.get(refresh=refresh)
        sites = gsc_server.get_gsc_service().sites().list().execute().get("siteEntry", [])
        return json.dumps(build_client_overview(clients, sites), ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}{proxy_hint(e)}"


def proxy_hint(error: Exception) -> str:
    """Extra uitleg als de proxy geen Google-token heeft toegevoegd."""
    if use_proxy() and "401" in str(error):
        return (
            "\nHint: Google kreeg geen toegangstoken. Controleer in de cloudomgeving het "
            "netwerkgeheim van het type 'GCP access token (with Service Account Key)' voor "
            "*.googleapis.com, en start daarna een nieuwe sessie."
        )
    return ""


# --- Tools en serverbeschrijving -------------------------------------------

def capabilities_text() -> str:
    lines = ["Google Search Console MCP (mPower Digital)", ""]
    if use_proxy():
        lines.append("AUTH: proxymodus. Het Google-token wordt door de cloudomgeving toegevoegd.")
    else:
        try:
            gsc_server.get_gsc_service()
            lines.append("AUTH: ingelogd.")
        except Exception as e:
            lines.append(f"AUTH: niet ingelogd. Details: {e}")
    lines.append(f"MODUS: {'alleen lezen' if READ_ONLY else 'lezen en schrijven'}")
    lines += ["", "START: roep list_clients aan voor klantnamen en de exacte site_url.", "",
              "TOOLS:"]
    for tool in mcp._tool_manager.list_tools():
        summary = (tool.description or "").strip().splitlines()[0] if tool.description else ""
        lines.append(f"  - {tool.name}: {summary}")
    return "\n".join(lines)


async def get_capabilities() -> str:
    """
    Get a full list of all available tools, current auth status, and how to get started.
    ALWAYS call this first when asked what tools are available or what this server can do.
    """
    return capabilities_text()


def configure() -> None:
    """Pas de upstream-server aan. Idempotent."""
    gsc_server.get_gsc_service = get_gsc_service
    if READ_ONLY:
        gsc_server.SCOPES = [READ_ONLY_SCOPE]
    registered = {t.name for t in mcp._tool_manager.list_tools()}
    removals = list(WRITE_TOOLS) if READ_ONLY else []
    if use_proxy():
        removals.append("reauthenticate")  # OAuth-login is in proxymodus niet nodig
    removals.append("get_creator_info")  # promotie van de maker; vermelding staat in LICENSE/README
    removals.append("get_capabilities")  # vervangen door de versie hieronder
    for name in removals:
        if name in registered:
            mcp.remove_tool(name)
    mcp.add_tool(get_capabilities)
    mcp._mcp_server.instructions = (
        "Google Search Console data for mPower Digital's clients. When the user names a "
        "client, call list_clients first and use that client's 'property' as site_url."
    )


configure()


def main():
    gsc_server.main()


if __name__ == "__main__":
    main()
