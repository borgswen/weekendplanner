# Weekendplanner

De weekendplanner kijkt in jullie twee agenda's wanneer jullie allebei vrij zijn: een weekend, een los dagje, of een periode die je zelf kiest. Claude Code maakt daar een concreet plan voor:
- echte trein- en Flixbusverbindingen met prijzen en een boekingslink, met een advies welke optie je het best kunt nemen. De treinprijzen komen van de eigen service [treinprijzen](treinprijzen/README.md): per verbinding de prijs bij bahn.de, NS International, ÖBB, NS, SBB (open data) en SNCF (open data), voor reizen in en naar NL, BE, LU, DE, AT, CH en FR;
- 2-3 echte slaapplekken met links, plus zoeklinks naar Booking, Airbnb en Hostelworld met de datums al ingevuld;
- een programma per dag, met foto's van Wikimedia Commons.

Het voorstel komt als ntfy-melding op je telefoon, met de knoppen 👍, 👎 en 🔁 Ander idee.

```
iCal (ik + vriendin) ─┐                                   ┌─ trein  (treinprijzen: DB, NSI, ÖBB, NS)
Open-Meteo (weer) ────┼─► vrij blok + passende ideeën ─► claude -p ─┼─ flixbus (echte ritten + prijzen)
config (ideeën, budget)┘          ▲                       ├─ websearch (hotels, Airbnb, activiteiten)
                     👍/👎 + genegeerde afspraken          └─► plan + foto's ─► ntfy + webpagina
```

## Webinterface (poort 8088)

- **Voorstellen:** de eerstvolgende vrije momenten (met de knop "Maak voorstel") en alle voorstellen tot nu toe.
- **Agenda:** een maandoverzicht van beide agenda's. Vrije weekenden zijn groen, vrije losse dagen lichtgroen.
  - Klik op een dag om een begin te kiezen en op een tweede dag voor het eind. Dat werkt ook doordeweeks.
  - Je kunt een **extra wens** opgeven, bijvoorbeeld "iets met sauna" of "we willen naar Gent".
  - Klik op een afspraak om hem **te negeren**: alleen die ene keer, of altijd bij die titel. Handig voor herinneringen zoals "stofzuigen niet vergeten".
- **Instellingen:** budget en maximale reistijd per soort uitje (dagje, 1 nacht, 2+ nachten), voorkeuren, wanneer er automatisch voorstellen komen, en de volledige YAML met de ideeënlijst.

Automatische voorstellen komen op twee momenten:
- **Zondag:** voor het eerstvolgende vrije weekend over 2 tot 6 weken.
- **Woensdag:** last-minute, voor het komende weekend of een vrij dagje, met de echte weersverwachting.

## Installeren met Portainer (vanuit deze repo)

1. **Stack aanmaken:** ga in Portainer naar Stacks → Add stack → **Repository**.
   - Repository URL: `https://github.com/borgswen/weekendplanner`
   - Authentication: aan. Gebruik je GitHub-gebruikersnaam en een *fine-grained personal access token* met alleen "Contents: Read-only" op deze repo.
   - Compose path: `docker-compose.yml`
2. **Omgevingsvariabelen** van de stack invullen:
   - `CLAUDE_CODE_OAUTH_TOKEN`: maak je aan met `claude setup-token` in de console van de container.
   - `ICAL_IK` en `ICAL_VRIENDIN`: in Google Agenda via Instellingen → agenda → "Geheim adres in iCal-indeling".
   - `NTFY_TOPIC`
   - Optioneel: `PUBLIEKE_URL` (standaard `http://192.168.68.125:8088`) en `DATA_DIR` (standaard `/opt/weekendplanner/data`, waar de data van versie 1 al staat).
   - Optioneel voor betere treinprijzen: `LEEFTIJDEN` (bijv. `22,23`), `STUDENTENOV` (bijv. `weekend,weekend`) en `NS_API_KEY`. Zie [treinprijzen/README.md](treinprijzen/README.md).
3. **Deploy.**
4. **Updaten:** open de stack en klik **Pull and redeploy**. Of zet "Automatic updates" aan, dan haalt Portainer nieuwe versies zelf op.

De instellingen staan in `data/config.yaml` en pas je aan in de webinterface. De `config.yaml` in deze repo is alleen de standaard voor de eerste start.

## Handig in de console van de container

```bash
python -m planner vrij                                    # vrije weekenden en dagjes
python -m planner nu --van 2026-12-11T16:00 --tot 2026-12-13T19:00 --wens "iets met een kerstmarkt"
python -m planner testmelding
python -m planner.reistools --test Delft Gent 2026-12-11T16:00   # test trein- en Flixbus-zoeken
node -e "fetch('http://treinprijzen:8089/reizen?van=Delft&naar=Keulen&vertrek=2026-12-11T16:00&personen=2').then(r=>r.text()).then(console.log)"   # treinprijzen direct
claude -p "zeg hoi"                                       # werkt het Claude-token?
```

## Goed om te weten

- **Wat Claude mag:** alleen zoeken, webpagina's lezen en de reistools gebruiken (trein, Flixbus, boekingslinks). Het kan niets boeken.
- **Treinen:** de stack draait ook de container `treinprijzen` (poort 8089). Die haalt eerst de dienstregeling op en zoekt dan per verbinding de prijs bij bahn.de, NS International, ÖBB en NS, inclusief wat jullie studentenreisproduct scheelt. Is die service even niet bereikbaar, dan valt de planner terug op de openbare DB-dienstregeling (v6.db.transport.rest) en markeert Claude geschatte prijzen als schatting.
- **Foto's:** komen van Wikimedia Commons, met maker en licentie op de pagina.
- **Prijzen** worden opgezocht op het moment dat het voorstel gemaakt wordt. Check ze even voordat je boekt.
- **Fouten:** gaat er iets mis, zoals een verlopen token of een agenda die niet bereikbaar is, dan krijg je een ntfy-melding.
