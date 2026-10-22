# Upstream: AminForou/mcp-gsc

Deze repository bouwt voort op [AminForou/mcp-gsc](https://github.com/AminForou/mcp-gsc) (MIT-licentie, © 2025 Amin Foroutan, zie `LICENSE`).

## Overgenomen versie

* Commit `d49eea9` (15-09-2026), pakketversie 0.4.1

## Ongewijzigd overgenomen

* `gsc_server.py`
* `test_gsc_server.py`
* `LICENSE`

Wijzig deze bestanden niet. Alle mPower-aanpassingen staan in `mpower_gsc.py`, zodat een update van upstream een kwestie van bestanden vervangen is.

## Aangepast overgenomen

* `.claude/skills/*/SKILL.md` (uit `skills/`): stap 1 verwijst naar `list_clients`. In `indexing-audit` gebruikt stap 2 `get_advanced_search_analytics`, omdat `get_search_analytics` geen `sort_by`-parameter heeft. Gedachtestreepjes zijn vervangen door dubbele punten of komma's (huisstijl).
* `pyproject.toml`: dezelfde dependencies, andere projectnaam en entrypoint (`mpower-gsc`).

## Niet overgenomen

Plugin-bestanden (`.claude-plugin/`, `.cursor-plugin/`), `Dockerfile`, `assets/`, de upstream `README.md` en `CLAUDE.md`. Die zijn bedoeld voor de distributie van upstream, niet voor ons gebruik.

## Wat `mpower_gsc.py` aan upstream verandert

1. `gsc_server.get_gsc_service` wordt vervangen: in proxymodus zonder sleutel, anders de upstream-functie.
2. `gsc_server.SCOPES` wordt de leesscope als `GSC_READ_ONLY` aanstaat.
3. Tools die worden weggehaald: de schrijftools (bij alleen-lezen), `reauthenticate` (in proxymodus), `get_creator_info` (promotie) en `get_capabilities` (vervangen door een eigen versie die de echte toollijst toont).
4. Nieuwe tool: `list_clients`. Nieuwe serverinstructies.

## Upstream bijwerken

```bash
git clone --depth 1 https://github.com/AminForou/mcp-gsc /tmp/mcp-gsc
cp /tmp/mcp-gsc/gsc_server.py /tmp/mcp-gsc/test_gsc_server.py /tmp/mcp-gsc/LICENSE .
diff -r /tmp/mcp-gsc/skills .claude/skills   # wijzigingen in skills met de hand overnemen
uv run pytest                                  # beide testsets moeten slagen
```

Controleer daarna in de diff van `gsc_server.py` of er nieuwe schrijftools zijn bijgekomen. Zet die in `WRITE_TOOLS` in `mpower_gsc.py`, anders worden ze in alleen-lezen-modus toch aangeboden. Werk ook "Overgenomen versie" hierboven bij.
