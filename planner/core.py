"""De runs: vrije blokken zoeken, ideeën filteren, Claude laten plannen, foto's erbij, melden."""
from __future__ import annotations

import logging
import random
import secrets
from datetime import date, datetime, timedelta

from . import claude, deals, ideas, images, notify
from .calendars import TZ, Blok, custom_block, free_blocks, load_events
from .config import ConfigStore
from .store import Store
from .weather import Weather

log = logging.getLogger(__name__)


class App:
    def __init__(self, configs: ConfigStore, store: Store, dry_run: bool = False):
        self.configs, self.store, self.dry_run = configs, store, dry_run

    @property
    def cfg(self) -> dict:
        return self.configs.load()

    # ------------------------------------------------------------ agenda
    def events(self, van: date, tot: date):
        return load_events(self.cfg, van, tot)

    def blocks(self, dagen: int = 70, van: date | None = None) -> list[Blok]:
        van = van or date.today()
        cfg = self.cfg
        events = load_events(cfg, van - timedelta(days=1), van + timedelta(days=dagen + 7))
        dagjes = cfg.get("planning", {}).get("dagjes", True)
        return free_blocks(events, cfg, van, van + timedelta(days=dagen), self.store.negeer(), dagjes)

    def custom(self, vertrek: datetime, terug: datetime, notitie: str = "") -> Blok:
        events = load_events(self.cfg, vertrek.date() - timedelta(days=2), terug.date() + timedelta(days=3))
        return custom_block(events, self.cfg, vertrek, terug, notitie, self.store.negeer())

    def kies_blok(self, modus: str, alle: list[Blok]) -> Blok | None:
        vandaag = date.today()
        if modus == "vooruit":
            p = self.cfg.get("planning", {}).get("vooruit", {})
            lo, hi = p.get("min_dagen", 14), p.get("max_dagen", 42)
            for b in alle:
                if b.soort == "weekend" and lo <= (b.vertrek.date() - vandaag).days <= hi and not self.store.for_key(b.key):
                    return b
            return None
        # lastminute: eerstvolgende vrije weekend of dagje binnen een week
        for b in alle:
            if 0 <= (b.vertrek.date() - vandaag).days <= 6:
                eerder = self.store.for_key(b.key)
                if any(v["feedback"] == "up" or v["modus"] != "vooruit" for v in eerder):
                    continue
                return b
        return None

    # ---------------------------------------------------------------- run
    def gebruik_lijst(self, cfg: dict, blok: Blok) -> bool:
        """Ideeënlijst als menukaart gebruiken? Standaard alleen als we zelf een wens opgeven."""
        stand = str((cfg.get("inspiratie") or {}).get("ideeenlijst", "wens")).lower()
        if blok.notitie.strip() or stand == "altijd":
            return True
        return stand == "soms" and random.random() < 0.25

    def run(self, modus: str, blok: Blok | None = None, uitsluiten_ids: set[str] = frozenset(),
            al_voorgesteld: list[str] | None = None) -> str | None:
        taak = secrets.token_hex(3)
        try:
            cfg = self.cfg
            if blok is None:
                blok = self.kies_blok(modus, self.blocks())
            if blok is None:
                log.info("[%s] Geen geschikt vrij blok gevonden; niks te doen.", modus)
                return None
            self.store.bezig[taak] = f"{blok.soort_label()} {blok.label()}"
            log.info("[%s] Gekozen: %s (%s)", modus, blok.label(), blok.soort_label())
            weather = Weather()
            lijst = self.gebruik_lijst(cfg, blok)
            kandidaten, afgevallen = ideas.candidates(cfg, blok, modus, weather, uitsluiten_ids) if lijst else ([], [])
            if lijst and not kandidaten and not blok.notitie:
                log.info("Geen passende ideeën uit de lijst (%s); Claude bedenkt zelf iets", "; ".join(afgevallen))
                lijst = False
            log.info("Ideeënlijst %s", "gebruikt" if lijst else "niet gebruikt: Claude bedenkt zelf iets")
            thuis = cfg.get("thuis_locatie") or {"lat": 52.01, "lon": 4.36}
            prompt = claude.build_prompt(
                cfg, blok, modus, kandidaten, afgevallen, self.store.history_for_prompt(20),
                deals.voor_prompt(self, blok.vertrek.date()), lijst=lijst, thema=random.choice(claude.THEMAS),
                al_voorgesteld=al_voorgesteld, weer_thuis=weather.for_days(thuis, blok.activiteitdagen))
            plan, kosten = claude.make_plan(cfg, prompt)
            fotos = images.voor_plan(plan)
            vid = self.store.add(blok.to_dict(), blok.key, modus, plan, kosten, fotos)
            notify.send_plan(cfg, vid, self.store.get(vid), self.dry_run)
            log.info("Voorstel %s verstuurd: %s", vid, plan.get("titel"))
            return vid
        except Exception as e:
            log.exception("Run mislukt")
            notify.send_error(self.cfg, f"{type(e).__name__}: {e}", self.dry_run)
            return None
        finally:
            self.store.bezig.pop(taak, None)

    def deals_scan(self) -> int:
        taak = secrets.token_hex(3)
        self.store.bezig[taak] = "deals zoeken"
        try:
            return deals.scan(self)
        except Exception as e:
            log.exception("Deals zoeken mislukt")
            notify.send_error(self.cfg, f"Deals zoeken mislukt: {type(e).__name__}: {e}", self.dry_run)
            return 0
        finally:
            self.store.bezig.pop(taak, None)

    def opnieuw(self, vid: str) -> str | None:
        v = self.store.get(vid)
        if not v:
            return None
        if not v["feedback"]:
            self.store.set_feedback(vid, "opnieuw")
        blok = Blok.from_dict(v["blok"])
        al_gehad = {x["plan"].get("idee_id") for x in self.store.for_key(v["blok_key"])}
        if {i["id"] for i in self.cfg["ideeen"]} <= al_gehad:
            al_gehad = {v["plan"].get("idee_id")}
        eerder = [f"{x['plan'].get('titel')} ({x['plan'].get('bestemming')})" for x in self.store.for_key(v["blok_key"])]
        return self.run("opnieuw", blok, al_gehad, eerder)


def parse_local(s: str) -> datetime:
    """'2026-12-11T16:00' uit een datetime-local veld → aware datetime."""
    return datetime.fromisoformat(s).replace(tzinfo=TZ)
