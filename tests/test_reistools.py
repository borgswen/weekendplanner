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


TP = {"van": "Delft", "naar": "Köln Hbf", "bronnen": {"bahn.de": "ok", "NS International": "ok"},
      "links": {"bahn_de": "https://int.bahn.de/x"}, "let_op": "samen",
      "reizen": [{"vertrek": "2026-12-11T16:20:00+01:00", "aankomst": "2026-12-11T19:40:00+01:00", "duur_min": 200,
                  "overstappen": 1, "landen": ["NL", "DE"],
                  "ritten": [{"trein": "IC 2245", "van": "Delft", "vertrek": "2026-12-11T16:20:00+01:00",
                              "naar": "Utrecht Centraal", "aankomst": "2026-12-11T17:00:00+01:00"}],
                  "prijzen": [{"bron": "bahn.de", "totaal_eur": 79.98, "per_persoon_eur": 39.99, "deelprijs": False,
                               "boeken": "https://int.bahn.de/y", "klasse": 2},
                              {"bron": "NS International", "totaal_eur": 69.98, "per_persoon_eur": 34.99,
                               "tarief": "Second Class", "deelprijs": False, "boeken": "https://nsi/z", "klasse": 2}],
                  "goedkoopst": {"bron": "NS International", "totaal_eur": 69.98, "per_persoon_eur": 34.99}}]}


def test_trein_via_treinprijzen(monkeypatch):
    calls = []

    def fake(url, params=None, timeout=25):
        calls.append((url, params))
        assert url == "http://tp:8089/reizen"
        return TP

    monkeypatch.setattr(rt, "TREINPRIJZEN", "http://tp:8089")
    monkeypatch.setattr(rt, "_get", fake)
    r = rt.zoek_trein("Delft", "Keulen", "2026-12-11T16:00:00", personen=2)
    assert calls[0][1] == {"van": "Delft", "naar": "Keulen", "personen": 2, "aantal": 4, "vertrek": "2026-12-11T16:00"}
    j = r["reizen"][0]
    assert j["goedkoopst"]["bron"] == "NS International"
    assert j["ritten"] == ["IC 2245: Delft 16:20 → Utrecht Centraal 17:00"]
    assert "klasse" not in j["prijzen"][0] and j["prijzen"][1]["tarief"] == "Second Class"
    assert r["bronnen"]["NS International"] == "ok"


def test_trein_valt_terug_op_db_rest(monkeypatch):
    def fake(url, params=None, timeout=25):
        if url.startswith("http://tp:8089"):
            raise ConnectionError("weg")
        return fake_get(url, params, timeout)

    monkeypatch.setattr(rt, "TREINPRIJZEN", "http://tp:8089")
    monkeypatch.setattr(rt, "_get", fake)
    r = rt.zoek_trein("Delft", "Gent", "2026-12-11T16:00")
    assert r["reizen"][0]["prijs_p_p_eur"] == 39.9 and "treinprijzen-service" in r["waarschuwing"]
