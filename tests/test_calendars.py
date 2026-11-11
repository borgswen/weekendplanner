from datetime import date, datetime

from planner.calendars import TZ, custom_block, free_blocks, parse_events

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:test
BEGIN:VEVENT
UID:lab
DTSTART;TZID=Europe/Amsterdam:20261113T080000
DTEND;TZID=Europe/Amsterdam:20261113T150000
RRULE:FREQ=WEEKLY;BYDAY=FR
SUMMARY:Projectlab
END:VEVENT
BEGIN:VEVENT
UID:duinrell
DTSTART;VALUE=DATE:20261127
DTEND;VALUE=DATE:20261130
TRANSP:TRANSPARENT
SUMMARY:Duinrell weekend
END:VEVENT
BEGIN:VEVENT
UID:knutselen
DTSTART;TZID=Europe/Amsterdam:20261220T111500
DTEND;TZID=Europe/Amsterdam:20261220T233000
SUMMARY:Carnaval kostuum knutselen
END:VEVENT
BEGIN:VEVENT
UID:feest
DTSTART;TZID=Europe/Amsterdam:20261204T153000
DTEND;TZID=Europe/Amsterdam:20261204T220000
SUMMARY:Secret scorpenta
END:VEVENT
BEGIN:VEVENT
UID:jarig
DTSTART;VALUE=DATE:20270109
DTEND;VALUE=DATE:20270110
SUMMARY:Tjeerd jarig
END:VEVENT
BEGIN:VEVENT
UID:afgeslagen
DTSTART;TZID=Europe/Amsterdam:20270116T120000
DTEND;TZID=Europe/Amsterdam:20270116T180000
SUMMARY:Saaie vergadering
ATTENDEE;PARTSTAT=DECLINED:mailto:ik@example.com
END:VEVENT
BEGIN:VEVENT
UID:geannuleerd
DTSTART;TZID=Europe/Amsterdam:20270123T120000
DTEND;TZID=Europe/Amsterdam:20270123T180000
STATUS:CANCELLED
SUMMARY:Gaat niet door
END:VEVENT
BEGIN:VEVENT
UID:zaterdag
DTSTART;TZID=Europe/Amsterdam:20270130T120000
DTEND;TZID=Europe/Amsterdam:20270130T180000
SUMMARY:Borrel
END:VEVENT
END:VCALENDAR
"""

CFG = {
    "agenda_regels": {"negeer": ["jarig"]},
    "weekend": {"vertrek_vrijdag": "16:00", "vertrek_zaterdag": "08:00",
                "terug_zaterdag": "22:00", "terug_zondag": "19:00"},
    "uitsluiten": [{"van": "2027-01-01", "tot": "2027-01-03"}],
}


def _events():
    s, e = datetime(2026, 11, 10, tzinfo=TZ), datetime(2027, 2, 5, tzinfo=TZ)
    return parse_events(ICS, "test", s, e, email="ik@example.com")


def _weekends(negeer=None):
    return {w.key: w for w in free_blocks(_events(), CFG, date(2026, 11, 10), date(2027, 2, 1), negeer)}


def test_weekly_lab_until_15_does_not_block_friday_departure():
    assert _weekends()["2026-11-13"].nachten == 2


def test_transparent_multiday_event_still_blocks():
    assert "2026-11-27" not in _weekends()


def test_friday_evening_party_gives_saturday_departure():
    w = _weekends()["2026-12-04"]
    assert w.nachten == 1 and w.vertrek.hour == 8


def test_sunday_event_gives_friday_to_saturday():
    w = _weekends()["2026-12-18"]
    assert w.nachten == 1 and w.terug.day == 19


def test_ignored_birthday_and_context():
    w = _weekends()["2027-01-08"]
    assert w.nachten == 2
    assert any("Tjeerd jarig" in o for o in w.omheen)


def test_declined_and_cancelled_ignored():
    assert _weekends()["2027-01-15"].nachten == 2
    assert _weekends()["2027-01-22"].nachten == 2


def test_saturday_afternoon_gives_sunday_dagje():
    ws = _weekends()
    assert "2027-01-29" not in ws
    dagje = ws["dagje:2027-01-31T08:30"]
    assert dagje.nachten == 0 and dagje.reissoort == "dagje"


def test_ignore_single_event_and_title_from_gui():
    ev = next(e for e in _events() if e.titel == "Borrel")
    assert "2027-01-29" in _weekends({"afspraken": {ev.key: "Borrel"}})
    assert "2027-01-29" in _weekends({"titels": ["borrel"]})


def test_custom_block_on_weekdays_reports_conflicts():
    b = custom_block(_events(), CFG, datetime(2026, 11, 26, 9, tzinfo=TZ), datetime(2026, 11, 28, 18, tzinfo=TZ), "sauna")
    assert b.soort == "eigen" and b.nachten == 2 and b.notitie == "sauna"
    assert any("Duinrell" in c for c in b.conflicten)
    assert [d.day for d in b.activiteitdagen] == [26, 27, 28]


def test_excluded_period():
    assert "2027-01-01" not in _weekends()
