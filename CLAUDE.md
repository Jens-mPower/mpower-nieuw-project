# CLAUDE.md

MCP-server voor Google Search Console van mPower Digital. Zie `README.md` voor installatie en `UPSTREAM.md` voor de relatie met AminForou/mcp-gsc.

## Klantdata opvragen

* Noemt de gebruiker een klant, roep dan eerst `list_clients` aan en gebruik de `property` van die klant als `site_url`.
* Staat bij een klant `geen toegang`, meld dat dan en verzin geen cijfers. Het service account moet dan nog worden toegevoegd in Search Console.
* CTR komt uit de tools als fractie (`0.0312` = 3,12%).
* Rapporteer in het Nederlands en gebruik geen gedachtestreepje (het lange streepje).
* De server is standaard alleen-lezen. Wijzigingen in Search Console (sitemaps indienen of verwijderen) doet de gebruiker zelf.

## Ontwikkelen

* `gsc_server.py`, `test_gsc_server.py` en `LICENSE` zijn upstream-bestanden: niet wijzigen. Aanpassingen horen in `mpower_gsc.py` met tests in `test_mpower_gsc.py`.
* Tests: `uv run pytest` (geen Google-account nodig).
* Nooit sleutels, tokens of klantenlijsten met echte data committen.
