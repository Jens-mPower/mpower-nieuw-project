"""Klantenlijst: inlezen uit Google Sheets of een CSV-bestand en klanten opzoeken."""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

INACTIVE_VALUES = {"nee", "no", "false", "0", "uit", "inactief"}

# Toegestane kolomnamen (hoofdletterongevoelig) per veld.
NAME_HEADERS = {"klant", "naam", "klantnaam", "client", "name"}
PROPERTY_HEADERS = {"property", "site", "site_url", "gsc property", "gsc-property"}
ACTIVE_HEADERS = {"actief", "active"}


class ClientListError(Exception):
    """De klantenlijst kan niet worden gelezen of is ongeldig."""


class ClientNotFound(Exception):
    """De gevraagde klant staat niet (of niet eenduidig) in de lijst."""


@dataclass(frozen=True)
class Client:
    name: str
    property: str
    active: bool = True


def _find_column(header: list[str], options: set[str]) -> int | None:
    for index, value in enumerate(header):
        if value.strip().lower() in options:
            return index
    return None


def parse_rows(rows: list[list[str]]) -> list[Client]:
    """Zet ruwe rijen (eerste rij = kopteksten) om naar klanten."""
    if not rows:
        raise ClientListError("De klantenlijst is leeg.")

    header = rows[0]
    name_col = _find_column(header, NAME_HEADERS)
    property_col = _find_column(header, PROPERTY_HEADERS)
    active_col = _find_column(header, ACTIVE_HEADERS)
    if name_col is None or property_col is None:
        raise ClientListError(
            "De klantenlijst mist de kolom 'Klant' of 'Property'. "
            f"Gevonden kopteksten: {header}"
        )

    def cell(row: list[str], col: int | None) -> str:
        if col is None or col >= len(row):
            return ""
        return str(row[col]).strip()

    clients = []
    for row in rows[1:]:
        name = cell(row, name_col)
        prop = cell(row, property_col)
        if not name or not prop:
            continue
        active = cell(row, active_col).lower() not in INACTIVE_VALUES
        clients.append(Client(name=name, property=prop, active=active))
    return clients


def read_csv_rows(path: str | Path) -> list[list[str]]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            return [row for row in csv.reader(handle)]
    except OSError as exc:
        raise ClientListError(f"Kan het CSV-bestand '{path}' niet lezen: {exc}") from exc


def resolve(clients: list[Client], query: str) -> Client:
    """Zoek een actieve klant op naam of property.

    Volgorde: exacte naam, exacte property, daarna een unieke deelmatch op naam.
    """
    needle = query.strip().lower()
    active = [c for c in clients if c.active]

    for client in active:
        if client.name.lower() == needle:
            return client
    for client in active:
        if client.property.lower() == needle:
            return client

    partial = [c for c in active if needle in c.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        names = ", ".join(c.name for c in partial)
        raise ClientNotFound(f"'{query}' past bij meerdere klanten: {names}. Wees specifieker.")

    if any(needle == c.name.lower() for c in clients):
        raise ClientNotFound(f"Klant '{query}' staat op inactief in de klantenlijst.")
    raise ClientNotFound(
        f"Klant '{query}' staat niet in de klantenlijst. Gebruik list_clients voor een overzicht."
    )


class ClientRegistry:
    """Houdt de klantenlijst kort in het geheugen, zodat niet elke vraag de Sheet leest."""

    def __init__(
        self,
        load_rows: Callable[[], list[list[str]]],
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._load_rows = load_rows
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: list[Client] | None = None
        self._loaded_at = 0.0

    def all(self, refresh: bool = False) -> list[Client]:
        expired = self._clock() - self._loaded_at > self._ttl
        if refresh or self._cache is None or expired:
            self._cache = parse_rows(self._load_rows())
            self._loaded_at = self._clock()
        return self._cache

    def get(self, query: str) -> Client:
        return resolve(self.all(), query)
