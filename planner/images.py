"""Foto's bij een plan zoeken op Wikimedia Commons (vrij te gebruiken, met naamsvermelding)."""
from __future__ import annotations

import html
import logging
import re

import requests

log = logging.getLogger(__name__)
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "weekendplanner/2 (zelfgehost reisplanner)"}
_TAG = re.compile(r"<[^>]+>")


def _tekst(meta: dict, veld: str) -> str:
    return html.unescape(_TAG.sub("", (meta.get(veld) or {}).get("value", ""))).strip()


def zoek(zoekterm: str, n: int = 1, session=None) -> list[dict]:
    s = session or requests
    r = s.get(API, headers=UA, timeout=15, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{zoekterm} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": max(n * 3, 5), "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": 800})
    r.raise_for_status()
    pages = sorted((r.json().get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    out = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        if not info.get("thumburl") or info.get("width", 0) < 500:
            continue
        meta = info.get("extmetadata") or {}
        out.append({"url": info["thumburl"], "pagina": info.get("descriptionurl"),
                    "maker": _tekst(meta, "Artist")[:80] or "onbekend",
                    "licentie": _tekst(meta, "LicenseShortName") or "zie bron", "zoekterm": zoekterm})
        if len(out) >= n:
            break
    return out


def voor_plan(plan: dict, maximaal: int = 6) -> list[dict]:
    termen = [plan.get("foto_zoekterm") or plan.get("bestemming")]
    for dag in plan.get("programma", []):
        termen += [o.get("foto_zoekterm") for o in dag.get("onderdelen", [])]
    gezien, fotos = set(), []
    for t in termen:
        if not t or t.lower() in gezien or len(fotos) >= maximaal:
            continue
        gezien.add(t.lower())
        try:
            for f in zoek(t):
                if f["url"] not in {x["url"] for x in fotos}:
                    fotos.append(f)
        except Exception as e:
            log.warning("Foto zoeken mislukt voor %r: %s", t, e)
    return fotos
