"""Ideeën filteren op soort reis, reistijd, seizoen, lengte en weer."""
from __future__ import annotations

from .calendars import Blok
from .weather import Weather, voldoet


def candidates(cfg: dict, blok: Blok, modus: str, weather: Weather,
               uitsluiten_ids: set[str] = frozenset()) -> tuple[list[dict], list[str]]:
    """Geeft (kandidaten met weer erbij, redenen waarom andere afvielen)."""
    reissoort = blok.reissoort
    max_uur = cfg["reizen"][reissoort]["max_reistijd_uur"]
    maand = blok.activiteitdagen[0].month
    kandidaten, afgevallen = [], []
    for idee in cfg["ideeen"]:
        naam = idee.get("titel", idee["id"])
        if idee["id"] in uitsluiten_ids:
            continue
        if reissoort not in idee.get("soorten", ["kort", "lang"]):
            continue
        if maand not in idee.get("maanden", range(1, 13)):
            continue
        if blok.nachten < idee.get("min_nachten", 0):
            afgevallen.append(f"{naam}: te kort ({blok.nachten} nacht)")
            continue
        if idee.get("reistijd_uur") and idee["reistijd_uur"] > max_uur:
            afgevallen.append(f"{naam}: reistijd ~{idee['reistijd_uur']} u is meer dan max {max_uur} u")
            continue
        weer = weather.for_days(idee.get("locatie"), blok.activiteitdagen)
        eisen = idee.get("weer")
        if idee.get("alleen_lastminute") and weer is None:
            if modus != "vooruit":
                afgevallen.append(f"{naam}: nog geen weersverwachting")
            continue
        if eisen and weer and not any(voldoet(d, eisen) for d in weer.values()):
            afgevallen.append(f"{naam}: weer past niet ({_kort(weer)})")
            continue
        kandidaat = {k: v for k, v in idee.items()
                     if k not in ("locatie", "actief", "maanden", "alleen_lastminute", "soorten")}
        if weer:
            kandidaat["weersverwachting"] = weer
        kandidaten.append(kandidaat)
    return kandidaten, afgevallen


def _kort(weer: dict) -> str:
    return "; ".join(f"{d[5:]}: {w['temp_max']:.0f}°C, {w['regen_mm']:.1f} mm, {w['wind_bft']} Bft"
                     for d, w in weer.items())
