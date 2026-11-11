# Treinprijzen

Een kleine API die treinverbindingen mét prijzen geeft, voor Nederland, België, Luxemburg, Duitsland, Oostenrijk, Zwitserland en Frankrijk, zodat de weekendplanner de trein eerlijk kan vergelijken met de auto. Hij draait als tweede container naast de weekendplanner. Je kunt hem ook zelf gebruiken via `http://192.168.68.125:8089/`.

## Hoe het werkt

Eerst haalt hij de dienstregeling op, daarna zoekt hij per verbinding de prijs op bij de verkopers die die reis verkopen:

```
van, naar, tijd ─► dienstregeling (DB Navigator: heel Europa)
                       │
                       ├─► bahn.de-prijs (DB Navigator, bij dezelfde zoekvraag)
                       ├─► NS International (reizen tussen NL/BE en het buitenland), gekoppeld op vertrek- en aankomsttijd
                       ├─► ÖBB (reizen van/naar/door Oostenrijk, Nightjets, ook naar Zwitserland), idem
                       ├─► NS (binnenland, officiële NS-API) + studentenreisproduct
                       ├─► NMBS (België binnenland): schatting op basis van de kilometertarieven
                       └─► Luxemburg binnenland: gratis
                   ─► per verbinding alle prijzen + de goedkoopste
```

| Bron | Wat | Nodig |
|---|---|---|
| **bahn.de** (DB Navigator, via [db-vendo-client](https://github.com/public-transport/db-vendo-client)) | Dienstregeling voor alles, prijzen voor Duitsland en veel grensoverschrijdende reizen. Ook de goedkoopste reizen van een hele dag. | niets |
| **NS International** | Internationale prijzen vanuit Nederland en België, naar Duitsland, België, Frankrijk (Eurostar), Zwitserland en Oostenrijk (Nightjet) | niets |
| **ÖBB** (shop.oebbtickets.at) | Oostenrijk, Nightjets en reizen via Oostenrijk. Prijs per persoon × aantal reizigers. | niets |
| **NS** | Binnenlandse prijzen | gratis sleutel (`NS_API_KEY`), zie hieronder |
| **Studentenreisproduct** | Rekent uit wat een binnenlandse reis kost met jullie week- of weekendabonnement (gratis, 40% korting of vol) | `STUDENTENOV` |
| **NMBS** (België binnenland) | Een **schatting**: de NMBS rekent per kilometer (max. €20,90), met 40% korting onder 26 jaar en 30% in het weekend. De afstand schatten we uit de coördinaten. Staat gemarkeerd met `schatting: true`. | |
| **Zwitserland / Frankrijk binnenland** | Nog geen prijzen, wel een link naar SBB of SNCF Connect. Internationale reizen erheen krijgen wel prijzen (bahn.de, NS International, ÖBB). | |

Alle prijzen zijn **voor alle reizigers samen, enkele reis**, op het moment van opvragen. Prijzen worden 30 minuten bewaard. Per site gaat er hooguit één vraag per seconde (bahn.de), per 1,5 seconde (ÖBB) of per 2,5 seconde (NS International) de deur uit.

Lukt een bron niet, dan staat dat bij `bronnen`, bijvoorbeeld `"NS International": "geblokkeerd: ..."`. De andere prijzen en de zoeklinks werken dan gewoon.

## Endpoints

```bash
# Verbindingen met prijzen (of aankomst= in plaats van vertrek=)
curl 'http://192.168.68.125:8089/reizen?van=Delft&naar=Keulen&vertrek=2026-12-11T16:00&personen=2'

# De goedkoopste DB-reizen van één dag
curl 'http://192.168.68.125:8089/dagprijzen?van=Delft&naar=Berlijn&datum=2026-12-11&personen=2'

# Per dag de laagste prijs in een periode (max. 14 dagen)
curl 'http://192.168.68.125:8089/goedkoopste-dag?van=Delft&naar=Winterberg&van_datum=2026-12-11&tot_datum=2026-12-13'

# Stations zoeken
curl 'http://192.168.68.125:8089/stations?q=Winterberg'
```

Extra opties: `leeftijden=22,23` (DB geeft onder de 27 jaar jongerenprijzen), `klasse=1`, `studentenov=weekend,week`, `aantal=5`. Zonder `leeftijden` of `studentenov` gelden de instellingen hieronder.

Een stukje antwoord van `/reizen`:

```json
{
  "vertrek": "2026-12-11T16:20:00+01:00", "aankomst": "2026-12-11T19:40:00+01:00",
  "duur_min": 200, "overstappen": 1, "landen": ["NL", "DE"],
  "ritten": [{"trein": "IC 2245", "van": "Delft", "naar": "Utrecht Centraal", ...}, ...],
  "prijzen": [
    {"bron": "bahn.de", "totaal_eur": 79.98, "per_persoon_eur": 39.99, "deelprijs": false, "boeken": "https://int.bahn.de/..."},
    {"bron": "NS International", "totaal_eur": 69.98, "per_persoon_eur": 34.99, "tarief": "Second Class", "flexibel": "nee", "boeken": "https://www.nsinternational.com/..."}
  ],
  "goedkoopst": {"bron": "NS International", "totaal_eur": 69.98, "per_persoon_eur": 34.99}
}
```

`deelprijs: true` betekent dat die verkoper maar een deel van de reis verkoopt. Zo'n prijs telt niet mee voor `goedkoopst`.

## Instellingen (omgevingsvariabelen van de stack)

| Variabele | Voorbeeld | Waarvoor |
|---|---|---|
| `LEEFTIJDEN` | `22,23` | Standaard reizigers. Zonder deze instelling rekent hij met volwassenen. |
| `STUDENTENOV` | `weekend,weekend` | Studentenreisproduct per reiziger, in dezelfde volgorde: `weekend`, `week` of `geen`. |
| `NS_API_KEY` | | Binnenlandse NS-prijzen. Maak een gratis account op [apiportal.ns.nl](https://apiportal.ns.nl), abonneer je op het product met de Reisinformatie-API (heet meestal **Ns-App**) en kopieer de *primary key*. |
| `BRONNEN` | `db,nsi,ns,oebb` | Bronnen aan- of uitzetten. |
| `USER_AGENT` | | Hoe de service zich voorstelt aan de sites. |

## Testen

```bash
npm install && npm test
```

De tests gebruiken nagebootste antwoorden, plus een echt DB Navigator-antwoord uit de tests van db-vendo-client.

Of de echte bronnen werken, zie je door deze link in je browser te openen (op je thuisnetwerk):

<http://192.168.68.125:8089/reizen?van=Delft&naar=Keulen&vertrek=2026-12-11T16:00&personen=2>

Kijk dan vooral naar `bronnen` onderaan.

## Goed om te weten

- Deze service gebruikt dezelfde zoekvragen als de app en website van DB en NS International. Dat zijn geen officiële, openbare API's: ze kunnen veranderen of ons gaan weigeren. Daarom zijn er een rem en een cache, en is het bedoeld voor eigen gebruik.
- NS International en ÖBB rekenen met het volwassenentarief. Eventuele jongerenkorting zie je pas op hun site.
- ÖBB heeft botcontrole (Cloudflare). Weigert ÖBB, dan zie je `geblokkeerd` bij `bronnen`.
- De studentenreisproduct-regels komen van [studentenreisproduct.nl](https://www.studentenreisproduct.nl/en/productvoorwaarden/). Ze gelden alleen voor reizen binnen Nederland.
- `data/stations.json` koppelt DB-stations aan NS International-codes. Het komt uit de open [stationslijst van Trainline](https://github.com/trainline-eu/stations) (ODbL). Opnieuw maken: zie `scripts/maak_stations.py`.

## Later

- Echte prijzen voor reizen binnen Zwitserland (SBB) en Frankrijk (SNCF). Hun sites zijn lastig te bevragen.
- Officiële NMBS-prijzen in plaats van de schatting.
