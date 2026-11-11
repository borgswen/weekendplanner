import os
import shutil
from datetime import date, datetime, timedelta

import pytest
import yaml

from planner import claude, deals, notify, web
from planner.calendars import TZ, custom_block
from planner.config import ConfigStore
from planner.core import App
from planner.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VANDAAG = date.today()
LATER = (VANDAAG + timedelta(days=30)).isoformat()
VOORBIJ = (VANDAAG - timedelta(days=1)).isoformat()


def deal(titel, url, korting=None, geldig_tot="", prijs=29.95, **extra):
    return {"titel": titel, "site": "socialdeal.nl", "url": url, "plaats": "Den Haag", "soort": "wellness",
            "prijs_eur": prijs, "van_prijs_eur": 59.9 if korting else None, "korting_pct": korting,
            "voor_personen": 2, "geldig_tot": geldig_tot, **extra}


@pytest.fixture
def app(tmp_path, monkeypatch):
    for k in ("ICAL_IK", "ICAL_VRIENDIN", "NTFY_TOPIC"):
        monkeypatch.setenv(k, "")
    shutil.copy(os.path.join(ROOT, "config.yaml"), tmp_path / "default.yaml")
    a = App(ConfigStore(str(tmp_path / "default.yaml"), str(tmp_path)), Store(str(tmp_path / "state.json")), dry_run=True)
    return a


def test_samenvoegen_dedupe_en_verlopen():
    oud = {"https://x/a": deal("A", "https://x/a", 50, LATER) | {"gevonden": "2026-01-01", "gezien": "2026-01-01"},
           "https://x/b": deal("B", "https://x/b", 30, VOORBIJ) | {"gezien": VANDAAG.isoformat()}}
    nieuw = [deal("A (nieuwe prijs)", "https://X/a/?utm=1", 55, LATER), deal("C", "https://x/c", 45), {"titel": "kapot", "url": "geen-url"}]
    alle, erbij = deals.samenvoegen(oud, nieuw, 60)
    assert set(alle) == {"https://x/a", "https://x/c"}  # B verlopen, kapotte URL genegeerd
    assert alle["https://x/a"]["titel"] == "A (nieuwe prijs)" and alle["https://x/a"]["gevonden"] == "2026-01-01"
    assert [d["titel"] for d in erbij] == ["C"]


def test_deal_zonder_einddatum_vervalt_na_drie_weken():
    assert deals.geldig({"gezien": (VANDAAG - timedelta(days=10)).isoformat()})
    assert not deals.geldig({"gezien": (VANDAAG - timedelta(days=30)).isoformat()})
    assert not deals.geldig({"geldig_tot": "2026-01-01"}, date(2026, 2, 1))


def test_melding_alleen_voor_goede_deals():
    m = deals.melding({"deals": {"melden_vanaf_korting": 40}},
                      [deal("Sauna", "https://x/1", 52), deal("Karten", "https://x/2", 20), deal("Escape", "https://x/3", 45)])
    titel, tekst = m
    assert titel == "2 leuke deals gevonden"
    assert tekst.splitlines()[0].startswith("• Sauna (Den Haag): €29,95 i.p.v. €59,90, -52%")
    assert deals.melding({}, [deal("Karten", "https://x/2", 20)]) is None


def test_scan_prompt_noemt_sites_regios_en_bekende(app):
    p = deals.build_scan_prompt(app.cfg, [deal("Sauna", "https://x/1")])
    assert "site:socialdeal.nl" in p and "- groupon.nl" in p and "- dagjeweg.nl" in p
    assert "Harz" in p  # regio uit de ideeënlijst
    assert "https://x/1" in p


def test_scan_slaat_op_en_meldt(app, monkeypatch):
    gestuurd, aanroep = [], {}

    def fake_claude(cfg, prompt, schema, opdracht, mcp=True):
        aanroep.update(schema=schema, mcp=mcp)
        return {"deals": [deal("Sauna voor 2", "https://www.socialdeal.nl/deals/sauna-1", 50, LATER),
                          deal("Bowlen", "https://www.groupon.nl/deals/bowlen", 25)]}, 0.12
    monkeypatch.setattr(claude, "run_claude", fake_claude)
    monkeypatch.setattr(notify, "send_text", lambda cfg, titel, tekst, dry_run=False, klik=None: gestuurd.append((titel, klik)))
    assert app.deals_scan() == 2
    assert aanroep["mcp"] is False and aanroep["schema"] is deals.SCHEMA
    assert len(app.store.deals()) == 2
    assert gestuurd == [("1 leuke deal gevonden", "http://192.168.68.125:8088/deals")]
    # tweede keer: niets nieuws, geen melding
    assert app.deals_scan() == 0
    assert len(gestuurd) == 1


def test_scan_fout_geeft_foutmelding(app, monkeypatch):
    fouten = []
    monkeypatch.setattr(claude, "run_claude", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("token verlopen")))
    monkeypatch.setattr(notify, "send_error", lambda cfg, tekst, dry_run=False: fouten.append(tekst))
    assert app.deals_scan() == 0
    assert "token verlopen" in fouten[0]
    assert not app.store.bezig


def test_deals_in_de_planprompt(app):
    app.store.set_deals({"a": deal("Sauna", "https://x/a", 50, LATER) | {"gezien": VANDAAG.isoformat()},
                         "b": deal("Oud", "https://x/b", 60, (VANDAAG + timedelta(days=2)).isoformat()) | {"gezien": VANDAAG.isoformat()}})
    vertrek = datetime.combine(VANDAAG + timedelta(days=10), datetime.min.time(), TZ).replace(hour=9)
    lijst = deals.voor_prompt(app, vertrek.date())
    assert [d["titel"] for d in lijst] == ["Sauna"]  # "Oud" is dan verlopen
    blok = custom_block([], app.cfg, vertrek, vertrek + timedelta(hours=12))
    p = claude.build_prompt(app.cfg, blok, "handmatig", [], [], [], lijst)
    assert "# Lopende deals" in p and "https://x/a" in p and "site:socialdeal.nl <plaats>" in p
    zonder = claude.build_prompt({**app.cfg, "deals": {"aan": False}}, blok, "handmatig", [], [], [], lijst)
    assert "Lopende deals" not in zonder and "site:" not in zonder


def test_webpagina_en_instellingen(app):
    app.store.set_deals({"a": deal("Sauna <voor 2>", "https://x/a", 50, LATER, waarom="Ontspannen na de week")
                         | {"gevonden": VANDAAG.isoformat(), "gezien": VANDAAG.isoformat()}})
    html = web.render_deals(app).decode()
    assert "Sauna &lt;voor 2&gt;" in html and "€29,95" in html and "-50%" in html and "<b>nieuw</b>" in html
    assert "Nu zoeken" in html
    assert "name=deals_sites" in web.render_instellingen(app).decode()
    f = {s + k: v for s in ("dagje", "kort", "lang") for k, v in (("_budget", "100"), ("_reistijd", "2"))}
    f |= {"vooruit_dag": "zondag", "vooruit_tijd": "19:00", "lastminute_dag": "woensdag", "lastminute_tijd": "18:00",
          "deals_dag": "dinsdag", "deals_tijd": "20:00", "deals_drempel": "35", "deals_sites": "socialdeal.nl, groupon.nl",
          "deals_zoek_naar": "sauna", "deals_regio": "Delft"}
    web.opslaan_snel(app, f)
    cfg = app.cfg
    assert cfg["deals"]["aan"] is False  # vinkje niet meegestuurd
    assert cfg["deals"]["sites"] == ["socialdeal.nl", "groupon.nl"] and cfg["deals"]["melden_vanaf_korting"] == 35
    assert cfg["planning"]["deals"] == {"dag": "dinsdag", "tijd": "20:00"}
