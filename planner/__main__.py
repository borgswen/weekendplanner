"""Gebruik:
  python -m planner serve                    webserver + automatische planning (standaard in Docker)
  python -m planner vrij                     laat de vrije weekenden en dagjes zien
  python -m planner nu [--modus vooruit|lastminute] [--van 2026-12-11T16:00 --tot 2026-12-13T19:00] [--wens "..."] [--dry-run]
  python -m planner testmelding              stuurt een testmelding via ntfy
  python -m planner deals [--dry-run]        zoekt nu naar deals op de dealsites
"""
import argparse
import logging
import os
import threading
import time
from datetime import date, datetime

from . import config, notify, web
from .config import ConfigStore
from .core import App, parse_local
from .store import Store


def scheduler(app: App):
    log = logging.getLogger("planning")
    while True:
        nu = datetime.now()
        try:
            planning = app.cfg.get("planning", {})
        except Exception:
            log.exception("Config lezen mislukt")
            planning = {}
        # Deals zoeken staat standaard op maandagavond, ook in oudere configs zonder deze regel
        planning = {"deals": {"dag": "maandag", "tijd": "19:30"}} | planning
        for taak, p in planning.items():
            if not isinstance(p, dict) or "dag" not in p:
                continue
            try:
                if (nu.weekday() == config.weekday_index(p["dag"]) and nu.time() >= config.parse_time(p["tijd"])
                        and app.store.last_run(taak) != nu.date().isoformat()):
                    app.store.set_last_run(taak, nu.date().isoformat())
                    log.info("Geplande taak '%s' start", taak)
                    if taak == "deals":
                        if (app.cfg.get("deals") or {}).get("aan", True):
                            app.deals_scan()
                    else:
                        app.run(taak)
            except Exception:
                log.exception("Taak %s mislukt", taak)
        time.sleep(30)


def main():
    ap = argparse.ArgumentParser(prog="planner")
    ap.add_argument("actie", choices=["serve", "vrij", "weekenden", "nu", "testmelding", "deals"])
    ap.add_argument("--modus", default="vooruit", choices=["vooruit", "lastminute"])
    ap.add_argument("--van", help="vertrek, bv. 2026-12-11T16:00")
    ap.add_argument("--tot", help="terug, bv. 2026-12-13T19:00")
    ap.add_argument("--wens", default="", help="extra wens voor Claude")
    ap.add_argument("--dry-run", action="store_true", help="geen ntfy-melding versturen, alleen loggen")
    ap.add_argument("--config", default=os.environ.get("PLANNER_CONFIG", "/app/config.yaml"))
    ap.add_argument("--data", default=os.environ.get("PLANNER_DATA", "/data"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = App(ConfigStore(args.config, args.data), Store(os.path.join(args.data, "state.json")), args.dry_run)

    if args.actie in ("vrij", "weekenden"):
        for b in app.blocks():
            print(f"{b.label():34} {b.soort_label():22} ({(b.vertrek.date() - date.today()).days} dagen)")
            for o in b.omheen:
                print(f"    · {o}")
    elif args.actie == "nu":
        blok = app.custom(parse_local(args.van), parse_local(args.tot), args.wens) if args.van and args.tot else None
        vid = app.run("handmatig" if blok else args.modus, blok)
        print(f"Voorstel: {app.cfg.get('publieke_url', '').rstrip('/')}/plan/{vid}" if vid else "Geen voorstel gemaakt.")
    elif args.actie == "deals":
        n = app.deals_scan()
        for d in sorted(app.store.deals().values(), key=lambda x: -(x.get("korting_pct") or 0)):
            print(f"{d.get('korting_pct') or 0:>4.0f}%  €{d['prijs_eur']:>7.2f}  {d['titel'][:60]:60}  {d.get('plaats', '')}")
        print(f"{n} nieuwe deal(s).")
    elif args.actie == "testmelding":
        notify.send_text(app.cfg, "Weekendplanner", "Testmelding: het werkt! 🎉", args.dry_run)
    else:
        threading.Thread(target=scheduler, args=(app,), daemon=True).start()
        web.serve(app, int(os.environ.get("PORT", 8088)))


if __name__ == "__main__":
    main()
