import pytest

from mpower_gsc.clients import (
    Client,
    ClientListError,
    ClientNotFound,
    ClientRegistry,
    parse_rows,
    read_csv_rows,
    resolve,
)

ROWS = [
    ["Klant", "Property", "Actief"],
    ["Voorbeeld BV", "sc-domain:voorbeeld.nl", "ja"],
    ["Demo Webshop", "https://www.demowebshop.nl/", ""],
    ["Demo Blog", "sc-domain:demoblog.nl", "ja"],
    ["Oude Klant", "sc-domain:oudeklant.nl", "nee"],
    ["", "sc-domain:zondernaam.nl", "ja"],
]


def test_parse_rows_reads_columns_and_active_flag():
    clients = parse_rows(ROWS)
    assert len(clients) == 4  # rij zonder naam wordt overgeslagen
    assert clients[0] == Client("Voorbeeld BV", "sc-domain:voorbeeld.nl", True)
    assert clients[1].active is True  # lege 'Actief' telt als actief
    assert clients[3].active is False


def test_parse_rows_accepts_other_column_order_and_missing_active_column():
    clients = parse_rows([["site_url", "Naam"], ["sc-domain:a.nl", "A"]])
    assert clients == [Client("A", "sc-domain:a.nl", True)]


def test_parse_rows_handles_short_rows():
    clients = parse_rows([["Klant", "Property", "Actief"], ["A", "sc-domain:a.nl"]])
    assert clients == [Client("A", "sc-domain:a.nl", True)]


def test_parse_rows_requires_headers():
    with pytest.raises(ClientListError):
        parse_rows([["Iets", "Anders"]])
    with pytest.raises(ClientListError):
        parse_rows([])


def test_resolve_by_exact_name_property_and_unique_partial():
    clients = parse_rows(ROWS)
    assert resolve(clients, "voorbeeld bv").property == "sc-domain:voorbeeld.nl"
    assert resolve(clients, "https://www.demowebshop.nl/").name == "Demo Webshop"
    assert resolve(clients, "webshop").name == "Demo Webshop"


def test_resolve_rejects_ambiguous_inactive_and_unknown():
    clients = parse_rows(ROWS)
    with pytest.raises(ClientNotFound, match="meerdere"):
        resolve(clients, "demo")
    with pytest.raises(ClientNotFound, match="inactief"):
        resolve(clients, "Oude Klant")
    with pytest.raises(ClientNotFound, match="niet in de klantenlijst"):
        resolve(clients, "Bestaat Niet")


def test_registry_caches_until_ttl_or_refresh():
    calls = []
    now = [0.0]

    def loader():
        calls.append(1)
        return ROWS

    registry = ClientRegistry(loader, ttl_seconds=60, clock=lambda: now[0])
    registry.all()
    registry.all()
    assert len(calls) == 1
    now[0] = 61
    registry.all()
    assert len(calls) == 2
    registry.all(refresh=True)
    assert len(calls) == 3


def test_example_csv_is_valid(tmp_path):
    clients = parse_rows(read_csv_rows("klanten.voorbeeld.csv"))
    assert [c.name for c in clients if c.active] == ["Voorbeeld BV", "Demo Webshop"]
