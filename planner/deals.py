"""Deals: houdt dealsites (Social Deal, Groupon, DagjeWeg.NL Tickets…) in de gaten voor leuke, goedkope uitjes.

Eén keer per week zoekt Claude op die sites naar deals die bij ons passen (zoals iemand die zelf even rondkijkt:
een paar zoekopdrachten en pagina's, geen massale scraping). De deals worden bewaard; goede nieuwe deals komen
als ntfy-melding, en de voorstellen gebruiken ze als ze passen.
"""
from __future__ import annotations

import logging
from datetime import date

import yaml

from . import claude, notify

log = logging.getLogger("deals")

STANDAARD = {
    "aan": True,
    "sites": ["socialdeal.nl", "groupon.nl", "dagjeweg.nl"],
    "zoek_naar": ("Uitjes voor ons tweeën: wellness of sauna, escape room, karten, klimmen of boulderen, suppen, "
                  "zeilen of kanoën, workshops, rondvaarten, musea, concerten of comedy, uit eten, en hotelovernachtingen "
                  "of arrangementen voor een weekendje weg."),
    "regio": "Delft en omgeving (Den Haag, Rotterdam, Leiden), en de plekken uit onze ideeënlijst",
    "melden_vanaf_korting": 40,
    "max_bewaren": 60,
}

S, N, B = {"type": "string"}, {"type": "number"}, {"type": "boolean"}
DEAL = {
    "type": "object",
    "additionalProperties": False,
    "required": ["titel", "site", "url", "plaats", "soort", "prijs_eur"],
    "properties": {
        "titel": S, "site": S, "url": S, "plaats": S,
        "soort": {"type": "string", "enum": ["uitje", "wellness", "eten", "overnachting", "cultuur", "sport", "anders"]},
        "prijs_eur": N, "van_prijs_eur": N, "korting_pct": N,
        "voor_personen": N, "geldig_tot": S, "beperkingen": S, "waarom": S,
    },
}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["deals"],
          "properties": {"deals": {"type": "array", "items": DEAL}}}


def instellingen(cfg: dict) -> dict:
    return {**STANDAARD, **(cfg.get("deals") or {})}


def _ideeen(cfg: dict) -> list[str]:
    """Onze ideeën (regio of titel), zodat Claude ook bij die bestemmingen naar deals zoekt."""
    uit = []
    for i in cfg.get("ideeen", []):
        if i.get("actief", True):
            t = str(i.get("regio") or i.get("titel") or "").strip()
            if t and t not in uit:
                uit.append(t)
    return uit


def build_scan_prompt(cfg: dict, bekende: list[dict]) -> str:
    d = instellingen(cfg)
    r = cfg.get("reizen", {})
    return f"""Zoek op dealsites naar leuke, goedkope uitjes die bij ons passen. Vandaag is het {date.today().isoformat()}.

# Wie
{(cfg.get('voorkeuren') or '').strip()}
Personen: {cfg.get('personen', 2)}. Woonplaats: {cfg.get('thuis', 'Delft')}.
Budget voor een dagje weg (alles samen): €{r.get('dagje', {}).get('budget_eur', 80)}; weekend: €{r.get('lang', {}).get('budget_eur', 400)}.

# Waar we naar zoeken
{d['zoek_naar'].strip()}

# Waar
{d['regio']}
Onze ideeën (zoek ook bij die bestemmingen): {'; '.join(_ideeen(cfg)) or 'geen'}

# Dealsites
{chr(10).join('- ' + s for s in d['sites'])}

# Werkwijze
1. Zoek per site met WebSearch, bijvoorbeeld `site:socialdeal.nl sauna Den Haag` of `site:groupon.nl escape room Rotterdam`.
   Doe hooguit zo'n 15 zoekopdrachten in totaal.
2. Open de beste kandidaten met WebFetch en controleer prijs, normale prijs, waar het is, tot wanneer de deal
   geldig is en of er beperkingen zijn (alleen doordeweeks, lidmaatschap nodig, enz.).
3. Geef 8-20 deals die nu te koop zijn en echt bij ons passen. Liefst voor 2 personen. Geen deals die je niet zelf
   hebt gecontroleerd, geen verzonnen URL's: alleen de URL van de dealpagina zelf.
4. `geldig_tot` als JJJJ-MM-DD (leeg als onbekend), `korting_pct` als getal (leeg als onbekend),
   `prijs_eur` voor het genoemde aantal personen (`voor_personen`), `waarom`: in één zin waarom het bij ons past.

Deals die we al kennen (alleen opnieuw opnemen als ze nog lopen):
{yaml.safe_dump([{'titel': b['titel'], 'url': b['url']} for b in bekende], allow_unicode=True) if bekende else '- geen'}
"""


def _sleutel(deal: dict) -> str:
    return deal["url"].split("?")[0].rstrip("/").lower()


def geldig(deal: dict, op: date | None = None) -> bool:
    op = op or date.today()
    tot = (deal.get("geldig_tot") or "").strip()
    if tot:
        try:
            return date.fromisoformat(tot[:10]) >= op
        except ValueError:
            pass
    # Zonder einddatum: houden zolang we hem de laatste 3 weken nog zagen
    gezien = deal.get("gezien")
    return not gezien or (date.today() - date.fromisoformat(gezien)).days <= 21


def samenvoegen(oud: dict[str, dict], nieuw: list[dict], max_bewaren: int) -> tuple[dict[str, dict], list[dict]]:
    vandaag = date.today().isoformat()
    alle = {k: v for k, v in oud.items() if geldig(v)}
    erbij = []
    for deal in nieuw:
        if not str(deal.get("url", "")).startswith("http"):
            continue
        k = _sleutel(deal)
        if k in alle:
            alle[k] = {**alle[k], **deal, "gezien": vandaag}
        else:
            alle[k] = {**deal, "gevonden": vandaag, "gezien": vandaag}
            erbij.append(alle[k])
    if len(alle) > max_bewaren:
        houden = sorted(alle.items(), key=lambda kv: kv[1].get("gezien", ""), reverse=True)[:max_bewaren]
        alle = dict(houden)
    return alle, erbij


def melding(cfg: dict, nieuwe: list[dict]) -> tuple[str, str] | None:
    drempel = instellingen(cfg)["melden_vanaf_korting"]
    goed = sorted((d for d in nieuwe if (d.get("korting_pct") or 0) >= drempel),
                  key=lambda d: -(d.get("korting_pct") or 0))[:3]
    if not goed:
        return None
    eur = lambda x: f"€{x:.2f}".replace(".", ",")  # noqa: E731
    regels = [f"• {d['titel']} ({d.get('plaats', '')}): {eur(d['prijs_eur'])}"
              + (f" i.p.v. {eur(d['van_prijs_eur'])}" if d.get("van_prijs_eur") else "")
              + (f", -{d['korting_pct']:.0f}%" if d.get("korting_pct") else "") for d in goed]
    return f"{len(goed)} leuke deal{'s' if len(goed) > 1 else ''} gevonden", "\n".join(regels)


def scan(app) -> int:
    """Zoekt nieuwe deals, slaat ze op en meldt de goede. Geeft het aantal nieuwe deals terug."""
    cfg = app.cfg
    d = instellingen(cfg)
    if not d.get("aan", True):
        log.info("Deals staan uit")
        return 0
    bekende = list(app.store.deals().values())
    resultaat, kosten = claude.run_claude(
        cfg, build_scan_prompt(cfg, bekende), SCHEMA,
        "Zoek de deals volgens de meegestuurde instructies. Lever het resultaat in het gevraagde JSON-formaat.", mcp=False)
    alle, nieuwe = samenvoegen(app.store.deals(), resultaat.get("deals", []), int(d["max_bewaren"]))
    app.store.set_deals(alle)
    log.info("Deals: %d gevonden, %d nieuw, %d bewaard (Claude: %s USD)", len(resultaat.get("deals", [])),
             len(nieuwe), len(alle), kosten)
    m = melding(cfg, nieuwe)
    if m:
        notify.send_text(cfg, m[0], m[1], app.dry_run,
                         klik=f"{str(cfg.get('publieke_url', '')).rstrip('/')}/deals")
    return len(nieuwe)


def voor_prompt(app, op: date, n: int = 15) -> list[dict]:
    """Bewaarde deals die op de vertrekdatum nog geldig zijn, de beste eerst, kort gemaakt voor de prompt."""
    lijst = [x for x in app.store.deals().values() if geldig(x, op)]
    lijst.sort(key=lambda x: -(x.get("korting_pct") or 0))
    velden = ("titel", "plaats", "soort", "prijs_eur", "van_prijs_eur", "voor_personen", "geldig_tot", "beperkingen", "url")
    return [{k: x[k] for k in velden if x.get(k) not in (None, "")} for x in lijst[:n]]
