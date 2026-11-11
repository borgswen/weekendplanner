from planner import reistools as rt

FLIX_STAD = {"Rotterdam": [{"id": "R", "name": "Rotterdam"}], "Gent": [{"id": "G", "name": "Gent"}]}
FLIX_SEARCH = {"stations": {"s1": {"name": "Rotterdam CS"}, "s2": {"name": "Gent Dampoort"}},
               "trips": [{"results": {
                   "a": {"status": "available", "departure": {"date": "2026-12-11T17:50:00+01:00", "station_id": "s1"},
                         "arrival": {"date": "2026-12-11T19:55:00+01:00", "station_id": "s2"},
                         "duration": {"hours": 2, "minutes": 5}, "price": {"total": 24.48, "total_with_platform_fee": 25.47},
                         "available": {"seats": 34}, "legs": [{"means_of_transport": "bus"}]},
                   "b": {"status": "full", "departure": {"date": "x", "station_id": "s1"}, "arrival": {"date": "x", "station_id": "s2"},
                         "duration": {"hours": 1, "minutes": 0}, "price": {}, "legs": []}}}]}
DB_LOC = {"Delft": [{"id": "8400170", "name": "Delft"}], "Gent": [{"id": "8892007", "name": "Gent-Sint-Pieters"}]}
DB_J = {"journeys": [{"price": {"amount": 39.9, "currency": "EUR"}, "legs": [
    {"origin": {"name": "Delft"}, "destination": {"name": "Rotterdam Centraal"}, "departure": "2026-12-11T16:05:00+01:00",
     "arrival": "2026-12-11T16:19:00+01:00", "line": {"name": "IC 2236"}},
    {"walking": True},
    {"origin": {"name": "Rotterdam Centraal"}, "destination": {"name": "Gent-Sint-Pieters"}, "departure": "2026-12-11T16:32:00+01:00",
     "arrival": "2026-12-11T18:10:00+01:00", "line": {"name": "EuroCity Direct 9245"}}]}]}


def fake_get(url, params=None, timeout=25):
    if url.endswith("/autocomplete/cities"):
        return FLIX_STAD[params["q"]]
    if url.endswith("/v4/search"):
        assert params["departure_date"] == "11.12.2026"
        return FLIX_SEARCH
    if url.endswith("/locations"):
        return DB_LOC[params["query"]]
    if url.endswith("/journeys"):
        assert params["tickets"] == "true"
        return DB_J
    raise AssertionError(url)


def test_flixbus(monkeypatch):
    monkeypatch.setattr(rt, "_get", fake_get)
    r = rt.zoek_flixbus("Rotterdam", "Gent", "2026-12-11")
    assert len(r["ritten"]) == 1
    rit = r["ritten"][0]
    assert rit["prijs_totaal_eur"] == 25.47 and rit["duur_min"] == 125 and rit["van_halte"] == "Rotterdam CS"
    assert "rideDate=11.12.2026" in r["boeken"] and "adult=2" in r["boeken"]


def test_trein(monkeypatch):
    monkeypatch.setattr(rt, "_get", fake_get)
    r = rt.zoek_trein("Delft", "Gent", "2026-12-11T16:00")
    j = r["reizen"][0]
    assert j["duur_min"] == 125 and j["overstappen"] == 1 and j["prijs_p_p_eur"] == 39.9
    assert j["ritten"][1].startswith("EuroCity Direct 9245: Rotterdam Centraal 16:32")
    assert "so=Delft" in r["boeken"]["bahn_de"] and "hd=2026-12-11T16%3A00%3A00" in r["boeken"]["bahn_de"]


def test_slaap_links():
    l = rt.links_slapen("Winterberg", "2026-12-11", "2026-12-13", 2, 90)
    assert "checkin=2026-12-11" in l["booking"] and "price%3DEUR-min-90-1" in l["booking"]
    assert l["airbnb"].startswith("https://www.airbnb.nl/s/Winterberg/homes?") and "price_max=90" in l["airbnb"]
