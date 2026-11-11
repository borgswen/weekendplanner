"""Meldingen via ntfy."""
from __future__ import annotations

import json
import logging

import requests

from .calendars import Blok

log = logging.getLogger(__name__)


def _post(cfg: dict, payload: dict, dry_run: bool):
    n = cfg.get("ntfy", {})
    payload = {"topic": n.get("topic")} | payload
    if dry_run or not n.get("topic"):
        log.info("ntfy (niet verstuurd%s):\n%s", "" if dry_run else ", geen topic ingesteld",
                 json.dumps(payload, ensure_ascii=False, indent=2))
        return
    headers = {"Authorization": f"Bearer {n['token']}"} if n.get("token") else {}
    r = requests.post(n.get("server", "https://ntfy.sh").rstrip("/") + "/", json=payload, headers=headers, timeout=20)
    r.raise_for_status()


def _aanbevolen(opties: list[dict]) -> dict | None:
    return next((o for o in opties if o.get("aanbevolen")), opties[0] if opties else None)


def send_plan(cfg: dict, vid: str, voorstel: dict, dry_run: bool = False):
    p, base = voorstel["plan"], cfg.get("publieke_url", "").rstrip("/")
    blok = Blok.from_dict(voorstel["blok"])
    regels = [f"{blok.label()} · {blok.soort_label()}", p.get("samenvatting", ""), ""]
    if "vervoer" in p:
        v = _aanbevolen(p["vervoer"].get("opties", []))
        if v:
            regels.append(f"🚆 {v['omschrijving']} ({v['reistijd_enkel_min'] // 60:.0f}u{v['reistijd_enkel_min'] % 60:02.0f})")
        s = _aanbevolen(p.get("slapen", {}).get("opties", []))
        if s:
            regels.append(f"🛏 {s['naam']}")
    totaal = p.get("kosten", {}).get("totaal")
    if totaal is not None:
        regels.append(f"💶 ca. €{totaal:.0f} voor jullie samen")
    payload = {
        "title": p.get("titel", "Weekendidee"),
        "message": "\n".join(regels)[:3800],
        "tags": ["sunrise"] if voorstel["modus"] in ("lastminute", "handmatig") else ["calendar"],
        "click": f"{base}/plan/{vid}",
        "actions": [
            {"action": "http", "label": "👍 Leuk", "url": f"{base}/feedback/{vid}/up", "method": "POST", "clear": True},
            {"action": "http", "label": "👎 Niks", "url": f"{base}/feedback/{vid}/down", "method": "POST", "clear": True},
            {"action": "http", "label": "🔁 Ander idee", "url": f"{base}/opnieuw/{vid}", "method": "POST", "clear": True},
        ],
    }
    if voorstel.get("fotos"):
        payload["attach"] = voorstel["fotos"][0]["url"]
    _post(cfg, payload, dry_run)


def send_error(cfg: dict, tekst: str, dry_run: bool = False):
    try:
        _post(cfg, {"title": "Weekendplanner: er ging iets mis", "message": tekst[:3000],
                    "tags": ["warning"], "priority": 2}, dry_run)
    except Exception:
        log.exception("Kon foutmelding niet versturen")


def send_text(cfg: dict, titel: str, tekst: str, dry_run: bool = False):
    _post(cfg, {"title": titel, "message": tekst}, dry_run)
