# mPower GSC MCP

Eigen MCP-server waarmee Claude Code Google Search Console-data van **alle klanten** kan bevragen. Welke klanten er zijn, staat in één Google Sheet. Een klant toevoegen is een rij toevoegen.

De server heeft alleen leesrechten: hij kan niets indienen, verwijderen of wijzigen in Search Console of in de Sheet.

## Tools

| Tool | Wat het doet |
|---|---|
| `list_clients` | Alle klanten uit de Sheet, met per klant of het service account toegang heeft |
| `search_analytics` | Clicks, impressies, CTR (in %) en positie per query, pagina, land, apparaat, datum of zoekweergave, met filters |
| `inspect_url` | Indexeringsstatus van één URL (URL Inspection API) |
| `list_sitemaps` | Ingediende sitemaps met status, fouten en waarschuwingen |

Elke tool krijgt een `client` mee: de klantnaam (een uniek deel van de naam is genoeg) of de property.

Zonder datums gebruikt `search_analytics` de laatste 28 dagen tot en met 3 dagen geleden, omdat de meest recente dagen in Search Console vaak nog niet definitief zijn.

## Eenmalige installatie

### 1. Google Cloud

1. Maak in [Google Cloud Console](https://console.cloud.google.com/) een project aan, bijvoorbeeld `mpower-gsc-mcp`.
2. Zet onder *APIs & Services* deze twee API's aan: **Google Search Console API** en **Google Sheets API**.
3. Maak onder *IAM & Admin > Service Accounts* een service account aan.
4. Maak bij dat account een sleutel van het type **JSON** en bewaar die buiten deze repository, bijvoorbeeld in `~/.config/gsc/service_account.json`. Commit de sleutel nooit.

### 2. De klanten-Sheet

1. Maak een Google Sheet met een tabblad `Klanten` en deze kolommen:

   | Klant | Property | Actief |
   |---|---|---|
   | Voorbeeld BV | sc-domain:voorbeeld.nl | ja |
   | Demo Webshop | https://www.demowebshop.nl/ | ja |
   | Oude Klant | sc-domain:oudeklant.nl | nee |

   * **Property** neem je precies over uit de propertykiezer in Search Console. Domeinproperty: `sc-domain:voorbeeld.nl`. URL-prefix: `https://www.voorbeeld.nl/` (met slash aan het eind).
   * **Actief** mag leeg blijven (telt als actief). Met `nee` sluit je een klant uit zonder de rij te verwijderen.
   * De volgorde van de kolommen maakt niet uit, de kopteksten wel.
2. Deel de Sheet met het e-mailadres van het service account (eindigt op `iam.gserviceaccount.com`), met de rol **Lezer**.
3. Kopieer het Sheet-ID uit de URL: `https://docs.google.com/spreadsheets/d/`**`DIT_IS_HET_ID`**`/edit`.

Zie `klanten.voorbeeld.csv` voor een voorbeeld.

### 3. Per klant: toegang in Search Console

Ga in Search Console per property naar *Instellingen > Gebruikers en rechten* en voeg het service account toe met het recht **Beperkt**. Met `list_clients` zie je daarna per klant of de toegang werkt.

### 4a. Claude Code op het web (claude.ai/code)

De server staat al in `.mcp.json`, dus elke cloudsessie op deze repository start hem automatisch. De sleutel komt **niet** in de sessie: de proxy van de cloudomgeving voegt het toegangstoken toe.

Open de cloudomgeving (menu in de titelbalk van de sessie, daarna het tandwiel bij de omgeving) en stel in:

1. **Network secrets > Add secret**
   * Secret type: **GCP access token (with Service Account Key)**
   * Service account key: de inhoud van het JSON-sleutelbestand
   * Scopes: `https://www.googleapis.com/auth/webmasters.readonly` en `https://www.googleapis.com/auth/spreadsheets.readonly`
   * Allowed websites: `*.googleapis.com`
2. **Environment variables**: voeg toe `GSC_CLIENTS_SHEET_ID=DIT_IS_HET_ID`
3. **Network access**: `*.googleapis.com` moet bereikbaar zijn. Gebruik je het niveau Limited, zet het dan bij Allowed domains.

Start daarna een **nieuwe** sessie en vraag: *"Toon alle klanten en of de GSC-toegang werkt."*

Netwerkgeheimen vragen op Team en Enterprise een organisatiebeheerder. Zie [Cloud environments](https://code.claude.com/docs/en/cloud-environments#add-network-secrets).

### 4b. Claude Code op je eigen computer

Je hebt [uv](https://docs.astral.sh/uv/) nodig. Clone deze repository en voer daarna dit commando uit (pas de paden en het Sheet-ID aan):

```bash
claude mcp add mpower-gsc-lokaal --scope user \
  -e GOOGLE_APPLICATION_CREDENTIALS=$HOME/.config/gsc/service_account.json \
  -e GSC_CLIENTS_SHEET_ID=DIT_IS_HET_ID \
  -- uv run --directory /pad/naar/mpower-nieuw-project mpower-gsc-mcp
```

Start Claude Code, controleer met `/mcp` of `mpower-gsc-lokaal` verbonden is (de andere naam voorkomt een conflict met de webversie uit `.mcp.json`), en vraag bijvoorbeeld: *"Toon alle klanten en of de GSC-toegang werkt."*

## Dagelijks gebruik: een klant toevoegen

1. Voeg in Search Console het service account toe aan de property van de klant (recht: Beperkt).
2. Voeg een rij toe aan de Sheet.

De server leest de Sheet maximaal elke 5 minuten opnieuw. Wil je dat direct, vraag Claude dan om `list_clients` met `refresh` aan te roepen.

## Instellingen

| Variabele | Verplicht | Uitleg |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | ja, of de volgende | Pad naar de JSON-sleutel |
| `GSC_SERVICE_ACCOUNT_JSON` | alternatief | De inhoud van de JSON-sleutel als tekst (handig in omgevingen zonder bestanden) |
| `GSC_AUTH_VIA_PROXY` | alternatief | `1`: geen sleutel in de sessie, de proxy voegt het token toe (standaard aan via `.mcp.json`) |
| `GSC_CLIENTS_SHEET_ID` | ja, of de volgende | ID van de klanten-Sheet |
| `GSC_CLIENTS_CSV` | alternatief | Pad naar een lokale CSV met dezelfde kolommen (`klanten.csv` staat in `.gitignore`) |
| `GSC_CLIENTS_SHEET_RANGE` | nee | Standaard `Klanten!A:C` |
| `GSC_CLIENTS_CACHE_SECONDS` | nee | Standaard `300` |

## Ontwikkelen

```bash
uv run --extra dev pytest
```

De tests draaien zonder Google-account: ze gebruiken een nagebootste Search Console.
