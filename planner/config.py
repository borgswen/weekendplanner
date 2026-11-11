"""Config laden en opslaan.

- De standaardconfig zit in het image (/app/config.yaml).
- Bij de eerste start wordt die gekopieerd naar /data/config.yaml; die versie bewerk je in de webinterface.
- ${VAR} en ${VAR:-standaard} worden bij het laden ingevuld uit de omgeving (geheimen blijven in Portainer).
"""
from __future__ import annotations

import io
import os
import re
import shutil
from datetime import date, datetime, time

from ruamel.yaml import YAML

_ENV = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")
DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]

STANDAARD_REIZEN = {
    "dagje": {"budget_eur": 80, "max_reistijd_uur": 1.5},
    "kort": {"budget_eur": 300, "max_reistijd_uur": 3},
    "lang": {"budget_eur": 400, "max_reistijd_uur": 5, "extra_per_nacht_eur": 120},
}

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def _expand(v):
    if isinstance(v, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), v)
    if isinstance(v, list):
        return [_expand(x) for x in v]
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    return v


def _plain(v):
    """ruamel-objecten → gewone dicts/lists."""
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    for t in (bool, int, float, str):          # ScalarFloat, LiteralScalarString, ... → gewone types
        if isinstance(v, t):
            return t(v)
    return v


class ConfigStore:
    def __init__(self, standaard: str, data_dir: str):
        self.standaard = standaard
        self.path = os.path.join(data_dir, "config.yaml")
        if not os.path.exists(self.path):
            os.makedirs(data_dir, exist_ok=True)
            shutil.copyfile(standaard, self.path)

    def raw_text(self) -> str:
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def raw(self):
        with open(self.path, encoding="utf-8") as f:
            return _yaml.load(f)

    def load(self) -> dict:
        cfg = _expand(_plain(self.raw()))
        eigen = cfg.get("reizen") or {}
        reizen = {soort: {**std, **(eigen.get(soort) or {})} for soort, std in STANDAARD_REIZEN.items()}
        if "budget_eur" in cfg and "budget_eur" not in (eigen.get("lang") or {}):
            reizen["lang"]["budget_eur"] = cfg["budget_eur"]     # config van versie 1
        cfg["reizen"] = reizen
        cfg["ideeen"] = [i for i in cfg.get("ideeen", []) or [] if i.get("actief", True)]
        return cfg

    def validate_text(self, text: str) -> dict:
        data = _plain(_yaml.load(text))
        if not isinstance(data, dict):
            raise ValueError("De config moet een YAML-woordenboek zijn")
        if not isinstance(data.get("agendas"), list) or not data["agendas"]:
            raise ValueError("'agendas' ontbreekt")
        for i in data.get("ideeen", []) or []:
            if not isinstance(i, dict) or "id" not in i:
                raise ValueError(f"Elk idee heeft een 'id' nodig (fout bij: {i})")
        return data

    def save_text(self, text: str):
        self.validate_text(text)
        self._backup()
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def save_raw(self, data):
        buf = io.StringIO()
        _yaml.dump(data, buf)
        self.save_text(buf.getvalue())

    def _backup(self):
        if os.path.exists(self.path):
            shutil.copyfile(self.path, self.path + ".vorige")


def parse_time(s) -> time:
    if isinstance(s, time):
        return s
    if isinstance(s, int):                  # YAML leest 08:30 soms als sexagesimaal getal
        return time(s // 60, s % 60)
    return datetime.strptime(str(s), "%H:%M").time()


def as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def weekday_index(naam: str) -> int:
    return DAGEN.index(naam.strip().lower())
