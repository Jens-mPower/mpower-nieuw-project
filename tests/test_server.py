"""Test de tools tegen een nep-Search Console, zonder echte Google-aanroepen."""

import asyncio

import pytest

from mpower_gsc import server
from mpower_gsc.clients import ClientRegistry


class _Call:
    def __init__(self, result, log, name, kwargs):
        self._result, self._log, self._name, self._kwargs = result, log, name, kwargs

    def execute(self):
        self._log.append((self._name, self._kwargs))
        return self._result


class FakeGSC:
    def __init__(self):
        self.log = []

    def sites(self):
        return self

    def list(self, **kw):
        if "siteUrl" in kw:
            return _Call({"sitemap": [{"path": "https://voorbeeld.nl/sitemap.xml"}]}, self.log, "sitemaps", kw)
        return _Call({"siteEntry": [{"siteUrl": "sc-domain:voorbeeld.nl",
                                     "permissionLevel": "siteRestrictedUser"}]}, self.log, "sites", kw)

    def sitemaps(self):
        return self

    def searchanalytics(self):
        return self

    def query(self, **kw):
        return _Call({"rows": [{"keys": ["seo"], "clicks": 5, "impressions": 100,
                                "ctr": 0.05, "position": 3.0}]}, self.log, "query", kw)


ROWS = [["Klant", "Property"], ["Voorbeeld BV", "sc-domain:voorbeeld.nl"],
        ["Andere Klant", "sc-domain:andere.nl"]]


@pytest.fixture
def fake(monkeypatch):
    gsc = FakeGSC()
    monkeypatch.setattr(server.state, "_gsc", gsc)
    monkeypatch.setattr(server.state, "_sheets", object())
    monkeypatch.setattr(server.state, "_registry", ClientRegistry(lambda: ROWS))
    return gsc


def test_list_clients_shows_access(fake):
    assert server.list_clients() == [
        {"klant": "Voorbeeld BV", "property": "sc-domain:voorbeeld.nl", "actief": True,
         "toegang": "siteRestrictedUser"},
        {"klant": "Andere Klant", "property": "sc-domain:andere.nl", "actief": True,
         "toegang": "geen toegang"},
    ]


def test_search_analytics_uses_client_property(fake):
    result = server.search_analytics("voorbeeld", start_date="2026-09-01", end_date="2026-09-30")
    name, kwargs = fake.log[-1]
    assert name == "query" and kwargs["siteUrl"] == "sc-domain:voorbeeld.nl"
    assert result["periode"] == {"start": "2026-09-01", "eind": "2026-09-30"}
    assert result["rijen"] == [{"query": "seo", "clicks": 5, "impressions": 100,
                                "ctr_pct": 5.0, "position": 3.0}]


def test_unknown_client_becomes_tool_error(fake):
    with pytest.raises(server.ToolError, match="niet in de klantenlijst"):
        server.search_analytics("Onbekend")


def test_list_sitemaps(fake):
    result = server.list_sitemaps("Voorbeeld BV")
    assert result["sitemaps"][0]["path"] == "https://voorbeeld.nl/sitemap.xml"


def test_missing_client_list_config_gives_clear_error(monkeypatch):
    monkeypatch.setattr(server.state, "_registry", None)
    monkeypatch.delenv("GSC_CLIENTS_SHEET_ID", raising=False)
    monkeypatch.delenv("GSC_CLIENTS_CSV", raising=False)
    with pytest.raises(server.ToolError, match="Geen klantenlijst"):
        server.search_analytics("x")


def test_tools_are_registered_and_read_only():
    tools = asyncio.run(server.server.list_tools())
    names = {t.name for t in tools}
    assert names == {"list_clients", "search_analytics", "inspect_url", "list_sitemaps"}
    assert all(t.annotations.read_only_hint for t in tools)
    params = next(t for t in tools if t.name == "search_analytics").input_schema["properties"]
    assert "client" in params and "row_limit" in params
