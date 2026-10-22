"""Tests voor de mPower-uitbreiding (mpower_gsc.py). Geen echte Google-aanroepen."""

import asyncio
import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

ENV_KEYS = (
    "GSC_AUTH_VIA_PROXY", "GSC_READ_ONLY", "GSC_CREDENTIALS_PATH", "GSC_CLIENTS_SHEET_ID",
    "GSC_CLIENTS_CSV", "GSC_SKIP_OAUTH", "GSC_OAUTH_CLIENT_SECRETS_FILE",
)


@pytest.fixture
def load(monkeypatch, tmp_path):
    """Laad gsc_server en mpower_gsc opnieuw met de opgegeven omgeving."""

    def _load(**env):
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("GSC_CONFIG_DIR", str(tmp_path))
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        for name in ("mpower_gsc", "gsc_server"):
            sys.modules.pop(name, None)
        return importlib.import_module("mpower_gsc")

    yield _load
    for name in ("mpower_gsc", "gsc_server"):
        sys.modules.pop(name, None)


def tool_names(mod):
    return {t.name for t in mod.mcp._tool_manager.list_tools()}


# --- Configuratie ----------------------------------------------------------

def test_read_only_is_default_and_removes_write_tools(load):
    mod = load()
    names = tool_names(mod)
    assert mod.READ_ONLY is True
    assert mod.gsc_server.SCOPES == ["https://www.googleapis.com/auth/webmasters.readonly"]
    assert not names & set(mod.WRITE_TOOLS)
    assert {"list_clients", "get_capabilities", "get_search_analytics",
            "compare_search_periods", "batch_url_inspection"} <= names


def test_write_tools_available_when_read_only_disabled(load):
    mod = load(GSC_READ_ONLY="false")
    assert set(mod.WRITE_TOOLS) <= tool_names(mod)
    assert mod.gsc_server.SCOPES == ["https://www.googleapis.com/auth/webmasters"]


def test_proxy_mode_removes_reauthenticate(load):
    assert "reauthenticate" in tool_names(load())
    assert "reauthenticate" not in tool_names(load(GSC_AUTH_VIA_PROXY="1"))


def test_configure_is_idempotent(load):
    mod = load(GSC_AUTH_VIA_PROXY="1")
    before = sorted(tool_names(mod))
    mod.configure()
    assert sorted(tool_names(mod)) == before


def test_server_instructions_mention_list_clients(load):
    mod = load()
    assert "list_clients" in mod.mcp.instructions


# --- Authenticatie ---------------------------------------------------------

def test_proxy_mode_builds_service_without_credentials(load):
    mod = load(GSC_AUTH_VIA_PROXY="1")
    with patch.object(mod, "build") as build:
        mod.gsc_server.get_gsc_service()
    _, kwargs = build.call_args
    assert "credentials" not in kwargs
    assert kwargs["http"] is not None


def test_proxy_mode_uses_fresh_http_per_call(load):
    mod = load(GSC_AUTH_VIA_PROXY="1")
    with patch.object(mod, "build") as build:
        mod.gsc_server.get_gsc_service()
        mod.gsc_server.get_gsc_service()
    first, second = (c.kwargs["http"] for c in build.call_args_list)
    assert first is not second


def test_proxy_http_sends_no_authorization_header(load):
    mod = load(GSC_AUTH_VIA_PROXY="1")
    http = mod.proxy_http()
    with patch.object(http, "_request", return_value=(MagicMock(status=200), b"{}")) as req:
        http.request("https://searchconsole.googleapis.com/webmasters/v3/sites")
    import inspect
    bound = inspect.signature(type(http)._request).bind(http, *req.call_args.args, **req.call_args.kwargs)
    headers = bound.arguments["headers"]
    assert isinstance(headers, dict) and headers  # er zijn wel headers, alleen geen auth
    assert "authorization" not in {k.lower() for k in headers}


def test_explicit_key_file_wins_over_proxy(load, tmp_path):
    key = tmp_path / "sa.json"
    key.write_text("{}")
    mod = load(GSC_AUTH_VIA_PROXY="1", GSC_CREDENTIALS_PATH=str(key))
    assert mod.use_proxy() is False
    with patch.object(mod, "_upstream_get_gsc_service", return_value="upstream") as upstream:
        assert mod.gsc_server.get_gsc_service() == "upstream"
    upstream.assert_called_once()


def test_without_proxy_upstream_auth_is_used(load):
    mod = load()
    with patch.object(mod, "_upstream_get_gsc_service", return_value="upstream"):
        assert mod.gsc_server.get_gsc_service() == "upstream"


def test_sheets_without_key_or_proxy_gives_clear_error(load):
    mod = load()
    with pytest.raises(RuntimeError, match="GSC_CLIENTS_CSV"):
        mod.get_sheets_service()


# --- Klantenlijst ----------------------------------------------------------

ROWS = [
    ["Klant", "Property", "Actief"],
    ["Voorbeeld BV", "sc-domain:voorbeeld.nl", "ja"],
    ["Demo Webshop", "https://www.demowebshop.nl/", ""],
    ["Oude Klant", "sc-domain:oudeklant.nl", "nee"],
    ["", "sc-domain:zondernaam.nl", "ja"],
    ["Korte Rij", "sc-domain:kort.nl"],
]


def test_parse_client_rows(load):
    mod = load()
    assert mod.parse_client_rows(ROWS) == [
        {"klant": "Voorbeeld BV", "property": "sc-domain:voorbeeld.nl", "actief": True},
        {"klant": "Demo Webshop", "property": "https://www.demowebshop.nl/", "actief": True},
        {"klant": "Oude Klant", "property": "sc-domain:oudeklant.nl", "actief": False},
        {"klant": "Korte Rij", "property": "sc-domain:kort.nl", "actief": True},
    ]


def test_parse_client_rows_other_column_order(load):
    mod = load()
    assert mod.parse_client_rows([["site_url", "Naam"], ["sc-domain:a.nl", "A"]]) == [
        {"klant": "A", "property": "sc-domain:a.nl", "actief": True}
    ]


def test_parse_client_rows_rejects_bad_input(load):
    mod = load()
    with pytest.raises(ValueError, match="leeg"):
        mod.parse_client_rows([])
    with pytest.raises(ValueError, match="Klant"):
        mod.parse_client_rows([["Iets", "Anders"]])


def test_example_csv_is_valid(load):
    mod = load()
    clients = mod.parse_client_rows(mod.read_csv_rows("klanten.voorbeeld.csv"))
    assert [c["klant"] for c in clients if c["actief"]] == ["Voorbeeld BV", "Demo Webshop"]


def test_client_cache_ttl_and_refresh(load):
    mod = load()
    calls, now = [], [0.0]

    def loader():
        calls.append(1)
        return ROWS

    cache = mod.ClientCache(loader, ttl_seconds=60, clock=lambda: now[0])
    cache.get()
    cache.get()
    assert len(calls) == 1
    now[0] = 61
    cache.get()
    assert len(calls) == 2
    cache.get(refresh=True)
    assert len(calls) == 3


def test_load_client_rows_prefers_sheet_and_passes_range(load):
    mod = load(GSC_CLIENTS_SHEET_ID="abc", GSC_CLIENTS_CSV="klanten.voorbeeld.csv")
    sheets = MagicMock()
    sheets.spreadsheets().values().get().execute.return_value = {"values": ROWS}
    with patch.object(mod, "get_sheets_service", return_value=sheets):
        assert mod.load_client_rows() == ROWS
    sheets.spreadsheets().values().get.assert_called_with(spreadsheetId="abc", range="Klanten!A:C")


def test_load_client_rows_none_when_not_configured(load):
    assert load().load_client_rows() is None


SITES = [
    {"siteUrl": "sc-domain:voorbeeld.nl", "permissionLevel": "siteRestrictedUser"},
    {"siteUrl": "sc-domain:nieuw.nl", "permissionLevel": "siteFullUser"},
]


def test_overview_with_client_list(load):
    mod = load()
    clients = mod.parse_client_rows(ROWS[:3])
    assert mod.build_client_overview(clients, SITES) == {
        "bron": "klantenlijst",
        "klanten": [
            {"klant": "Voorbeeld BV", "property": "sc-domain:voorbeeld.nl", "actief": True,
             "toegang": "siteRestrictedUser"},
            {"klant": "Demo Webshop", "property": "https://www.demowebshop.nl/", "actief": True,
             "toegang": "geen toegang"},
        ],
        "properties_zonder_klant": ["sc-domain:nieuw.nl"],
    }


def test_overview_without_client_list_lists_all_properties(load):
    mod = load()
    overview = mod.build_client_overview(None, SITES)
    assert [k["property"] for k in overview["klanten"]] == ["sc-domain:nieuw.nl", "sc-domain:voorbeeld.nl"]
    assert overview["bron"].startswith("Search Console")


def test_list_clients_tool_end_to_end(load):
    mod = load(GSC_CLIENTS_CSV="klanten.voorbeeld.csv")
    service = MagicMock()
    service.sites().list().execute.return_value = {"siteEntry": SITES}
    with patch.object(mod.gsc_server, "get_gsc_service", return_value=service):
        result = json.loads(asyncio.run(mod.list_clients()))
    first = result["klanten"][0]
    assert first == {"klant": "Voorbeeld BV", "property": "sc-domain:voorbeeld.nl",
                     "actief": True, "toegang": "siteRestrictedUser"}


def test_list_clients_reports_errors_as_text(load):
    mod = load(GSC_CLIENTS_CSV="/bestaat/niet.csv")
    assert asyncio.run(mod.list_clients()).startswith("Error:")


def test_capabilities_lists_available_tools_only(load):
    mod = load(GSC_AUTH_VIA_PROXY="1")
    text = asyncio.run(mod.get_capabilities())
    assert "proxymodus" in text and "alleen lezen" in text
    assert "list_clients" in text and "compare_search_periods" in text
    assert "delete_sitemap" not in text and "reauthenticate" not in text
    assert "get_creator_info" not in tool_names(mod)


def test_empty_key_path_from_mcp_json_keeps_proxy_mode(load):
    # .mcp.json geeft lege variabelen door als "" in plaats van ze weg te laten.
    mod = load(GSC_AUTH_VIA_PROXY="1", GSC_CREDENTIALS_PATH="", GSC_CLIENTS_SHEET_ID="",
               GSC_CLIENTS_CSV="")
    assert mod.use_proxy() is True
    assert mod.load_client_rows() is None


def test_list_clients_401_in_proxy_mode_explains_network_secret(load):
    mod = load(GSC_AUTH_VIA_PROXY="1")
    service = MagicMock()
    service.sites().list().execute.side_effect = Exception("<HttpError 401 when requesting ...>")
    with patch.object(mod.gsc_server, "get_gsc_service", return_value=service):
        text = asyncio.run(mod.list_clients())
    assert text.startswith("Error:") and "netwerkgeheim" in text


def test_no_proxy_hint_outside_proxy_mode(load):
    mod = load()
    assert mod.proxy_hint(Exception("HttpError 401")) == ""
