from datetime import date, datetime, timedelta

from planner.calendars import TZ, Blok
from planner.config import STANDAARD_REIZEN
from planner.ideas import candidates
from planner.weather import bft, voldoet


class FakeWeather:
    def __init__(self, dag):
        self.dag = dag

    def for_days(self, locatie, dagen):
        return {d.isoformat(): self.dag for d in dagen} if locatie and self.dag else None


def _blok(dagen_vooruit=3, nachten=2):
    vr = datetime.combine(date.today() + timedelta(days=dagen_vooruit), datetime.min.time(), TZ).replace(hour=16)
    return Blok("weekend" if nachten else "dagje", vr, vr + timedelta(days=nachten, hours=3), nachten)


def _cfg(*ideeen):
    return {"reizen": {k: dict(v) for k, v in STANDAARD_REIZEN.items()}, "ideeen": list(ideeen)}


ZEILEN = {"id": "zeilen", "soorten": ["dagje", "kort", "lang"], "locatie": {"lat": 1, "lon": 1}, "alleen_lastminute": True,
          "weer": {"wind_bft_min": 2, "wind_bft_max": 5, "temp_min": 14, "regen_max_mm": 4}}
STAD = {"id": "stad", "soorten": ["dagje", "kort", "lang"]}
HARZ = {"id": "harz", "soorten": ["lang"], "min_nachten": 2, "reistijd_uur": 5.5}
SKI = {"id": "ski", "reistijd_uur": 3.75}


def test_bft():
    assert [bft(x) for x in (0, 5, 6, 19, 20, 38, 39)] == [0, 1, 2, 3, 4, 5, 6]


def test_sailing_needs_good_weather():
    goed = {"temp_max": 18, "regen_mm": 0, "wind_bft": 3}
    storm = {"temp_max": 18, "regen_mm": 0, "wind_bft": 7}
    assert [c["id"] for c in candidates(_cfg(ZEILEN, STAD), _blok(), "lastminute", FakeWeather(goed))[0]] == ["zeilen", "stad"]
    kand, af = candidates(_cfg(ZEILEN, STAD), _blok(), "lastminute", FakeWeather(storm))
    assert [c["id"] for c in kand] == ["stad"] and "weer past niet" in af[0]


def test_sailing_not_proposed_without_forecast():
    kand, _ = candidates(_cfg(ZEILEN, STAD), _blok(30), "vooruit", FakeWeather(None))
    assert [c["id"] for c in kand] == ["stad"]


def test_max_travel_time_per_trip_length():
    cfg = _cfg(HARZ, SKI, STAD)
    assert [c["id"] for c in candidates(cfg, _blok(nachten=2), "vooruit", FakeWeather(None))[0]] == ["ski", "stad"]
    cfg["reizen"]["lang"]["max_reistijd_uur"] = 6
    assert "harz" in [c["id"] for c in candidates(cfg, _blok(nachten=2), "vooruit", FakeWeather(None))[0]]
    assert [c["id"] for c in candidates(cfg, _blok(nachten=0), "vooruit", FakeWeather(None))[0]] == ["stad"]


def test_exclusions():
    kand, _ = candidates(_cfg(STAD), _blok(), "vooruit", FakeWeather(None), {"stad"})
    assert kand == []


def test_voldoet_missing_value_fails():
    assert not voldoet({"sneeuwhoogte_cm": None}, {"sneeuwhoogte_min_cm": 10})
