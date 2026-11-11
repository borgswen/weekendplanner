"""JSON-opslag voor voorstellen, feedback, genegeerde afspraken en laatst-gedraaide taken."""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime


class Store:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(path):
            self._write({})
        self.bezig: dict[str, str] = {}          # taak-id → omschrijving (alleen in geheugen)

    # ---------------------------------------------------------------- basis
    def _read(self) -> dict:
        with open(self.path, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("voorstellen", {})
        d.setdefault("laatst_gedraaid", {})
        d.setdefault("negeer", {"afspraken": {}, "titels": []})
        return d

    def _write(self, data: dict):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _update(self, fn):
        with self._lock:
            d = self._read()
            res = fn(d)
            self._write(d)
            return res

    # ---------------------------------------------------------- voorstellen
    def add(self, blok: dict, blok_key: str, modus: str, plan: dict, kosten_usd: float | None,
            fotos: list | None = None) -> str:
        vid = secrets.token_urlsafe(6)

        def f(d):
            d["voorstellen"][vid] = {"id": vid, "versie": 2, "aangemaakt": datetime.now().isoformat(timespec="minutes"),
                                     "modus": modus, "blok": blok, "blok_key": blok_key, "plan": plan,
                                     "fotos": fotos or [], "feedback": None, "claude_kosten_usd": kosten_usd}
        self._update(f)
        return vid

    def get(self, vid: str) -> dict | None:
        return _compat(self._read()["voorstellen"].get(vid))

    def all(self) -> list[dict]:
        return sorted((_compat(v) for v in self._read()["voorstellen"].values()),
                      key=lambda v: v["aangemaakt"], reverse=True)

    def for_key(self, key: str) -> list[dict]:
        return [v for v in self.all() if v["blok_key"] == key]

    def set_feedback(self, vid: str, waarde: str) -> bool:
        def f(d):
            if vid not in d["voorstellen"]:
                return False
            d["voorstellen"][vid]["feedback"] = waarde
            return True
        return self._update(f)

    def history_for_prompt(self, n: int = 12) -> list[dict]:
        out = []
        for v in self.all()[:n]:
            p = v["plan"]
            fb = {"up": "👍", "down": "👎"}.get(v["feedback"], "geen reactie")
            out.append({"wanneer": v["blok"]["vertrek"][:10], "idee": p.get("idee_id"),
                        "titel": p.get("titel"), "bestemming": p.get("bestemming"), "feedback": fb})
        return out

    # ------------------------------------------------------------ negeren
    def negeer(self) -> dict:
        return self._read()["negeer"]

    def negeer_afspraak(self, key: str, omschrijving: str):
        self._update(lambda d: d["negeer"]["afspraken"].__setitem__(key, omschrijving))

    def negeer_titel(self, titel: str):
        def f(d):
            if titel.lower() not in (t.lower() for t in d["negeer"]["titels"]):
                d["negeer"]["titels"].append(titel)
        self._update(f)

    def herstel(self, key: str | None = None, titel: str | None = None):
        def f(d):
            if key:
                d["negeer"]["afspraken"].pop(key, None)
            if titel:
                d["negeer"]["titels"] = [t for t in d["negeer"]["titels"] if t.lower() != titel.lower()]
        self._update(f)

    # -------------------------------------------------------------- taken
    def last_run(self, taak: str) -> str | None:
        return self._read()["laatst_gedraaid"].get(taak)

    def set_last_run(self, taak: str, dag: str):
        self._update(lambda d: d["laatst_gedraaid"].__setitem__(taak, dag))


def _compat(v: dict | None) -> dict | None:
    """Voorstellen uit versie 1 (met 'weekend') omzetten naar het blokformaat."""
    if not v or "blok" in v:
        return v
    w = v.get("weekend", {})
    v = dict(v)
    v["blok"] = {"soort": "weekend", "vertrek": w["vertrek"], "terug": w["terug"], "nachten": w["nachten"],
                 "omheen": w.get("omheen", []), "notitie": "", "conflicten": []}
    v["blok_key"] = w["vrijdag"]
    v.setdefault("fotos", [])
    v.setdefault("versie", 1)
    return v
