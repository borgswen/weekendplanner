"""Webinterface: voorstellen, agenda-overlay, instellingen en de knoppen uit de ntfy-melding."""
from __future__ import annotations

import calendar
import html
import logging
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from .calendars import TZ, Blok, is_genegeerd
from .config import STANDAARD_REIZEN, DAGEN
from .core import App, parse_local

log = logging.getLogger(__name__)
e = html.escape
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september",
           "oktober", "november", "december"]
KLEUREN = ["#2f6fdf", "#d2457a", "#8a5cd1", "#d98a1b"]
ICOON = {"trein": "🚆", "bus": "🚌", "trein+bus": "🚆🚌", "auto": "🚗", "auto+aanhanger": "🚗🛻", "fiets": "🚲",
         "brommer": "🛵", "boot": "⛵", "lopen": "🚶"}

CSS = """
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d2321;--muted:#66706c;--accent:#1f6f5c;--line:#e4e0d6;--vrij:#e3f3ea;--dagje:#f1f7d9;--sel:#fff1c7}
@media(prefers-color-scheme:dark){:root{--bg:#141716;--card:#1d2120;--ink:#ecefed;--muted:#9aa5a0;--accent:#6cc4a8;--line:#2c3230;--vrij:#1d3329;--dagje:#2b331b;--sel:#3d3418}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:760px;margin:0 auto;padding:12px 16px 60px}main.breed{max-width:1180px}
nav{display:flex;gap:4px;flex-wrap:wrap;margin:6px 0 14px}nav a{padding:6px 12px;border-radius:999px;text-decoration:none;color:var(--ink);border:1px solid var(--line);background:var(--card)}
nav a.on{background:var(--accent);color:#fff;border-color:var(--accent)}
h1{font-size:1.6rem;line-height:1.2;margin:.2em 0}h2{font-size:1.05rem;margin:0 0 .5em;color:var(--accent)}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.chip{border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:.88rem;background:var(--card)}
table{width:100%;border-collapse:collapse}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
td.r,th.r{text-align:right;white-space:nowrap}tr.tot td{font-weight:600;border-bottom:none}.dag{margin-top:10px;font-weight:600}
ul{padding-left:1.1em;margin:.3em 0}li{margin:.25em 0}a{color:var(--accent)}
.knoppen{display:flex;gap:10px;flex-wrap:wrap;align-items:center}form{margin:0}
button,.knop{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:7px 13px;cursor:pointer;text-decoration:none;display:inline-block}
button.hoofd,.knop.hoofd{background:var(--accent);border-color:var(--accent);color:#fff}button.on{outline:2px solid var(--accent)}
.badge{background:var(--accent);color:#fff;border-radius:6px;padding:1px 7px;font-size:.78rem;margin-left:6px}
.schat{color:var(--muted);font-size:.8rem}
.hero{width:100%;aspect-ratio:16/7;object-fit:cover;border-radius:14px;display:block}
.galerij{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
figure{margin:0 0 6px}.galerij img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:10px;display:block}
figcaption{font-size:.72rem;color:var(--muted);line-height:1.3;margin-top:2px}
.optie{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:8px 0}.optie.aan{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.lijst a{display:flex;gap:12px;text-decoration:none;color:inherit;align-items:center}.lijst img{width:84px;height:64px;object-fit:cover;border-radius:10px;flex:none}
label{display:block;margin:8px 0 2px;font-size:.9rem}input,textarea,select{font:inherit;width:100%;padding:7px 9px;border-radius:9px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
textarea.code{font-family:ui-monospace,monospace;font-size:.85rem;min-height:420px}
.rij{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.melding{background:var(--sel);border-radius:10px;padding:8px 12px;margin:10px 0}
/* agenda */
.maand{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}.maand .kop{font-size:.8rem;color:var(--muted);text-align:center}
.cel{background:var(--card);border:1px solid var(--line);border-radius:10px;min-height:118px;padding:4px 5px;cursor:pointer;position:relative;overflow:hidden}
.cel.anders{opacity:.45}.cel.vrij{background:var(--vrij)}.cel.dagje{background:var(--dagje)}.cel.sel{outline:3px solid #e0a800}.cel.vandaag .nr{background:var(--accent);color:#fff;border-radius:999px;padding:0 6px}
.cel .nr{font-size:.8rem;font-weight:600}.cel .lbl{font-size:.68rem;color:var(--accent);font-weight:600;margin-left:4px}
.ev{display:block;font-size:.72rem;line-height:1.25;border-radius:5px;padding:1px 4px;margin-top:2px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;border:0;width:100%;text-align:left}
.ev.neg{opacity:.45;text-decoration:line-through}
.idee{display:block;font-size:.72rem;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.paneel{position:sticky;bottom:0;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-top:12px;box-shadow:0 -4px 18px #0002}
dialog{border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--ink);max-width:420px}dialog::backdrop{background:#0006}
.legenda{display:flex;gap:12px;flex-wrap:wrap;font-size:.85rem;margin:6px 0}.legenda span{display:inline-flex;align-items:center;gap:5px}.legenda i{width:12px;height:12px;border-radius:3px;display:inline-block}
@media(max-width:700px){.cel{min-height:74px}.ev{font-size:.62rem}.cel .lbl{display:none}}
"""


def _nav(actief: str) -> str:
    items = [("/", "Voorstellen"), ("/agenda", "Agenda"), ("/instellingen", "Instellingen")]
    return "<nav>" + "".join(f"<a href='{u}' class='{'on' if u == actief else ''}'>{t}</a>" for u, t in items) + "</nav>"


def _page(titel: str, body: str, actief: str = "", breed: bool = False, melding: str = "") -> bytes:
    m = f"<div class=melding>{e(melding)}</div>" if melding else ""
    return (f"<!doctype html><html lang=nl><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(titel)}</title><style>{CSS}</style><main class='{'breed' if breed else ''}'>{_nav(actief)}{m}{body}</main></html>").encode()


def _eur(x) -> str:
    return "–" if x is None else f"€{x:,.0f}".replace(",", ".")


def _link(url, tekst) -> str:
    return f"<a href='{e(url)}' target=_blank rel=noopener>{e(tekst)}</a>" if url else e(tekst)


def _duur(minuten) -> str:
    if minuten is None:
        return "–"
    m = int(minuten)
    return f"{m // 60}u{m % 60:02d}"


def _foto_html(f: dict, groot: bool = False) -> str:
    cls = "hero" if groot else ""
    return (f"<figure><a href='{e(f.get('pagina') or f['url'])}' target=_blank rel=noopener>"
            f"<img class='{cls}' src='{e(f['url'])}' alt='{e(f.get('zoekterm', ''))}' loading=lazy></a>"
            f"<figcaption>{e(f.get('zoekterm', ''))} · {e(f.get('maker', ''))} · {e(f.get('licentie', ''))}</figcaption></figure>")


# ------------------------------------------------------------ planpagina ----------

def _feedback_knoppen(v: dict) -> str:
    fb = v.get("feedback")
    def knop(pad, label, waarde):
        actie = f"/{pad}/{v['id']}" + (f"/{waarde}" if pad == "feedback" else "")
        return f"<form method=post action='{actie}'><button class='{'on' if fb == waarde else ''}'>{label}</button></form>"
    return (f"<div class=card><div class=knoppen>{knop('feedback', '👍 Leuk', 'up')}{knop('feedback', '👎 Niks', 'down')}"
            f"{knop('opnieuw', '🔁 Ander idee', 'opnieuw')}</div></div>")


def render_plan(v: dict) -> bytes:
    p, b = v["plan"], Blok.from_dict(v["blok"])
    if "vervoer" not in p:
        return render_plan_v1(v)
    fotos = v.get("fotos", [])
    per_term = {f["zoekterm"].lower(): f for f in fotos}
    hero = _foto_html(fotos[0], True) if fotos else ""
    k = p["kosten"]

    def vervoer_optie(o):
        overstap = f" · {int(o['overstappen'])}x overstappen" if o.get("overstappen") else ""
        schat = " <span class=schat>(schatting)</span>" if o.get("prijs_is_schatting") else ""
        boek = " · " + _link(o.get("boeken_url"), "boeken →") if o.get("boeken_url") else ""
        aan = o.get("aanbevolen")
        return (f"<div class='optie {'aan' if aan else ''}'><b>{ICOON.get(o['soort'], '')} {e(o['omschrijving'])}</b>"
                f"{'<span class=badge>aanrader</span>' if aan else ''}"
                f"<div class=muted>Heen: {e(o['heen'])}<br>Terug: {e(o['terug'])}</div>"
                f"<div>{_duur(o.get('reistijd_enkel_min'))} enkel{overstap} · <b>{_eur(o.get('prijs_totaal_eur'))}</b> samen"
                f"{schat}{boek}</div></div>")
    vervoer = "".join(vervoer_optie(o) for o in p["vervoer"]["opties"])
    sl = p.get("slapen") or {}
    slapen = ""
    if sl.get("opties"):
        opts = "".join(
            f"<div class='optie {'aan' if o.get('aanbevolen') else ''}'><b>{_link(o.get('url'), o['naam'])}</b>"
            f"{'<span class=badge>aanrader</span>' if o.get('aanbevolen') else ''} <span class=muted>({e(o['soort'])}"
            f"{', ' + e(o['plaats']) if o.get('plaats') else ''})</span>"
            f"<div>{_eur(o.get('prijs_totaal_eur'))} totaal{' <span class=schat>(schatting)</span>' if o.get('prijs_is_schatting') else ''}"
            f" — {e(o.get('waarom', ''))}</div></div>" for o in sl["opties"])
        zoek = " ".join(f"<a class=knop href='{e(u)}' target=_blank rel=noopener>{e(n.capitalize())}</a>"
                        for n, u in (sl.get("zoeklinks") or {}).items())
        slapen = (f"<div class=card><h2>Slapen · {_eur(k.get('slapen'))}</h2>{opts}"
                  f"{'<p class=muted>Zelf verder zoeken:</p><div class=knoppen>' + zoek + '</div>' if zoek else ''}</div>")

    def onderdeel(o):
        f = per_term.get((o.get("foto_zoekterm") or "").lower())
        img = f"<img src='{e(f['url'])}' style='width:72px;height:54px;object-fit:cover;border-radius:8px;float:right;margin-left:8px' loading=lazy>" if f else ""
        return (f"<li>{img}<b>{e(o.get('tijd', ''))}</b> {_link(o.get('url'), o['wat'])}"
                f"{' – ' + e(o['toelichting']) if o.get('toelichting') else ''}"
                f"{' <span class=muted>(' + _eur(o['kosten_eur']) + ')</span>' if o.get('kosten_eur') else ''}<div style=clear:both></div></li>")
    prog = "".join(f"<div class=dag>{e(d['dag'])}</div><ul>{''.join(onderdeel(o) for o in d['onderdelen'])}</ul>"
                   for d in p["programma"])
    kosten = "".join(f"<tr><td>{n}</td><td class=r>{_eur(k.get(key))}</td></tr>" for n, key in
                     [("Reis", "reis"), ("Slapen", "slapen"), ("Activiteiten", "activiteiten"), ("Eten & drinken", "eten_drinken")])
    galerij = "".join(_foto_html(f) for f in fotos[1:])
    bronnen = "".join(f"<li>{_link(x['url'], x['titel'])}</li>" for x in p.get("bronnen", []))
    notitie = f"<p class=muted>Jullie wens: “{e(b.notitie)}”</p>" if b.notitie else ""
    body = f"""{hero}
<p class=muted>{e(b.label())} · {e(b.soort_label())} · {e(p['bestemming'])}</p>
<h1>{e(p['titel'])}</h1><p>{e(p['samenvatting'])}</p>{notitie}
<div class=chips><span class=chip>💶 {_eur(k.get('totaal'))} samen</span><span class=chip>🌤 {e(p.get('weer', ''))}</span></div>
<div class=card><h2>Waarom</h2>{e(p['waarom'])}</div>
<div class=card><h2>Vervoer</h2><p>{e(p['vervoer']['advies'])}</p>{vervoer}</div>
{slapen}
<div class=card><h2>Programma</h2>{prog}</div>
{'<div class=card><h2>Foto’s</h2><div class=galerij>' + galerij + '</div></div>' if galerij else ''}
<div class=card><h2>Kosten (samen)</h2><table>{kosten}<tr class=tot><td>Totaal</td><td class=r>{_eur(k.get('totaal'))}</td></tr></table>
<p class=muted>{e(k.get('toelichting', ''))}</p></div>
<div class=card><h2>Boeken</h2>{e(p['boeken_voor'])}{('<p>' + e(p['paklijst_tips']) + '</p>') if p.get('paklijst_tips') else ''}</div>
<div class=card><h2>Liever iets anders?</h2><b>{e(p['alternatief']['titel'])}</b> ({_eur(p['alternatief'].get('totaal_eur'))})<br>{e(p['alternatief']['omschrijving'])}</div>
{_feedback_knoppen(v)}
<div class=card><h2>Bronnen</h2><ul>{bronnen}</ul><p class=muted>Opgezocht op {e(v['aangemaakt'][:10])}; check prijzen even voor je boekt. Foto’s: Wikimedia Commons.</p></div>"""
    return _page(p["titel"], body, "/")


def render_plan_v1(v: dict) -> bytes:
    p, b = v["plan"], Blok.from_dict(v["blok"])
    r, a, k = p["reis"], p["accommodatie"], p["kosten"]
    prog = "".join(f"<div class=dag>{e(d['dag'])}</div><ul>" + "".join(
        f"<li><b>{e(o.get('tijd', ''))}</b> {_link(o.get('url'), o['wat'])}"
        f"{' – ' + e(o['toelichting']) if o.get('toelichting') else ''}</li>" for o in d["onderdelen"]) + "</ul>"
        for d in p["programma"])
    body = f"""<p class=muted>{e(b.label())} · {e(p['bestemming'])}</p><h1>{e(p['titel'])}</h1><p>{e(p['samenvatting'])}</p>
<div class=card><h2>Reis · {_eur(r.get('kosten_eur'))}</h2><b>{_link(r.get('boeken_url'), r['vervoer'])}</b>
<ul><li>Heen: {e(r['heen'])}</li><li>Terug: {e(r['terug'])}</li></ul><span class=muted>{e(r['toelichting'])}</span></div>
<div class=card><h2>Slapen · {_eur(a.get('prijs_eur'))}</h2><b>{_link(a.get('url'), a['naam'])}</b><p>{e(a['toelichting'])}</p></div>
<div class=card><h2>Programma</h2>{prog}</div>
<div class=card><h2>Totaal</h2>{_eur(k.get('totaal'))} samen</div>{_feedback_knoppen(v)}"""
    return _page(p["titel"], body, "/")


# --------------------------------------------------------------- overzicht ----------

def render_index(app: App, melding: str = "") -> bytes:
    bezig = "".join(f"<div class=melding>⏳ Bezig met een voorstel voor {e(t)}…</div>" for t in app.store.bezig.values())
    try:
        blokken = app.blocks(dagen=42)[:5]
        vrij = "".join(
            f"<div class=optie><form method=post action=/maak class=knoppen>"
            f"<input type=hidden name=vertrek value='{b.vertrek:%Y-%m-%dT%H:%M}'><input type=hidden name=terug value='{b.terug:%Y-%m-%dT%H:%M}'>"
            f"<input type=hidden name=soort value='{b.soort}'>"
            f"<span style='flex:1'><b>{e(b.label())}</b> <span class=muted>{e(b.soort_label())}"
            f"{' · ' + str(len(app.store.for_key(b.key))) + ' voorstel(len)' if app.store.for_key(b.key) else ''}</span></span>"
            f"<button>Maak voorstel</button></form></div>" for b in blokken) or "<p class=muted>Geen vrije weekenden of dagen in de komende 6 weken.</p>"
    except Exception as ex:
        vrij = f"<p class=muted>Agenda's ophalen mislukt: {e(str(ex))}</p>"
    kaarten = []
    for v in app.store.all():
        b = Blok.from_dict(v["blok"])
        img = f"<img src='{e(v['fotos'][0]['url'])}' loading=lazy>" if v.get("fotos") else ""
        fb = {"up": "👍", "down": "👎"}.get(v["feedback"], "")
        kaarten.append(f"<div class=card><a href='/plan/{v['id']}'>{img}<span><span class=muted>{e(b.label())} · "
                       f"{e(b.soort_label())} {fb}</span><br><b>{e(v['plan']['titel'])}</b> – "
                       f"{_eur(v['plan']['kosten'].get('totaal'))}</span></a></div>")
    body = (f"<h1>Weekendplanner</h1>{bezig}<div class=card><h2>Eerstvolgende vrije momenten</h2>{vrij}"
            f"<p class=muted>Ander moment of doordeweeks? Kies het in de <a href=/agenda>agenda</a>.</p></div>"
            f"<h2 style='margin-top:22px'>Voorstellen</h2><div class=lijst>{''.join(kaarten) or '<p class=muted>Nog geen voorstellen.</p>'}</div>")
    return _page("Weekendplanner", body, "/", melding=melding)


# ------------------------------------------------------------------ agenda ----------

def render_agenda(app: App, maand: str | None, melding: str = "") -> bytes:
    vandaag = date.today()
    j, m = (int(x) for x in maand.split("-")) if maand else (vandaag.year, vandaag.month)
    weken = calendar.Calendar(firstweekday=0).monthdatescalendar(j, m)
    begin, eind = weken[0][0], weken[-1][-1] + timedelta(days=1)
    cfg = app.cfg
    negeer = app.store.negeer()
    namen = [a["naam"] for a in cfg["agendas"]]
    kleur = {n: KLEUREN[i % len(KLEUREN)] for i, n in enumerate(namen)}
    try:
        events = app.events(begin - timedelta(days=1), eind + timedelta(days=1))
        fout = ""
    except Exception as ex:
        events, fout = [], f"Agenda's ophalen mislukt: {ex}"
    try:
        from .calendars import free_blocks
        blokken = free_blocks(events, cfg, max(begin, vandaag), eind, negeer, cfg.get("planning", {}).get("dagjes", True)) if events else []
    except Exception:
        blokken = []
    vrije_dag: dict[date, Blok] = {}
    for b in blokken:
        d = b.vertrek.date()
        while d <= b.terug.date():
            vrije_dag.setdefault(d, b)
            d += timedelta(days=1)
    voorstellen: dict[date, list] = {}
    for v in app.store.all():
        voorstellen.setdefault(datetime.fromisoformat(v["blok"]["vertrek"]).date(), []).append(v)

    cellen = []
    for week in weken:
        for d in week:
            ds, de = datetime.combine(d, datetime.min.time(), TZ), datetime.combine(d + timedelta(1), datetime.min.time(), TZ)
            evs = [x for x in events if x.start < de and x.end > ds]
            evs.sort(key=lambda x: (not x.hele_dag, x.start))
            chips = "".join(
                f"<button type=button class='ev {'neg' if is_genegeerd(x, cfg, negeer) else ''}' style='background:{kleur.get(x.agenda, '#777')}'"
                f" data-key='{e(x.key)}' data-titel='{e(x.titel)}' data-agenda='{e(x.agenda)}' data-neg='{1 if is_genegeerd(x, cfg, negeer) else 0}'"
                f" data-tijd='{e(x.kort())}' title='{e(x.kort())}'>{'' if x.hele_dag else x.start.strftime('%H:%M') + ' '}{e(x.titel)}</button>"
                for x in evs)
            ideeen = "".join(f"<a class=idee href='/plan/{v['id']}' onclick='event.stopPropagation()'>💡 {e(v['plan']['titel'])}</a>"
                             for v in voorstellen.get(d, []))
            b = vrije_dag.get(d)
            cls = ["cel"] + (["anders"] if d.month != m else []) + (["vandaag"] if d == vandaag else [])
            lbl = ""
            if b:
                cls.append("dagje" if b.soort == "dagje" else "vrij")
                if d == b.vertrek.date():
                    lbl = f"<span class=lbl>{'vrij dagje' if b.soort == 'dagje' else 'vrij weekend'}</span>"
            attrs = f"data-datum='{d.isoformat()}'"
            if b:
                attrs += f" data-bv='{b.vertrek:%Y-%m-%dT%H:%M}' data-bt='{b.terug:%Y-%m-%dT%H:%M}'"
            cellen.append(f"<div class='{' '.join(cls)}' {attrs}><span class=nr>{d.day}</span>{lbl}{chips}{ideeen}</div>")

    vorige = (date(j, m, 1) - timedelta(days=1)).strftime("%Y-%m")
    volgende = (date(j, m, 28) + timedelta(days=7)).strftime("%Y-%m")
    legenda = "".join(f"<span><i style='background:{kleur[n]}'></i>{e(n)}</span>" for n in namen)
    legenda += "<span><i style='background:var(--vrij);border:1px solid var(--line)'></i>vrij weekend</span>"
    legenda += "<span><i style='background:var(--dagje);border:1px solid var(--line)'></i>vrij dagje</span>"
    kop = "".join(f"<div class=kop>{d[:2]}</div>" for d in DAGEN)
    body = f"""
<div class=knoppen style='justify-content:space-between'><a class=knop href='/agenda?m={vorige}'>←</a>
<h1 style='margin:0'>{MAANDEN[m - 1].capitalize()} {j}</h1><a class=knop href='/agenda?m={volgende}'>→</a></div>
<div class=legenda>{legenda}</div>
{f'<div class=melding>{e(fout)}</div>' if fout else ''}
<p class=muted>Klik op een dag om een begin te kiezen en op een tweede dag voor het eind (of klik een groene dag voor dat vrije blok).
Klik op een afspraak om hem te negeren.</p>
<div class=maand>{kop}{''.join(cellen)}</div>
<form class=paneel id=paneel method=post action=/maak hidden>
 <input type=hidden name=terug_naar value='/agenda?m={j}-{m:02d}'>
 <div class=rij><div><label>Vertrek</label><input type=datetime-local name=vertrek id=v required></div>
 <div><label>Terug</label><input type=datetime-local name=terug id=t required></div></div>
 <label>Extra wens voor Claude (optioneel)</label>
 <textarea name=notitie rows=2 placeholder='bv. iets met sauna, of: we willen naar Gent, of: niet te ver, we zijn moe'></textarea>
 <div class=knoppen style='margin-top:8px'><button class=hoofd>Maak voorstel</button><button type=button onclick='wis()'>Annuleer</button>
 <span class=muted id=info></span></div>
</form>
<dialog id=dlg><form method=post action=/negeer>
 <h2 id=dt></h2><p class=muted id=dw></p>
 <input type=hidden name=key id=dk><input type=hidden name=titel id=dti><input type=hidden name=terug_naar value='/agenda?m={j}-{m:02d}'>
 <div id=dnieuw><p>Mag deze afspraak worden overgeslagen bij het zoeken naar vrije tijd?</p>
 <div class=knoppen><button name=scope value=afspraak class=hoofd>Alleen deze keer</button><button name=scope value=titel>Altijd met deze titel</button></div></div>
 <div id=dherstel><p>Deze afspraak wordt nu genegeerd.</p><div class=knoppen><button name=scope value=herstel class=hoofd>Weer meetellen</button></div></div>
 <p><button type=button onclick="dlg.close()">Sluiten</button></p></form></dialog>
<script>
const paneel=document.getElementById('paneel'),v=document.getElementById('v'),t=document.getElementById('t'),info=document.getElementById('info');
let start=null;
function cellen(){{return [...document.querySelectorAll('.cel')]}}
function markeer(a,b){{cellen().forEach(c=>{{const d=c.dataset.datum;c.classList.toggle('sel',a&&d>=a&&d<=(b||a))}})}}
function wis(){{start=null;markeer(null);paneel.hidden=true}}
function vul(vt,tt){{v.value=vt;t.value=tt;paneel.hidden=false;
 const n=Math.round((new Date(tt.slice(0,10))-new Date(vt.slice(0,10)))/864e5);info.textContent=n===0?'dagje weg':n+' nacht'+(n>1?'en':'');
 paneel.scrollIntoView({{behavior:'smooth',block:'nearest'}})}}
cellen().forEach(c=>c.addEventListener('click',ev=>{{
 if(ev.target.closest('.ev'))return;const d=c.dataset.datum;
 if(!start&&c.dataset.bv){{markeer(c.dataset.bv.slice(0,10),c.dataset.bt.slice(0,10));vul(c.dataset.bv,c.dataset.bt);start=null;return}}
 if(!start||d<start){{start=d;markeer(d);const dow=new Date(d).getDay();vul(d+(dow===5?'T16:00':'T09:00'),d+'T20:00');return}}
 markeer(start,d);vul(v.value,d+'T19:00');start=null;
}}));
document.querySelectorAll('.ev').forEach(b=>b.addEventListener('click',ev=>{{ev.stopPropagation();
 dk.value=b.dataset.key;dti.value=b.dataset.titel;dt.textContent=b.dataset.titel;dw.textContent=b.dataset.tijd;
 const neg=b.dataset.neg==='1';dnieuw.hidden=neg;dherstel.hidden=!neg;dlg.showModal()}}));
</script>"""
    return _page("Agenda", body, "/agenda", breed=True, melding=melding)


# ------------------------------------------------------------- instellingen ----------

def render_instellingen(app: App, melding: str = "", yaml_tekst: str | None = None) -> bytes:
    cfg = app.cfg
    r = cfg["reizen"]
    pl = cfg.get("planning", {})
    namen = {"dagje": "Dagje weg", "kort": "1 nacht", "lang": "2+ nachten"}
    reizen = "".join(
        f"<div class=card style='margin:6px 0'><b>{namen[s]}</b><div class=rij>"
        f"<div><label>Budget samen (€)</label><input type=number name='{s}_budget' value='{r[s]['budget_eur']}' min=0></div>"
        f"<div><label>Max reistijd enkel (uur)</label><input type=number step=0.25 name='{s}_reistijd' value='{r[s]['max_reistijd_uur']}' min=0></div>"
        + (f"<div><label>Extra per nacht boven 2 (€)</label><input type=number name='lang_extra' value='{r['lang'].get('extra_per_nacht_eur', 0)}' min=0></div>" if s == "lang" else "")
        + "</div></div>" for s in STANDAARD_REIZEN)

    def dagsel(naam, waarde):
        return f"<select name='{naam}'>" + "".join(f"<option {'selected' if d == waarde else ''}>{d}</option>" for d in DAGEN) + "</select>"
    vo, lm = pl.get("vooruit", {}), pl.get("lastminute", {})
    negeer = app.store.negeer()
    genegeerd = "".join(
        f"<li>{e(oms)} <form method=post action=/negeer style='display:inline'><input type=hidden name=key value='{e(k)}'>"
        f"<input type=hidden name=terug_naar value=/instellingen><button name=scope value=herstel>herstel</button></form></li>"
        for k, oms in (negeer.get("afspraken") or {}).items())
    genegeerd += "".join(
        f"<li>Altijd: “{e(t)}” <form method=post action=/negeer style='display:inline'><input type=hidden name=titel value='{e(t)}'>"
        f"<input type=hidden name=terug_naar value=/instellingen><button name=scope value=herstel>herstel</button></form></li>"
        for t in negeer.get("titels") or [])
    yaml_tekst = yaml_tekst if yaml_tekst is not None else app.configs.raw_text()
    body = f"""<h1>Instellingen</h1>
<form method=post action=/instellingen class=card>
<h2>Budget en reistijd</h2>{reizen}
<div class=rij><div><label>Vertrekpunt</label><input name=thuis value='{e(str(cfg.get('thuis', '')))}'></div>
<div><label>Personen</label><input type=number name=personen value='{cfg.get('personen', 2)}' min=1></div></div>
<label>Voorkeuren (gaat letterlijk naar Claude)</label><textarea name=voorkeuren rows=8>{e(cfg.get('voorkeuren', '') or '')}</textarea>
<h2 style='margin-top:14px'>Automatische voorstellen</h2>
<div class=rij><div><label>Vooruit: dag</label>{dagsel('vooruit_dag', vo.get('dag', 'zondag'))}</div>
<div><label>tijd</label><input name=vooruit_tijd value='{e(str(vo.get('tijd', '19:00')))}'></div>
<div><label>Last-minute: dag</label>{dagsel('lastminute_dag', lm.get('dag', 'woensdag'))}</div>
<div><label>tijd</label><input name=lastminute_tijd value='{e(str(lm.get('tijd', '18:00')))}'></div></div>
<label><input type=checkbox name=dagjes style='width:auto' {'checked' if pl.get('dagjes', True) else ''}> Ook losse vrije weekenddagen voorstellen (dagje weg)</label>
<label>Woorden in afspraaktitels die nooit blokkeren (komma's)</label>
<input name=negeer_woorden value='{e(", ".join(cfg.get("agenda_regels", {}).get("negeer", []) or []))}'>
<p><button class=hoofd>Opslaan</button></p></form>
<div class=card><h2>Genegeerde afspraken</h2><ul>{genegeerd or '<li class=muted>Geen</li>'}</ul>
<p class=muted>Afspraken negeren doe je in de <a href=/agenda>agenda</a> door erop te klikken.</p></div>
<form method=post action=/instellingen/yaml class=card><h2>Alles (YAML, ook de ideeënlijst)</h2>
<p class=muted>${{NAAM}} wordt ingevuld uit de omgevingsvariabelen in Portainer. Bij opslaan wordt de vorige versie bewaard als config.yaml.vorige.</p>
<textarea class=code name=yaml spellcheck=false>{e(yaml_tekst)}</textarea><p><button class=hoofd>YAML opslaan</button></p></form>"""
    return _page("Instellingen", body, "/instellingen", melding=melding)


def opslaan_snel(app: App, f: dict):
    raw = app.configs.raw()

    def zet(pad, waarde):
        d = raw
        for k in pad[:-1]:
            if d.get(k) is None:
                d[k] = {}
            d = d[k]
        d[pad[-1]] = waarde

    def getal(x):
        v = float(x)
        return int(v) if v.is_integer() else v
    for s in STANDAARD_REIZEN:
        zet(["reizen", s, "budget_eur"], getal(f[f"{s}_budget"]))
        zet(["reizen", s, "max_reistijd_uur"], getal(f[f"{s}_reistijd"]))
    zet(["reizen", "lang", "extra_per_nacht_eur"], getal(f.get("lang_extra", 0) or 0))
    if "budget_eur" in raw:
        del raw["budget_eur"]
    zet(["thuis"], f.get("thuis", "Delft").strip())
    zet(["personen"], int(f.get("personen", 2)))
    from ruamel.yaml.scalarstring import LiteralScalarString
    zet(["voorkeuren"], LiteralScalarString(f.get("voorkeuren", "").replace("\r\n", "\n").rstrip() + "\n"))
    zet(["planning", "vooruit", "dag"], f["vooruit_dag"])
    zet(["planning", "vooruit", "tijd"], f["vooruit_tijd"])
    zet(["planning", "lastminute", "dag"], f["lastminute_dag"])
    zet(["planning", "lastminute", "tijd"], f["lastminute_tijd"])
    zet(["planning", "dagjes"], "dagjes" in f)
    zet(["agenda_regels", "negeer"], [w.strip() for w in f.get("negeer_woorden", "").split(",") if w.strip()])
    app.configs.save_raw(raw)


# ------------------------------------------------------------------- server ----------

def make_handler(app: App):
    def bg(fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

        def _send(self, body: bytes, status=200, ctype="text/html; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, url: str):
            self.send_response(303)
            self.send_header("Location", url)
            self.end_headers()

        def _reply(self, tekst: str, terug: str = "/"):
            # ntfy-knoppen krijgen platte tekst; een browserformulier gaat terug naar de pagina
            if "text/html" in (self.headers.get("Accept") or ""):
                sep = "&" if "?" in terug else "?"
                self._redirect(f"{terug}{sep}melding={quote(tekst)}")
            else:
                self._send(tekst.encode(), ctype="text/plain; charset=utf-8")

        def _form(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            data = parse_qs(self.rfile.read(n).decode("utf-8")) if n else {}
            return {k: v[-1] for k, v in data.items()}

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(u.query).items()}
            parts = u.path.strip("/").split("/")
            try:
                if parts == [""]:
                    return self._send(render_index(app, q.get("melding", "")))
                if parts[0] == "plan" and len(parts) == 2 and (v := app.store.get(parts[1])):
                    return self._send(render_plan(v))
                if parts == ["agenda"]:
                    return self._send(render_agenda(app, q.get("m"), q.get("melding", "")))
                if parts == ["instellingen"]:
                    return self._send(render_instellingen(app, q.get("melding", "")))
                if parts == ["health"]:
                    return self._send(b"ok", ctype="text/plain")
            except Exception as ex:
                log.exception("Fout bij %s", self.path)
                return self._send(_page("Fout", f"<p>Er ging iets mis: {e(str(ex))}</p>"), 500)
            self._send(_page("Niet gevonden", "<p>Niet gevonden.</p>"), 404)

        def do_POST(self):
            parts = urlparse(self.path).path.strip("/").split("/")
            try:
                if parts[0] == "feedback" and len(parts) == 3 and parts[2] in ("up", "down"):
                    ok = app.store.set_feedback(parts[1], parts[2])
                    return self._reply("Dank, genoteerd!" if ok else "Onbekend voorstel", f"/plan/{parts[1]}")
                if parts[0] == "opnieuw" and len(parts) == 2 and app.store.get(parts[1]):
                    bg(app.opnieuw, parts[1])
                    return self._reply("Ik zoek een ander idee; je krijgt zo een melding.", "/")
                f = self._form()
                if parts == ["maak"]:
                    vertrek, terug = parse_local(f["vertrek"]), parse_local(f["terug"])
                    if terug <= vertrek:
                        return self._reply("Het eind moet na het begin liggen.", f.get("terug_naar", "/"))
                    blok = app.custom(vertrek, terug, f.get("notitie", ""))
                    if f.get("soort") in ("weekend", "dagje") and not blok.notitie and not blok.conflicten:
                        blok.soort = f["soort"]
                    bg(lambda: app.run("handmatig", blok))
                    extra = f" Let op: {len(blok.conflicten)} afspraak/afspraken in die periode." if blok.conflicten else ""
                    return self._reply(f"Bezig met een voorstel voor {blok.label()}; je krijgt zo een melding.{extra}", "/")
                if parts == ["negeer"]:
                    scope, terug = f.get("scope"), f.get("terug_naar", "/agenda")
                    if scope == "afspraak":
                        app.store.negeer_afspraak(f["key"], f.get("titel", ""))
                    elif scope == "titel":
                        app.store.negeer_titel(f["titel"])
                    elif scope == "herstel":
                        app.store.herstel(f.get("key"), None)
                        if f.get("titel"):
                            app.store.herstel(None, f["titel"])
                    return self._reply("Opgeslagen.", terug)
                if parts == ["instellingen"]:
                    opslaan_snel(app, f)
                    return self._reply("Instellingen opgeslagen.", "/instellingen")
                if parts == ["instellingen", "yaml"]:
                    try:
                        app.configs.save_text(f.get("yaml", "").replace("\r\n", "\n"))
                    except Exception as ex:
                        return self._send(render_instellingen(app, f"Niet opgeslagen: {ex}", f.get("yaml", "")), 400)
                    return self._reply("YAML opgeslagen.", "/instellingen")
            except Exception as ex:
                log.exception("Fout bij POST %s", self.path)
                return self._send(_page("Fout", f"<p>Er ging iets mis: {e(str(ex))}</p>"), 500)
            self._send(b"Niet gevonden", 404, "text/plain")

    return H


def serve(app: App, port: int):
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(app))
    log.info("Webserver op poort %d", port)
    srv.serve_forever()
