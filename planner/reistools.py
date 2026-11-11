"""MCP-server met reistools voor Claude: echte trein- en busverbindingen plus boekingslinks.

Wordt door `claude -p` gestart via --mcp-config (stdio). Los testen:
    python -m planner.reistools --test "Delft" "Winterberg" 2026-12-11T16:00
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from urllib.parse import quote, urlencode

import requests

UA = {"User-Agent": "weekendplanner/2 (zelfgehost reisplanner)"}
DB = "https://v6.db.transport.rest"
FLIX = "https://global.api.flixbus.com"
# De eigen treinprijzen-service (zie treinprijzen/), in docker-compose: http://treinprijzen:8089
TREINPRIJZEN = os.environ.get("TREINPRIJZEN_URL", "").rstrip("/")


def _get(url, params=None, timeout=25):
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _min(a: str, b: str) -> int:
    return int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60)


# ------------------------------------------------------------- links ----------

def links_trein(van: str, naar: str, vertrek: str) -> dict:
    t = vertrek[:16]
    return {
        "ns_reisplanner": "https://www.ns.nl/reisplanner/#/?" + urlencode(
            {"vertrek": van, "aankomst": naar, "type": "vertrek", "tijd": t}),
        "ns_international": "https://www.nsinternational.com/nl",
        "bahn_de": "https://int.bahn.de/nl/buchung/fahrplan/suche#" + urlencode(
            {"sts": "true", "so": van, "zo": naar, "hd": t + ":00", "kl": "2"}, quote_via=quote),
    }


def links_slapen(plaats: str, aankomst: str, vertrek: str, personen: int = 2,
                 max_prijs_per_nacht: int | None = None) -> dict:
    booking = {"ss": plaats, "checkin": aankomst, "checkout": vertrek, "group_adults": personen,
               "no_rooms": 1, "group_children": 0, "order": "price"}
    if max_prijs_per_nacht:
        booking["nflt"] = f"price=EUR-min-{int(max_prijs_per_nacht)}-1"
    airbnb = {"checkin": aankomst, "checkout": vertrek, "adults": personen}
    if max_prijs_per_nacht:
        airbnb["price_max"] = int(max_prijs_per_nacht)
    return {
        "booking": "https://www.booking.com/searchresults.nl.html?" + urlencode(booking),
        "airbnb": f"https://www.airbnb.nl/s/{quote(plaats)}/homes?" + urlencode(airbnb),
        "hostelworld": "https://www.hostelworld.com/search?" + urlencode(
            {"search_keywords": plaats, "date_from": aankomst, "date_to": vertrek, "number_of_guests": personen}),
    }


# ------------------------------------------------------------ trein ----------

def _db_station(naam: str) -> dict:
    res = _get(f"{DB}/locations", {"query": naam, "results": 1, "addresses": "false", "poi": "false", "language": "nl"})
    if not res:
        raise ValueError(f"Station/plaats niet gevonden: {naam}")
    return res[0]


def _zoek_trein_db_rest(van: str, naar: str, vertrek: str, aankomst_voor: str | None = None, aantal: int = 4) -> dict:
    a, b = _db_station(van), _db_station(naar)
    params = {"from": a["id"], "to": b["id"], "results": aantal, "tickets": "true", "language": "nl",
              "stopovers": "false", "remarks": "false"}
    params["arrival" if aankomst_voor else "departure"] = aankomst_voor or vertrek
    data = _get(f"{DB}/journeys", params, timeout=40)
    reizen = []
    for j in data.get("journeys", []):
        legs = [l for l in j.get("legs", []) if not l.get("walking")]
        if not legs:
            continue
        start = legs[0].get("departure") or legs[0].get("plannedDeparture")
        eind = legs[-1].get("arrival") or legs[-1].get("plannedArrival")
        prijs = (j.get("price") or {}).get("amount")
        reizen.append({
            "vertrek": start, "aankomst": eind, "duur_min": _min(start, eind), "overstappen": len(legs) - 1,
            "ritten": [f"{(l.get('line') or {}).get('name', '?')}: {l['origin']['name']} "
                       f"{(l.get('departure') or l.get('plannedDeparture') or '')[11:16]} → "
                       f"{l['destination']['name']} {(l.get('arrival') or l.get('plannedArrival') or '')[11:16]}"
                       for l in legs],
            "prijs_p_p_eur": prijs, "prijsbron": "DB (indicatie, NS-prijzen ontbreken vaak)" if prijs else None,
        })
    return {"van": a["name"], "naar": b["name"], "reizen": reizen,
            "boeken": links_trein(a["name"], b["name"], aankomst_voor or vertrek)}


def _rit_kort(r: dict) -> str:
    return f"{r['trein']}: {r['van']} {(r.get('vertrek') or '')[11:16]} → {r['naar']} {(r.get('aankomst') or '')[11:16]}"


def zoek_trein_prijzen(van: str, naar: str, vertrek: str, aankomst_voor: str | None = None, aantal: int = 4,
                       personen: int = 2) -> dict:
    """Via de treinprijzen-service: dienstregeling plus de prijs bij elke verkoper (DB, NS International, NS)."""
    params = {"van": van, "naar": naar, "personen": personen, "aantal": aantal}
    params["aankomst" if aankomst_voor else "vertrek"] = (aankomst_voor or vertrek)[:16]
    data = _get(f"{TREINPRIJZEN}/reizen", params, timeout=120)
    reizen = []
    for r in data.get("reizen", []):
        reizen.append({
            "vertrek": r["vertrek"], "aankomst": r["aankomst"], "duur_min": r["duur_min"],
            "overstappen": r["overstappen"], "ritten": [_rit_kort(x) for x in r["ritten"]],
            "prijzen": [{k: p[k] for k in ("bron", "totaal_eur", "per_persoon_eur", "tarief", "flexibel", "deelprijs",
                                           "toelichting", "schatting", "boeken") if p.get(k) not in (None, "")} for p in r["prijzen"]],
            "goedkoopst": r.get("goedkoopst"),
            **({"uitgevallen": True} if r.get("uitgevallen") else {}),
        })
    return {"van": data.get("van"), "naar": data.get("naar"), "personen": personen, "reizen": reizen,
            "bronnen": data.get("bronnen"), "boeken": data.get("links"), "let_op": data.get("let_op")}


def zoek_trein(van: str, naar: str, vertrek: str, aankomst_voor: str | None = None, aantal: int = 4,
               personen: int = 2) -> dict:
    if TREINPRIJZEN:
        try:
            return zoek_trein_prijzen(van, naar, vertrek, aankomst_voor, aantal, personen)
        except Exception as e:  # service even niet bereikbaar: val terug op de openbare DB-dienstregeling
            res = _zoek_trein_db_rest(van, naar, vertrek, aankomst_voor, aantal)
            res["waarschuwing"] = f"treinprijzen-service gaf een fout ({type(e).__name__}: {e}); alleen DB-gegevens"
            return res
    return _zoek_trein_db_rest(van, naar, vertrek, aankomst_voor, aantal)


def goedkoopste_dag(van: str, naar: str, van_datum: str, tot_datum: str, personen: int = 2) -> dict:
    if not TREINPRIJZEN:
        return {"fout": "TREINPRIJZEN_URL is niet ingesteld"}
    return _get(f"{TREINPRIJZEN}/goedkoopste-dag", {"van": van, "naar": naar, "van_datum": van_datum[:10],
                                                     "tot_datum": tot_datum[:10], "personen": personen}, timeout=120)


# ----------------------------------------------------------- flixbus ----------

def _flix_stad(naam: str) -> dict:
    res = _get(f"{FLIX}/search/autocomplete/cities", {"q": naam, "lang": "nl", "flixbus_cities_only": "true"})
    if not res:
        raise ValueError(f"Geen Flixbus-stad gevonden voor: {naam}")
    return res[0]


def zoek_flixbus(van: str, naar: str, datum: str, personen: int = 2) -> dict:
    a, b = _flix_stad(van), _flix_stad(naar)
    d = datetime.fromisoformat(datum[:10]).strftime("%d.%m.%Y")
    data = _get(f"{FLIX}/search/service/v4/search", {
        "from_city_id": a["id"], "to_city_id": b["id"], "departure_date": d,
        "products": json.dumps({"adult": personen}), "currency": "EUR", "locale": "nl",
        "search_by": "cities", "include_after_midnight_rides": 1})
    stations = data.get("stations", {})
    ritten = []
    for trip in data.get("trips", []):
        for r in (trip.get("results") or {}).values():
            if r.get("status") != "available":
                continue
            ritten.append({
                "vertrek": r["departure"]["date"], "aankomst": r["arrival"]["date"],
                "van_halte": stations.get(r["departure"]["station_id"], {}).get("name"),
                "naar_halte": stations.get(r["arrival"]["station_id"], {}).get("name"),
                "duur_min": r["duration"]["hours"] * 60 + r["duration"]["minutes"],
                "overstappen": max(0, len(r.get("legs", [])) - 1),
                "vervoer": sorted({l.get("means_of_transport", "bus") for l in r.get("legs", [])}),
                "prijs_totaal_eur": (r.get("price") or {}).get("total_with_platform_fee") or (r.get("price") or {}).get("total"),
                "stoelen_vrij": (r.get("available") or {}).get("seats"),
            })
    ritten.sort(key=lambda x: x["vertrek"])
    link = "https://shop.flixbus.nl/search?" + urlencode({
        "departureCity": a["id"], "arrivalCity": b["id"], "rideDate": d, "adult": personen, "_locale": "nl"})
    return {"van": a["name"], "naar": b["name"], "personen": personen, "ritten": ritten[:8], "boeken": link}


# --------------------------------------------------------------- MCP ----------

def serve():
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer("reis", instructions="Echte trein- en busverbindingen met prijzen, en boekingslinks met ingevulde datums.")

    @srv.tool(description="Zoek treinverbindingen (NL, BE, LU, DE, AT, CH, FR) met tijden, overstappen en per "
                          "verbinding de prijzen van elke verkoper (bahn.de, NS International, ÖBB, NS, NMBS-schatting) "
                          "voor alle personen samen, enkele reis, plus de goedkoopste. Tijden ISO, bv. 2026-12-11T16:00.")
    def trein(van: str, naar: str, vertrek: str, aankomst_voor: str | None = None, aantal: int = 4,
              personen: int = 2) -> dict:
        try:
            return zoek_trein(van, naar, vertrek, aankomst_voor, aantal, personen)
        except Exception as e:
            return {"fout": f"{type(e).__name__}: {e}", "boeken": links_trein(van, naar, aankomst_voor or vertrek)}

    @srv.tool(description="Per dag de laagste treinprijs (DB/bahn.de, alle personen samen, enkele reis) in een "
                          "periode van max. 14 dagen (datums YYYY-MM-DD). Handig om de goedkoopste vertrekdag te kiezen.")
    def trein_goedkoopste_dag(van: str, naar: str, van_datum: str, tot_datum: str, personen: int = 2) -> dict:
        try:
            return goedkoopste_dag(van, naar, van_datum, tot_datum, personen)
        except Exception as e:
            return {"fout": f"{type(e).__name__}: {e}"}

    @srv.tool(description="Zoek Flixbus-ritten (bus en soms trein) op een datum (YYYY-MM-DD) met echte totaalprijs "
                          "voor het aantal personen en een boekingslink.")
    def flixbus(van: str, naar: str, datum: str, personen: int = 2) -> dict:
        try:
            return zoek_flixbus(van, naar, datum, personen)
        except Exception as e:
            return {"fout": f"{type(e).__name__}: {e}", "boeken": "https://www.flixbus.nl"}

    @srv.tool(description="Boekingslinks (Booking, Airbnb, Hostelworld) voor een plaats met aankomst- en vertrekdatum "
                          "(YYYY-MM-DD) al ingevuld, optioneel met maximumprijs per nacht.")
    def slaap_links(plaats: str, aankomst: str, vertrek: str, personen: int = 2,
                    max_prijs_per_nacht: int | None = None) -> dict:
        return links_slapen(plaats, aankomst, vertrek, personen, max_prijs_per_nacht)

    @srv.tool(description="Links naar NS-reisplanner, NS International en bahn.de met van/naar/tijd ingevuld.")
    def trein_links(van: str, naar: str, vertrek: str) -> dict:
        return links_trein(van, naar, vertrek)

    srv.run("stdio")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        van, naar, wanneer = sys.argv[2:5]
        print(json.dumps(zoek_trein(van, naar, wanneer), indent=2, ensure_ascii=False))
        print(json.dumps(zoek_flixbus(van, naar, wanneer), indent=2, ensure_ascii=False))
    else:
        serve()
