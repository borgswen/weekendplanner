"""Agenda's ophalen (iCal), afspraken negeren en vrije blokken (weekend / dagje / eigen) bepalen."""
from __future__ import annotations

import logging
import threading
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events
import requests

from .config import as_date, parse_time

TZ = ZoneInfo("Europe/Amsterdam")
log = logging.getLogger(__name__)

_DAGNAMEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
_MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]


def _dag(d) -> str:
    return f"{_DAGNAMEN[d.weekday()]} {d.day} {_MAANDEN[d.month - 1]}"


@dataclass
class Event:
    start: datetime
    end: datetime
    titel: str
    agenda: str
    hele_dag: bool
    uid: str = ""

    @property
    def key(self) -> str:
        return f"{self.agenda}|{self.uid}|{self.start.isoformat()}"

    def kort(self) -> str:
        if self.hele_dag:
            dagen = (self.end.date() - self.start.date()).days
            wanneer = _dag(self.start) + (f" t/m {_dag(self.end - timedelta(days=1))}" if dagen > 1 else " (hele dag)")
        else:
            wanneer = f"{_dag(self.start)} {self.start:%H:%M}-{self.end:%H:%M}"
        return f"{wanneer}: {self.titel} ({self.agenda})"

    def to_json(self) -> dict:
        return {"key": self.key, "titel": self.titel, "agenda": self.agenda, "hele_dag": self.hele_dag,
                "start": self.start.isoformat(), "eind": self.end.isoformat()}


@dataclass
class Blok:
    """Een vrije periode om weg te gaan. soort: weekend | dagje | eigen."""
    soort: str
    vertrek: datetime
    terug: datetime
    nachten: int
    omheen: list[str] = field(default_factory=list)
    notitie: str = ""                       # extra wens van de gebruiker (eigen prompt)
    conflicten: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        if self.soort == "weekend":         # zelfde sleutel als versie 1: de vrijdag
            d = self.vertrek.date()
            return (d - timedelta(days=(d.weekday() - 4) % 7)).isoformat()
        return f"{self.soort}:{self.vertrek:%Y-%m-%dT%H:%M}"

    @property
    def reissoort(self) -> str:
        return "dagje" if self.nachten == 0 else ("kort" if self.nachten == 1 else "lang")

    @property
    def activiteitdagen(self) -> list[date]:
        if self.nachten == 0:
            return [self.vertrek.date()]
        eerste = self.vertrek.date() + timedelta(days=1 if self.vertrek.hour >= 12 else 0)
        laatste = self.terug.date()
        dagen = [eerste + timedelta(days=i) for i in range((laatste - eerste).days + 1)]
        return dagen or [self.vertrek.date()]

    def label(self) -> str:
        if self.nachten == 0:
            return f"{_dag(self.vertrek)} {self.vertrek:%H:%M}-{self.terug:%H:%M}"
        return f"{_dag(self.vertrek)} {self.vertrek:%H:%M} t/m {_dag(self.terug)} {self.terug:%H:%M}"

    def soort_label(self) -> str:
        return {"dagje": "dagje weg", "kort": "weekendje (1 nacht)", "lang": f"{self.nachten} nachten weg"}[self.reissoort]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(vertrek=self.vertrek.isoformat(), terug=self.terug.isoformat())
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Blok":
        return cls(soort=d.get("soort", "weekend"), vertrek=datetime.fromisoformat(d["vertrek"]),
                   terug=datetime.fromisoformat(d["terug"]), nachten=d["nachten"], omheen=d.get("omheen", []),
                   notitie=d.get("notitie", ""), conflicten=d.get("conflicten", []))


# ---------------------------------------------------------------- iCal ----------

def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def _declined(comp, email: str | None) -> bool:
    if not email:
        return False
    atts = comp.get("ATTENDEE") or []
    if not isinstance(atts, list):
        atts = [atts]
    for a in atts:
        if str(a).lower().removeprefix("mailto:") == email.lower():
            return str(a.params.get("PARTSTAT", "")).upper() == "DECLINED"
    return False


def parse_events(ics: bytes, agenda: str, start: datetime, end: datetime, email: str | None = None) -> list[Event]:
    cal = icalendar.Calendar.from_ical(ics)
    out = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        if str(comp.get("STATUS", "")).upper() == "CANCELLED" or _declined(comp, email):
            continue
        s = comp.get("DTSTART").dt
        e = comp.get("DTEND").dt if comp.get("DTEND") else None
        uid = str(comp.get("UID", ""))
        titel = str(comp.get("SUMMARY", ""))
        if not isinstance(s, datetime):          # hele-dag-afspraak
            e = e or (s + timedelta(days=1))
            out.append(Event(datetime.combine(s, time.min, TZ), datetime.combine(e, time.min, TZ), titel, agenda, True, uid))
        else:
            s = _aware(s)
            if e is None:
                dur = comp.get("DURATION")
                e = s + (dur.dt if dur else timedelta(hours=1))
            out.append(Event(s, _aware(e), titel, agenda, False, uid))
    return sorted(out, key=lambda ev: ev.start)


_cache: dict = {}
_cache_lock = threading.Lock()


def load_events(cfg: dict, start: date, end: date, max_age_s: int = 300) -> list[Event]:
    """Afspraken van alle agenda's; de ruwe iCal wordt 5 minuten gecachet."""
    s = datetime.combine(start, time.min, TZ)
    e = datetime.combine(end, time.min, TZ)
    events = []
    for a in cfg["agendas"]:
        url = a.get("ical_url")
        if not url:
            raise RuntimeError(f"Geen iCal-link voor agenda '{a['naam']}' (zie omgevingsvariabelen)")
        with _cache_lock:
            hit = _cache.get(url)
        if hit and _time.time() - hit[0] < max_age_s:
            ics = hit[1]
        else:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            ics = r.content
            with _cache_lock:
                _cache[url] = (_time.time(), ics)
        events += parse_events(ics, a["naam"], s, e, a.get("email"))
    return sorted(events, key=lambda ev: ev.start)


# ------------------------------------------------------- negeren & vrij ----------

def is_genegeerd(ev: Event, cfg: dict, negeer: dict | None = None) -> bool:
    negeer = negeer or {}
    t = ev.titel.lower()
    woorden = cfg.get("agenda_regels", {}).get("negeer", []) or []
    if any(w.lower() in t for w in woorden):
        return True
    if ev.key in (negeer.get("afspraken") or {}):
        return True
    return any(t == x.lower() for x in (negeer.get("titels") or []))


def _blokkerend(events, cfg, negeer):
    return [e for e in events if not is_genegeerd(e, cfg, negeer)]


def _omheen(events, van: datetime, tot: datetime) -> list[str]:
    return [e.kort() for e in events if e.start < tot and e.end > van]


def _uitgesloten(d: date, cfg: dict) -> bool:
    return any(as_date(u["van"]) <= d <= as_date(u["tot"]) for u in cfg.get("uitsluiten", []) or [])


def free_blocks(events: list[Event], cfg: dict, van: date, tot: date, negeer: dict | None = None,
                dagjes: bool = True) -> list[Blok]:
    """Vrije weekenden (vr-zo, za-zo, vr-za) en, als het weekend niet vrij is, losse vrije weekenddagen."""
    w = cfg.get("weekend", {})
    vr_vertrek = parse_time(w.get("vertrek_vrijdag", "16:00"))
    za_vertrek = parse_time(w.get("vertrek_zaterdag", "08:00"))
    za_terug = parse_time(w.get("terug_zaterdag", "22:00"))
    zo_terug = parse_time(w.get("terug_zondag", "19:00"))
    dj = cfg.get("dagje", {})
    dj_van, dj_tot = parse_time(dj.get("van", "08:30")), parse_time(dj.get("tot", "21:00"))
    blok = _blokkerend(events, cfg, negeer)

    def vrij(s, e):
        return not any(x.start < e and x.end > s for x in blok)

    vrijdag = van + timedelta(days=(4 - van.weekday()) % 7)
    result = []
    while vrijdag <= tot:
        za, zo = vrijdag + timedelta(1), vrijdag + timedelta(2)
        ruim = (datetime.combine(vrijdag, time.min, TZ), datetime.combine(vrijdag + timedelta(4), time.min, TZ))
        omheen = _omheen(events, *ruim)
        if not any(_uitgesloten(d, cfg) for d in (vrijdag, za, zo)):
            varianten = [
                (datetime.combine(vrijdag, vr_vertrek, TZ), datetime.combine(zo, zo_terug, TZ), 2),
                (datetime.combine(za, za_vertrek, TZ), datetime.combine(zo, zo_terug, TZ), 1),
                (datetime.combine(vrijdag, vr_vertrek, TZ), datetime.combine(za, za_terug, TZ), 1),
            ]
            gevonden = next((Blok("weekend", s, e, n, omheen) for s, e, n in varianten if vrij(s, e)), None)
            if gevonden:
                result.append(gevonden)
            elif dagjes:
                for d in (za, zo):
                    s, e = datetime.combine(d, dj_van, TZ), datetime.combine(d, dj_tot, TZ)
                    if vrij(s, e):
                        result.append(Blok("dagje", s, e, 0, omheen))
        vrijdag += timedelta(7)
    return [b for b in result if b.vertrek.date() >= van]


def custom_block(events: list[Event], cfg: dict, vertrek: datetime, terug: datetime, notitie: str = "",
                 negeer: dict | None = None) -> Blok:
    """Een zelf gekozen periode (ook doordeweeks); afspraken die in de weg zitten komen in `conflicten`."""
    nachten = max(0, (terug.date() - vertrek.date()).days)
    blok = _blokkerend(events, cfg, negeer)
    conflicten = [e.kort() for e in blok if e.start < terug and e.end > vertrek]
    omheen = _omheen(events, datetime.combine(vertrek.date() - timedelta(1), time.min, TZ),
                     datetime.combine(terug.date() + timedelta(2), time.min, TZ))
    return Blok("eigen", vertrek, terug, nachten, omheen, notitie, conflicten)
