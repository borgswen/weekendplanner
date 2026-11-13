"""Claude Code (claude -p) aanroepen om een concreet plan te maken, met de reistools als MCP-server."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date

import yaml

from .calendars import Blok, _dag

log = logging.getLogger(__name__)

S = {"type": "string"}
N = {"type": "number"}
B = {"type": "boolean"}


def _obj(req: list[str], **props) -> dict:
    return {"type": "object", "required": req, "properties": props}


SCHEMA = _obj(
    ["idee_id", "titel", "bestemming", "samenvatting", "waarom", "vervoer", "slapen", "programma", "kosten",
     "boeken_voor", "weer", "alternatief", "bronnen"],
    idee_id=S,
    titel={"type": "string", "description": "Pakkende titel, max ~60 tekens"},
    bestemming=S,
    foto_zoekterm={"type": "string", "description": "Engelse zoekterm voor een sfeerfoto van de bestemming op Wikimedia Commons"},
    samenvatting={"type": "string", "description": "2-3 zinnen die zin geven om te gaan"},
    waarom=S,
    vervoer=_obj(["advies", "opties"],
                 advies={"type": "string", "description": "Welke optie je aanraadt en waarom, in 1-2 zinnen"},
                 opties={"type": "array", "minItems": 1, "items": _obj(
                     ["soort", "omschrijving", "heen", "terug", "reistijd_enkel_min", "prijs_totaal_eur", "aanbevolen"],
                     soort={"type": "string", "enum": ["trein", "bus", "trein+bus", "auto", "auto+aanhanger",
                                                       "fiets", "brommer", "boot", "lopen"]},
                     omschrijving=S, heen=S, terug=S, reistijd_enkel_min=N, overstappen=N,
                     prijs_totaal_eur={"type": "number", "description": "Heen en terug, voor alle personen samen"},
                     prijs_is_schatting=B, boeken_url=S, aanbevolen=B)}),
    slapen=_obj(["opties"],
                plaats=S,
                zoeklinks={"type": "object", "additionalProperties": S},
                opties={"type": "array", "items": _obj(
                    ["naam", "soort", "prijs_totaal_eur", "waarom", "aanbevolen"],
                    naam=S, soort=S, plaats=S, prijs_totaal_eur=N, prijs_is_schatting=B, url=S, waarom=S,
                    aanbevolen=B)}),
    programma={"type": "array", "items": _obj(
        ["dag", "onderdelen"], dag=S,
        onderdelen={"type": "array", "items": _obj(
            ["wat"], tijd=S, wat=S, toelichting=S, kosten_eur=N, url=S,
            foto_zoekterm={"type": "string", "description": "Engelse zoekterm voor een foto van dit onderdeel (plek/bezienswaardigheid)"})})},
    kosten=_obj(["reis", "slapen", "activiteiten", "eten_drinken", "totaal"],
                reis=N, slapen=N, activiteiten=N, eten_drinken=N, totaal=N, toelichting=S),
    boeken_voor={"type": "string", "description": "Wat je wanneer moet boeken om deze prijs te halen"},
    weer=S,
    paklijst_tips=S,
    alternatief=_obj(["titel", "omschrijving", "totaal_eur"], titel=S, omschrijving=S, totaal_eur=N),
    bronnen={"type": "array", "items": _obj(["titel", "url"], titel=S, url=S)},
)


def budget(cfg: dict, blok: Blok) -> int:
    r = cfg["reizen"][blok.reissoort]
    extra = max(0, blok.nachten - 2) * r.get("extra_per_nacht_eur", 0)
    return int(r["budget_eur"] + extra)


# Richtingen om Claude uit de voor de hand liggende hoek te duwen (één per voorstel, willekeurig gekozen)
THEMAS = [
    "iets dat alleen precies dit weekend of dit seizoen kan (evenement, festival, markt, natuurfenomeen)",
    "een bijzondere overnachting (boomhut, vuurtoren, klooster, woonboot, trekkershut, kasteel, bivak)",
    "een activiteit die we waarschijnlijk nog nooit gedaan hebben (workshop, ambacht, nieuwe sport, proeverij)",
    "een plek die weinig Nederlanders kennen, net over de grens of juist in een vergeten hoek van Nederland",
    "water, maar anders: kano, sup, pont-hoppen, getijden, wadlopen, een rivier volgen",
    "eten en drinken als rode draad (markt, boerderij, streekproduct, brouwerij, foodhall, kookles)",
    "cultuur met een twist (bijzonder museum, industrieel erfgoed, street art, theater, concert in een rare zaal)",
    "rust en wellness (thermen, sauna, stilte, sterren kijken, natuurhuisje zonder wifi)",
    "een kleine expeditie: van A naar B lopen of fietsen in plaats van heen en terug",
    "de nacht: sterrenwacht, nachtwandeling, donkere-hemelgebied, lichtfestival, nachttrein",
    "geschiedenis om aan te raken: vestingstad, bunker, mijn, Romeinse resten, slagveld",
    "een stad die we niet zouden kiezen, maar met één heel goede reden om er nu heen te gaan",
]


def build_prompt(cfg: dict, blok: Blok, modus: str, kandidaten: list[dict],
                 afgevallen: list[str], geschiedenis: list[dict], deals: list[dict] | None = None, *,
                 lijst: bool = True, thema: str | None = None, al_voorgesteld: list[str] | None = None,
                 weer_thuis: dict | None = None) -> str:
    def dump(x):
        return yaml.safe_dump(x, allow_unicode=True, sort_keys=False, width=110).strip()

    r = cfg["reizen"][blok.reissoort]
    personen = cfg.get("personen", 2)
    thuis = cfg.get("thuis", "Delft")
    slapen = "" if blok.nachten == 0 else f"""
- Slapen: zoek 2-3 echte, concrete opties voor precies deze nachten (hotel, hostel met tweepersoonskamer, B&B,
  Airbnb, natuurhuisje, camping) via WebSearch/WebFetch, met de echte prijs voor het hele verblijf en een link
  naar die specifieke accommodatie. Markeer er één als aanbevolen. Roep ook `slaap_links` aan voor de
  overnachtingsplaats en zet die links in slapen.zoeklinks."""
    wens = f"\n# Onze wens (heeft voorrang op alles hieronder)\n{blok.notitie.strip()}\n" if blok.notitie.strip() else ""
    eerder_hier = ("\n# Voor deze periode al voorgesteld (kom met iets totaal anders, andere plek én ander soort uitje)\n"
                   + "\n".join("- " + t for t in al_voorgesteld) + "\n") if al_voorgesteld else ""
    weer = ("\n# Weersverwachting rond huis (ter indicatie)\n" + dump(weer_thuis) + "\n") if weer_thuis else ""
    if lijst:
        ideeen_blok = f"""# Ideeën uit onze eigen lijst die nu passen
{"Gebruik ze alleen als ze bij onze wens passen; de wens gaat voor." if blok.notitie.strip() else "Kies er één, of een slimme combinatie."}
{dump(kandidaten) if kandidaten else '- geen'}

Afgevallen ideeën (ter info): {'; '.join(afgevallen) if afgevallen else 'geen'}"""
        kies = "Kies wat nu het leukst én haalbaar is binnen budget en reistijd. Wissel af t.o.v. eerdere voorstellen."
    else:
        bekend = "; ".join(f"{i.get('titel', i['id'])}" for i in cfg.get("ideeen", []))
        ideeen_blok = f"""# Verras ons
We willen dat je buiten onze vaste ideeën denkt. Onze eigen ideeënlijst kennen we al, dus kies daar NIET uit en
ook niet de voor de hand liggende bestemmingen die erin genoemd worden. Ter info, zodat je onze smaak kent maar
er niet naar terugvalt: {bekend or '-'}.
Zoek iets wat wij zelf waarschijnlijk niet hadden bedacht, maar wel bij ons past. Gebruik WebSearch om te kijken
wat er op precies deze datums te doen is (agenda's van steden en regio's, evenementen, seizoensdingen).
Onze eigen spullen (boot, brommers) alleen als dat écht het beste idee is.
Richting om mee te beginnen (laat los als je iets veel beters vindt): {thema or 'vrij'}."""
        kies = ("Bedenk eerst in stilte minstens vijf heel verschillende opties (andere plekken én soorten uitjes), "
                "verwerp de voorspelbare en kies de verrassendste die binnen budget en reistijd past. "
                "Zet bij `idee_id` \"nieuw\". Leg in `waarom` uit waarom dit nu leuk is.")
    dcfg = {"aan": True, "sites": ["socialdeal.nl", "groupon.nl", "dagjeweg.nl"], **(cfg.get("deals") or {})}
    dealsites = ", ".join(dcfg["sites"])
    deal_blok = ""
    if dcfg.get("aan", True):
        deal_blok = ("\n# Lopende deals die we eerder vonden (gebruik er een als hij past bij plek, datum en ons)\n"
                     + (dump(deals) if deals else "- geen") + "\n")
    deal_stap = ("" if not dcfg.get("aan", True) else f"""
   Kijk voor de gekozen bestemming ook naar deals ({dealsites}): de lijst 'Lopende deals' hierboven en zelf zoeken met
   WebSearch, bv. `site:{dcfg['sites'][0]} <plaats>`. Gebruik een deal alleen als hij geldig is op onze datums en
   je hem met WebFetch hebt gecontroleerd; zet dan de dealprijs in `kosten_eur`, de deal-URL in `url` en in
   `toelichting` "deal, normaal €…".""")
    conflict = ("\nLet op, deze afspraken vallen in de gekozen periode (wij hebben gezegd dat dat oké is, maar "
                "houd er rekening mee):\n" + "\n".join("- " + c for c in blok.conflicten) + "\n") if blok.conflicten else ""

    return f"""Je bent een slimme, praktische reisplanner. Maak één concreet, boekbaar plan.

# Wie
{(cfg.get('voorkeuren') or '').strip()}

Vertrekpunt: {thuis}. Personen: {personen}.
Wat we zelf hebben:
{dump(cfg.get('middelen', []))}

# De periode
Vandaag is het {_dag(date.today())} {date.today().year}. Soort voorstel: {modus}.
Vrij: {blok.label()} → {blok.soort_label()}.
Budget: maximaal €{budget(cfg, blok)} voor ALLES samen (reis, slapen, activiteiten, huur, eten en drinken).
Maximale reistijd enkele reis: {r['max_reistijd_uur']} uur (deur tot deur). Ga hier niet overheen.
Afspraken rond deze periode (houd er rekening mee):
{chr(10).join('- ' + o for o in blok.omheen) if blok.omheen else '- geen'}
{conflict}{wens}{eerder_hier}{weer}
{ideeen_blok}
{deal_blok}
# Eerdere voorstellen (voorkom herhaling; 👍 = leuk gevonden, 👎 = niet)
{dump(geschiedenis) if geschiedenis else '- nog geen'}

# Werkwijze
1. {kies}
2. Vervoer: gebruik de tools `trein` en `flixbus` om ECHTE verbindingen met tijden en prijzen voor deze
   datums op te halen (vanaf {thuis}), voor heen- én terugreis apart. `trein` geeft per verbinding de prijzen
   van elke verkoper (bahn.de, NS International, ÖBB, NS) voor alle {personen} reizigers samen, en `goedkoopst`.
   Neem die prijs over met de boekingslink van díe verkoper. Een `deelprijs` dekt maar een deel van de reis;
   een prijs met `schatting` neem je over met `prijs_is_schatting` op true.
   Staat er bij een treinreis geen prijs, kijk dan bij `bronnen` waarom; schat dan en zet `prijs_is_schatting`
   op true. Met `trein_goedkoopste_dag` zie je welke dag goedkoper is (handig bij een flexibele vertrekdag).
   Vergelijk met de auto (brandstof, tol, parkeren; schat realistisch). Geef 2-4 opties met heen- en
   terugreis, reistijd, totaalprijs voor {personen} personen en een boekingslink. Markeer de aanbevolen
   optie en leg in `vervoer.advies` uit waarom.{slapen}
3. Programma per dag met tijden die passen bij vertrek en terugkomst; geef per onderdeel een
   `foto_zoekterm` (Engels, naam van de plek, bv. "Kahler Asten Winterberg") en waar mogelijk een url.{deal_stap}
4. Reken eerlijk: kosten.totaal ≤ budget. Eten en drinken realistisch voor studenten.
5. Geef alleen URL's die je echt gevonden of van een tool gekregen hebt.
6. Schrijf in het Nederlands, kort en concreet, zonder marketingtaal.
"""


def _mcp_config(workdir: str) -> str:
    path = os.path.join(workdir, "mcp.json")
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(path, "w") as f:
        json.dump({"mcpServers": {"reis": {"command": sys.executable, "args": ["-m", "planner.reistools"],
                                           "env": {"PYTHONPATH": app_dir,
                                                   "TREINPRIJZEN_URL": os.environ.get("TREINPRIJZEN_URL", "")}}}}, f)
    return path


def run_claude(cfg: dict, prompt: str, schema: dict, opdracht: str, mcp: bool = True) -> tuple[dict, float | None]:
    """Roept Claude Code aan (alleen zoeken, webpagina's lezen en de reistools) en geeft de JSON terug."""
    ccfg = cfg.get("claude", {})
    workdir = os.environ.get("CLAUDE_WORKDIR", "/data/claude-werkmap")
    os.makedirs(workdir, exist_ok=True)
    cmd = [
        os.environ.get("CLAUDE_BIN", "claude"), "-p", opdracht,
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--model", ccfg.get("model", "sonnet"),
        "--tools", "WebSearch,WebFetch",
        "--allowedTools", "WebSearch,WebFetch" + (",mcp__reis" if mcp else ""),
        "--permission-mode", "dontAsk",
    ]
    if mcp:
        cmd += ["--mcp-config", _mcp_config(workdir), "--strict-mcp-config"]
    log.info("Claude wordt aangeroepen (%s)…", ccfg.get("model", "sonnet"))
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=workdir,
                       timeout=int(ccfg.get("timeout_min", 20)) * 60)
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Claude gaf geen JSON terug (exit {p.returncode}): {(p.stdout or p.stderr)[-800:]}")
    if out.get("is_error") or "structured_output" not in out:
        raise RuntimeError(f"Claude-run mislukt: {str(out.get('result') or out)[:800]}")
    return out["structured_output"], out.get("total_cost_usd")


def make_plan(cfg: dict, prompt: str) -> tuple[dict, float | None]:
    return run_claude(cfg, prompt, SCHEMA,
                      "Maak het plan volgens de meegestuurde instructies. Lever het resultaat in het gevraagde JSON-formaat.")
