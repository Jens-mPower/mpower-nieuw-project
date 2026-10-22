# mPower GSC MCP

MCP-server waarmee Claude Code de Google Search Console-data van **alle klanten van mPower Digital** kan bevragen, op het web (claude.ai/code) en lokaal.

Gebaseerd op [AminForou/mcp-gsc](https://github.com/AminForou/mcp-gsc) (MIT-licentie, © Amin Foroutan). De server van upstream blijft ongewijzigd; onze aanvullingen staan in een aparte laag. Zie [UPSTREAM.md](UPSTREAM.md).

## Wat het kan

| Tool | Wat het doet |
|---|---|
| `list_clients` | Klantnamen met de exacte property en of het service account toegang heeft (begin hier) |
| `list_properties`, `get_site_details` | Alle properties en hun details |
| `get_search_analytics`, `get_advanced_search_analytics` | Clicks, impressies, CTR en positie, met dimensies, filters en sortering |
| `get_performance_overview` | Totalen en dagtrend over een periode |
| `compare_search_periods` | Twee periodes vergelijken, per query of pagina |
| `get_search_by_page_query` | Zoektermen achter één pagina |
| `inspect_url_enhanced`, `batch_url_inspection`, `check_indexing_issues` | Indexeringsstatus van één of meer URL's |
| `get_sitemaps`, `list_sitemaps_enhanced`, `get_sitemap_details` | Sitemaps met status, fouten en waarschuwingen |
| `get_capabilities` | Overzicht van tools en de inlogstatus |

Daarnaast vier skills in `.claude/skills/`: kannibalisatiecheck, contentkansen, indexeringsaudit en een wekelijks SEO-rapport.

**Standaard alleen lezen.** Tools die iets wijzigen (`add_site`, `delete_site`, `submit_sitemap`, `delete_sitemap`, `manage_sitemaps`) worden niet aangeboden, en de server vraagt alleen de leesscope aan.

## Eenmalige installatie

### 1. Google Cloud

In het Google Cloud-project van het service account (`mpower-content`):

1. Zet onder *APIs & Services* de **Google Search Console API** aan, en de **Google Sheets API** als je de klanten-Sheet gebruikt.
2. Maak bij het service account een sleutel van het type **JSON**. Bewaar die buiten deze repository en commit hem nooit.

### 2. Per klant: toegang in Search Console

Voeg in Search Console per property bij *Instellingen > Gebruikers en rechten* het service account toe met het recht **Beperkt**:

`content-engine@mpower-content.iam.gserviceaccount.com`

Dit is de enige stap die echt nodig is om een klant toe te voegen.

### 3. Optioneel: klanten-Sheet met namen

Zonder Sheet toont `list_clients` alle properties waar het service account toegang toe heeft. Met een Sheet krijg je klantnamen, kun je klanten op inactief zetten en zie je welke properties nog geen klant hebben.

1. Maak een Google Sheet met een tabblad `Klanten`:

   | Klant | Property | Actief |
   |---|---|---|
   | Voorbeeld BV | sc-domain:voorbeeld.nl | ja |
   | Demo Webshop | https://www.demowebshop.nl/ | ja |
   | Oude Klant | sc-domain:oudeklant.nl | nee |

   * **Property** neem je precies over uit Search Console. Domeinproperty: `sc-domain:voorbeeld.nl`. URL-prefix: `https://www.voorbeeld.nl/` (met slash aan het eind).
   * **Actief** mag leeg blijven (telt als actief). Met `nee` sluit je een klant uit.
   * De volgorde van de kolommen maakt niet uit, de kopteksten wel.
2. Deel de Sheet met het service account als **Lezer**.
3. Het Sheet-ID staat in de URL: `https://docs.google.com/spreadsheets/d/`**`DIT_IS_HET_ID`**`/edit`.

### 4a. Claude Code op het web

De server staat in `.mcp.json`, dus elke cloudsessie op deze repository start hem automatisch. De sleutel komt **niet** in de sessie: de proxy van de cloudomgeving voegt het Google-token toe.

Open de cloudomgeving (menu in de titelbalk van een sessie, dan het tandwiel bij de omgeving) en stel in:

1. **Network secrets > Add secret**
   * Secret type: **GCP access token (with Service Account Key)**
   * Service account key: de inhoud van het JSON-sleutelbestand
   * Scopes: `https://www.googleapis.com/auth/webmasters.readonly` en, bij gebruik van de Sheet, `https://www.googleapis.com/auth/spreadsheets.readonly`
   * Allowed websites: `*.googleapis.com`
2. **Environment variables** (alleen bij gebruik van de Sheet): `GSC_CLIENTS_SHEET_ID=DIT_IS_HET_ID`
3. **Network access**: `*.googleapis.com` moet bereikbaar zijn. Bij het niveau Limited zet je het bij Allowed domains.

Start daarna een **nieuwe** sessie en vraag: *"Toon alle klanten en of de GSC-toegang werkt."*

Het secret type GCP access token vraagt op Team en Enterprise een organisatiebeheerder; zonder die rol toont het formulier alleen een kortere variant. Zie [Cloud environments](https://code.claude.com/docs/en/cloud-environments#add-network-secrets).

### 4b. Claude Code op je eigen computer

Je hebt [uv](https://docs.astral.sh/uv/) nodig. Start Claude Code in deze repository met de sleutel in een omgevingsvariabele:

```bash
export GSC_CREDENTIALS_PATH="$HOME/.config/gsc/service_account.json"
export GSC_CLIENTS_SHEET_ID="DIT_IS_HET_ID"   # optioneel
claude
```

`.mcp.json` start de server dan met het sleutelbestand. Een ingesteld sleutelbestand gaat altijd voor op de proxymodus.

## Instellingen

| Variabele | Standaard | Uitleg |
|---|---|---|
| `GSC_AUTH_VIA_PROXY` | `1` via `.mcp.json` | Geen sleutel in de sessie, de proxy voegt het token toe |
| `GSC_CREDENTIALS_PATH` | leeg | Pad naar de JSON-sleutel; gaat voor op de proxymodus |
| `GSC_READ_ONLY` | `1` | Leesscope en geen schrijftools. Zet op `0` om schrijftools aan te bieden |
| `GSC_ALLOW_DESTRUCTIVE` | `false` | Upstream: verwijdertools inschakelen (alleen relevant met `GSC_READ_ONLY=0`) |
| `GSC_CLIENTS_SHEET_ID` | leeg | ID van de klanten-Sheet |
| `GSC_CLIENTS_SHEET_RANGE` | `Klanten!A:C` | Tabblad en bereik |
| `GSC_CLIENTS_CSV` | leeg | Alternatief voor de Sheet: pad naar een CSV (`klanten.csv` staat in `.gitignore`) |
| `GSC_CLIENTS_CACHE_SECONDS` | `300` | Hoe lang de klantenlijst wordt onthouden |
| `GSC_DATA_STATE` | `all` | Upstream: `all` komt overeen met het GSC-dashboard, `final` alleen definitieve data |

## Ontwikkelen

```bash
uv run pytest
```

De tests draaien zonder Google-account; alle Google-aanroepen zijn nagebootst. `test_gsc_server.py` is de testset van upstream, `test_mpower_gsc.py` test onze laag.
