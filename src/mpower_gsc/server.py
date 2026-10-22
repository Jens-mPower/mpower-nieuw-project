"""MCP-server: Google Search Console voor alle klanten uit één klantenlijst."""

from __future__ import annotations

import functools
import os
from typing import Any, Callable

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from mpower_gsc import google_api
from mpower_gsc.clients import (
    ClientListError,
    ClientNotFound,
    ClientRegistry,
    read_csv_rows,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)

server = MCPServer(
    "mpower-gsc",
    instructions=(
        "Google Search Console-data (alleen lezen) voor de klanten van mPower Digital. "
        "Gebruik eerst list_clients om te zien welke klanten beschikbaar zijn en "
        "geef daarna de klantnaam mee aan de andere tools."
    ),
)


class _State:
    """Lazy opgebouwde Google-clients en klantenlijst, zodat de server ook zonder
    configuratie opstart en pas bij een toolaanroep een duidelijke fout geeft."""

    def __init__(self):
        self._gsc = None
        self._sheets = None
        self._registry: ClientRegistry | None = None

    def _services(self):
        if self._gsc is None:
            credentials = google_api.load_credentials()
            self._gsc, self._sheets = google_api.build_services(credentials)
        return self._gsc, self._sheets

    @property
    def gsc(self):
        return self._services()[0]

    @property
    def registry(self) -> ClientRegistry:
        if self._registry is None:
            sheet_id = os.getenv("GSC_CLIENTS_SHEET_ID")
            csv_path = os.getenv("GSC_CLIENTS_CSV")
            ttl = float(os.getenv("GSC_CLIENTS_CACHE_SECONDS", "300"))
            if sheet_id:
                cell_range = os.getenv("GSC_CLIENTS_SHEET_RANGE", "Klanten!A:C")
                sheets = self._services()[1]
                loader = lambda: google_api.read_sheet_rows(sheets, sheet_id, cell_range)
            elif csv_path:
                loader = lambda: read_csv_rows(csv_path)
            else:
                raise google_api.ConfigError(
                    "Geen klantenlijst ingesteld. Zet GSC_CLIENTS_SHEET_ID (Google Sheet) "
                    "of GSC_CLIENTS_CSV (pad naar een CSV-bestand)."
                )
            self._registry = ClientRegistry(loader, ttl_seconds=ttl)
        return self._registry


state = _State()


def _http_error_message(exc) -> str:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 401:
        return (
            "Google ontving geen geldig toegangstoken (401). Werk je in een Claude Code-"
            "cloudomgeving, controleer dan of het netwerkgeheim van het type 'GCP access token' "
            f"is ingesteld voor *.googleapis.com. Details: {exc}"
        )
    if status == 502 and "injection failed" in str(exc):
        return (
            "De proxy kon geen Google-token aanmaken met het netwerkgeheim. Controleer de "
            f"sleutel en de scopes van het geheim. Details: {exc}"
        )
    if status == 403:
        return (
            "Google weigert de toegang (403). Controleer of het service account als gebruiker "
            "is toegevoegd aan deze property in Search Console, of (bij de klantenlijst) of de "
            f"Sheet met het service account is gedeeld. Details: {exc}"
        )
    if status == 404:
        return f"Niet gevonden (404). Controleer de property of het Sheet-ID. Details: {exc}"
    return f"Fout van de Google-API: {exc}"


def tool_errors(func: Callable) -> Callable:
    """Zet verwachte fouten om in een leesbare ToolError voor Claude."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError

        try:
            return func(*args, **kwargs)
        except (google_api.ConfigError, ClientListError, ClientNotFound, ValueError) as exc:
            raise ToolError(str(exc)) from exc
        except HttpError as exc:
            raise ToolError(_http_error_message(exc)) from exc
        except RefreshError as exc:
            raise ToolError(
                "Google accepteert de service-account-sleutel niet. Controleer of de sleutel "
                f"nog geldig is en niet is ingetrokken. Details: {exc}"
            ) from exc

    return wrapper


@server.tool(annotations=READ_ONLY)
@tool_errors
def list_clients(refresh: bool = False) -> list[dict[str, Any]]:
    """Toon alle klanten uit de klantenlijst, met per klant of het service account
    toegang heeft tot de Search Console-property.

    Args:
        refresh: true om de klantenlijst direct opnieuw in te lezen (anders max. 5 min cache).
    """
    clients = state.registry.all(refresh=refresh)
    access = {s["siteUrl"]: s.get("permissionLevel") for s in google_api.list_sites(state.gsc)}
    return [
        {
            "klant": c.name,
            "property": c.property,
            "actief": c.active,
            "toegang": access.get(c.property, "geen toegang"),
        }
        for c in clients
    ]


@server.tool(annotations=READ_ONLY)
@tool_errors
def search_analytics(
    client: str,
    start_date: str | None = None,
    end_date: str | None = None,
    dimensions: list[str] | None = None,
    filters: list[dict[str, str]] | None = None,
    search_type: str = "web",
    row_limit: int = 100,
    start_row: int = 0,
) -> dict[str, Any]:
    """Clicks, impressies, CTR (in procenten) en gemiddelde positie voor een klant.

    Args:
        client: klantnaam of property uit de klantenlijst.
        start_date: JJJJ-MM-DD. Standaard 28 dagen tot en met 3 dagen geleden.
        end_date: JJJJ-MM-DD.
        dimensions: lijst uit query, page, country, device, date, searchAppearance.
            Standaard ["query"]. Een lege lijst geeft alleen totalen.
        filters: bijv. [{"dimension": "page", "operator": "contains", "expression": "/blog/"}].
            Operators: contains, equals, notContains, notEquals, includingRegex, excludingRegex.
        search_type: web, image, video, news, discover of googleNews.
        row_limit: aantal rijen (1 tot 25000).
        start_row: startpositie voor paginering.
    """
    target = state.registry.get(client)
    dims = ["query"] if dimensions is None else dimensions
    body = google_api.build_query_body(
        start_date, end_date, dims, row_limit, start_row, search_type, filters
    )
    rows = google_api.search_analytics(state.gsc, target.property, body)
    return {
        "klant": target.name,
        "property": target.property,
        "periode": {"start": body["startDate"], "eind": body["endDate"]},
        "dimensies": dims,
        "aantal_rijen": len(rows),
        "rijen": rows,
    }


@server.tool(annotations=READ_ONLY)
@tool_errors
def inspect_url(client: str, url: str) -> dict[str, Any]:
    """Indexeringsstatus van één URL via de URL Inspection API.

    Args:
        client: klantnaam of property uit de klantenlijst.
        url: de volledige URL die je wilt inspecteren (moet onder de property vallen).
    """
    target = state.registry.get(client)
    result = google_api.inspect_url(state.gsc, target.property, url)
    return {"klant": target.name, "property": target.property, "url": url, "resultaat": result}


@server.tool(annotations=READ_ONLY)
@tool_errors
def list_sitemaps(client: str) -> dict[str, Any]:
    """Ingediende sitemaps van een klant, met status, fouten en waarschuwingen.

    Args:
        client: klantnaam of property uit de klantenlijst.
    """
    target = state.registry.get(client)
    sitemaps = google_api.list_sitemaps(state.gsc, target.property)
    return {"klant": target.name, "property": target.property, "sitemaps": sitemaps}


def main():
    server.run()


if __name__ == "__main__":
    main()
