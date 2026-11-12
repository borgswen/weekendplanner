import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseOebb, maakOebb} from '../src/bronnen/oebb.js';
import {nmbsPrijs, afstandKm} from '../src/nmbs.js';
import {nsiCode, land} from '../src/stations.js';
import {bouwIndex, zoekRange} from '../src/bronnen/sncf.js';
import {leesTrips, fareVerzoek, leesPrijzen} from '../src/bronnen/ojp.js';
import {maakTest, rit, AMSTERDAM, SALZBURG, WIEN, BRUSSEL, BRUGGE, ZUERICH, BERN, PARIS_LYON, LYON, GRENOBLE, PARIS_NORD, MARSEILLE, DELFT} from './helpers.js';

const nachttrein = (prijsDb) => ({type: 'journey', legs: [
	rit(AMSTERDAM, SALZBURG, '2026-12-11T18:01:00+01:00', '2026-12-12T06:46:00+01:00', 'NJ 40421', 'ÖBB'),
	{walking: true},
	rit(SALZBURG, WIEN, '2026-12-12T07:07:00+01:00', '2026-12-12T09:32:00+01:00', 'RJX 19969', 'ÖBB'),
], price: prijsDb ? {amount: prijsDb, currency: 'EUR'} : undefined});

test('stations in Oostenrijk, Zwitserland en Frankrijk hebben een land en NS International-code', () => {
	assert.equal(land('8103000'), 'AT');
	assert.equal(nsiCode('8103000'), 'ATWIH');
	assert.equal(land('8503000'), 'CH');
	assert.ok(nsiCode('8503000'));
	assert.equal(nsiCode('8727100'), 'FRPNO');
	assert.equal(land('8799999'), 'FR'); // onbekend station: land uit het nummer
});

test('ÖBB-antwoorden (vorm van de webshop) worden goed gelezen', () => {
	const dir = new URL('./fixtures/', import.meta.url);
	const tt = JSON.parse(readFileSync(new URL('oebb-timetable.json', dir)));
	const pr = JSON.parse(readFileSync(new URL('oebb-prices.json', dir)));
	const v = parseOebb(tt, pr);
	assert.equal(v.length, 2);
	assert.deepEqual(v[0], {vertrek: '2026-12-01T18:01', aankomst: '2026-12-02T09:32', treinen: ['NJ 40421', 'RJX 19969'], perPersoon: 59.8, eersteKlas: false});
	assert.equal(v[1].perPersoon, 49.9);
});

test('Amsterdam → Wenen: ÖBB-prijs (per persoon × 2) naast DB en NS International', async () => {
	const {zoeker, log} = maakTest({
		reizen: [nachttrein(139.98)],
		nsi: [['2026-12-11T18:01', '2026-12-12T09:32', 129.98, 300]],
		oebb: [['2026-12-11T18:01', '2026-12-12T09:32', 59.9]],
	});
	const r = await zoeker.reizen({van: 'Amsterdam', naar: 'Wenen', vertrek: '2026-12-11T17:00', personen: 2, leeftijden: [], studentenov: []});
	const j = r.reizen[0];
	assert.deepEqual(j.landen, ['NL', 'AT']);
	assert.deepEqual(j.prijzen.map((p) => [p.bron, p.totaal_eur]), [['bahn.de', 139.98], ['NS International', 129.98], ['ÖBB', 119.8]]);
	assert.equal(j.goedkoopst.bron, 'ÖBB');
	assert.deepEqual(log.oebb[0], {van: '8400058', naar: '8103000', tijd: '2026-12-11T18:01', vanNaam: 'Amsterdam Centraal', naarNaam: 'Wien Hbf'});
	assert.equal(r.bronnen['ÖBB'], 'ok');
});

test('ÖBB geblokkeerd: status, de andere prijzen blijven', async () => {
	const {zoeker} = maakTest({reizen: [nachttrein(139.98)], nsi: [], oebb: 'blokkade'});
	const r = await zoeker.reizen({van: 'Amsterdam', naar: 'Wenen', vertrek: '2026-12-11T17:00', personen: 2, leeftijden: [], studentenov: []});
	assert.match(r.bronnen['ÖBB'], /^geblokkeerd.*botcontrole/);
	assert.equal(r.reizen[0].goedkoopst.bron, 'bahn.de');
});

test('ÖBB-client: sessie, travelAction, dienstregeling en prijzen in de goede volgorde', async () => {
	const calls = [];
	const json = (data) => new Response(JSON.stringify(data), {headers: {'content-type': 'application/json'}});
	const fetchFn = async (url, opt) => {
		const u = new URL(url);
		calls.push({pad: u.pathname, opt, query: u.search});
		if (u.pathname === '/api/domain/v1/anonymousToken') {
			return json({accessToken: 'tok', sessionId: 'ses'});
		}
		if (u.pathname === '/api/offer/v2/travelActions') {
			return json({travelActions: [{id: 'ta1', entrypoint: {id: 'timetable'}}]});
		}
		if (u.pathname === '/api/hafas/v4/timetable') {
			return json(JSON.parse(readFileSync(new URL('./fixtures/oebb-timetable.json', import.meta.url))));
		}
		if (u.pathname === '/api/offer/v1/prices') {
			return json(JSON.parse(readFileSync(new URL('./fixtures/oebb-prices.json', import.meta.url))));
		}
		throw new Error(u.pathname);
	};
	const o = maakOebb({userAgent: 'test', fetchFn});
	const v = await o.zoek('8400058', '8103000', '2026-12-01T18:00');
	assert.deepEqual(calls.map((c) => c.pad), ['/api/domain/v1/anonymousToken', '/api/offer/v2/travelActions', '/api/hafas/v4/timetable', '/api/offer/v1/prices']);
	assert.equal(calls[1].opt.headers.AccessToken, 'tok');
	assert.deepEqual(JSON.parse(calls[1].opt.body).from, {number: 8400058, name: ''});
	assert.equal(JSON.parse(calls[2].opt.body).travelActionId, 'ta1');
	assert.match(decodeURIComponent(calls[3].query), /connectionIds\[\]=d6d3a1/);
	assert.equal(v[0].perPersoon, 59.8);
});

test('ÖBB-client: HTML-botcontrole wordt herkend als blokkade', async () => {
	const fetchFn = async () => new Response('<html>Just a moment...</html>', {status: 403, headers: {'content-type': 'text/html'}});
	const o = maakOebb({userAgent: 'test', fetchFn});
	await assert.rejects(o.zoek('8400058', '8103000', '2026-12-01T18:00'), {name: 'Error', message: /botcontrole/});
});

test('NMBS-schatting: grenzen, jongeren, weekend en 1e klas (tarief 2026)', () => {
	assert.equal(nmbsPrijs(1), 2.6);
	assert.equal(nmbsPrijs(200), 21.3); // 20,90 + 2,14%
	assert.equal(nmbsPrijs(200, {leeftijd: 23}), 12.8); // 40% korting
	assert.equal(nmbsPrijs(200, {moment: '2026-12-12T10:00:00+01:00'}), 14.9); // zaterdag: 30% korting
	assert.equal(nmbsPrijs(200, {klasse: 1}), 34);
	const km = afstandKm([rit(BRUSSEL, BRUGGE, 'a', 'b', 'IC')]);
	assert.ok(km > 100 && km < 120, `Brussel–Brugge ca. 110 spoor-km, kreeg ${km}`);
});

test('NMBS-schatting tegen echte prijzen (65+/jongeren, tarief oktober 2025)', () => {
	// Bron: Neos, voorbeelden vanuit Turnhout. Corrigeer de indexatie van februari 2026 terug.
	const plek = (lat, lon) => ({location: {latitude: lat, longitude: lon}});
	const turnhout = plek(51.3223, 4.9386);
	const echt = [[plek(51.2172, 4.4211), 5.8], [plek(51.0177, 4.4828), 6.1], [plek(50.86, 4.3617), 8.6], [plek(51.2283, 2.9256), 12.5]];
	for (const [doel, prijs] of echt) {
		const schatting = nmbsPrijs(afstandKm([{origin: turnhout, destination: doel}]), {leeftijd: 70}) / 1.0214;
		assert.ok(Math.abs(schatting - prijs) / prijs < 0.12, `schatting ${schatting.toFixed(2)} vs echt ${prijs}`);
	}
});

test('afstand langs tussenstops is nauwkeuriger dan hemelsbreed', () => {
	const p = (lat, lon) => ({location: {latitude: lat, longitude: lon}});
	const leg = {origin: p(51.036, 3.710), destination: p(50.836, 4.336),
		stopovers: [{stop: p(50.936, 3.950)}, {stop: p(50.881, 4.072)}]}; // Gent – Aalst – Denderleeuw-achtig – Brussel
	const km = afstandKm([leg]);
	assert.ok(km > 50 && km < 60, String(km));
});

test('België binnenland krijgt een gemarkeerde schatting', async () => {
	const {zoeker} = maakTest({reizen: [{type: 'journey', legs: [rit(BRUSSEL, BRUGGE, '2026-12-12T10:00:00+01:00', '2026-12-12T11:00:00+01:00', 'IC 1834', 'SNCB')]}]});
	const r = await zoeker.reizen({van: 'Brussel', naar: 'Brugge', vertrek: '2026-12-12T09:00', personen: 2, leeftijden: [22, 30], studentenov: []});
	const p = r.reizen[0].prijzen[0];
	assert.equal(p.bron, 'NMBS (schatting)');
	assert.equal(p.schatting, true);
	assert.ok(p.totaal_eur > 15 && p.totaal_eur < 30, String(p.totaal_eur));
	assert.match(r.bronnen.NMBS, /schatting/);
});

const zuerichBern = [{type: 'journey', legs: [rit(ZUERICH, BERN, '2026-12-12T10:02:00+01:00', '2026-12-12T10:58:00+01:00', 'IC 8', 'SBB')]}];

test('Zwitserland binnenland zonder OJP-sleutel: status en link', async () => {
	const {zoeker} = maakTest({reizen: zuerichBern});
	const r = await zoeker.reizen({van: 'Zürich', naar: 'Bern', vertrek: '2026-12-12T10:00', personen: 2, leeftijden: [], studentenov: []});
	assert.equal(r.reizen[0].goedkoopst, null);
	assert.match(r.bronnen['SBB (OJP Fare)'], /OJP_API_KEY/);
	assert.ok(r.links.sbb);
});

test('Zwitserland binnenland met OJP Fare: CHF omgerekend, × personen', async () => {
	const {zoeker, log} = maakTest({reizen: zuerichBern, ojpTrips: [{vertrek: '2026-12-12T09:02:00Z', aankomst: '2026-12-12T09:58:00Z', chf: 56, compleet: true}]});
	const r = await zoeker.reizen({van: 'Zürich', naar: 'Bern', vertrek: '2026-12-12T10:00', personen: 2, leeftijden: [], studentenov: []});
	const p = r.reizen[0].prijzen[0];
	assert.equal(p.bron, 'SBB (OJP Fare)');
	assert.equal(p.per_persoon_eur, 60.48);
	assert.equal(p.totaal_eur, 120.96);
	assert.equal(log.ojp[0].iso, '2026-12-12T09:02:00Z');
	assert.match(r.bronnen['SBB (OJP Fare)'], /^ok/);
});

const SNCF_RECORDS = [
	{transporteur: 'TGV INOUI', gare_origine: 'PARIS GARE DE LYON', gare_origine_code_uic: '87686006', gare_destination: 'LYON PART DIEU', gare_destination_code_uic: '87723197', classe: '2', profil_tarifaire: 'Tarif Normal', prix_minimum: 25, prix_maximum: 123},
	{transporteur: 'TGV INOUI', gare_origine: 'PARIS GARE DE LYON', gare_origine_code_uic: '87686006', gare_destination: 'LYON PART DIEU', gare_destination_code_uic: '87723197', classe: '1', profil_tarifaire: 'Tarif Normal', prix_minimum: 40, prix_maximum: 180},
	{transporteur: 'OUIGO', gare_origine: 'PARIS GARE DE LYON', gare_origine_code_uic: '87686006', gare_destination: 'LYON PART DIEU', gare_destination_code_uic: '87723197', classe: '2', profil_tarifaire: 'Tarif Normal', prix_minimum: 19, prix_maximum: 89},
	{transporteur: 'TGV INOUI', gare_origine: 'PARIS GARE DE LYON', gare_origine_code_uic: '87686006', gare_destination: 'LYON PART DIEU', gare_destination_code_uic: '87723197', classe: '2', profil_tarifaire: 'Tarif Avantage', prix_minimum: 15, prix_maximum: 80},
];

test('SNCF open data: Parijs → Lyon geeft een prijsrange (2e klas, normaal tarief)', async () => {
	const {zoeker} = maakTest({sncfRecords: SNCF_RECORDS,
		reizen: [{type: 'journey', legs: [rit(PARIS_LYON, LYON, '2026-12-12T10:00:00+01:00', '2026-12-12T11:56:00+01:00', 'TGV 6611', 'SNCF')]}]});
	const r = await zoeker.reizen({van: 'Parijs', naar: 'Lyon', vertrek: '2026-12-12T09:00', personen: 2, leeftijden: [], studentenov: []});
	const p = r.reizen[0].prijzen[0];
	assert.equal(p.bron, 'SNCF (open data)');
	assert.deepEqual([p.prijs_van_pp, p.prijs_tot_pp, p.per_persoon_eur, p.totaal_eur], [19, 123, 71, 142]);
	assert.equal(p.schatting, true);
	assert.equal(r.reizen[0].goedkoopst.schatting, true);
});

test('SNCF open data: TER-rit zonder data maakt het een deelprijs', async () => {
	const {zoeker} = maakTest({sncfRecords: SNCF_RECORDS, reizen: [{type: 'journey', legs: [
		rit(PARIS_LYON, LYON, '2026-12-12T10:00:00+01:00', '2026-12-12T11:56:00+01:00', 'TGV 6611', 'SNCF'),
		{walking: true},
		rit(LYON, GRENOBLE, '2026-12-12T12:15:00+01:00', '2026-12-12T13:40:00+01:00', 'TER 17617', 'SNCF'),
	]}]});
	const r = await zoeker.reizen({van: 'Parijs', naar: 'Grenoble', vertrek: '2026-12-12T09:00', personen: 1, leeftijden: [], studentenov: []});
	assert.equal(r.reizen[0].prijzen[0].deelprijs, true);
	assert.equal(r.reizen[0].goedkoopst, null);
});

test('SNCF open data: andere veldnamen en stationsnamen werken ook', () => {
	const idx = bouwIndex([{origine: 'Paris Gare de Lyon (intramuros)', destination: 'Lyon Part-Dieu', classe: '2nde', prix_min: '25,00', prix_max: '99,00'}]);
	const r = zoekRange(idx, {vanId: 'x', naarId: 'y', vanNaam: 'Paris Gare de Lyon', naarNaam: 'Lyon Part-Dieu'});
	assert.deepEqual([r.min, r.max], [25, 99]);
});

test('OJP: trips lezen (perron → station), fare-verzoek bouwen en prijzen lezen', () => {
	const trip = `<?xml version="1.0"?><OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri"><OJPResponse><siri:ServiceDelivery><OJPTripDelivery>
<TripResponseContext><Places>
<Place><StopPoint><siri:StopPointRef>ch:1:sloid:3000:4:7</siri:StopPointRef><ParentRef>ch:1:sloid:3000</ParentRef></StopPoint></Place>
<Place><StopPoint><siri:StopPointRef>ch:1:sloid:7000:2:3</siri:StopPointRef><ParentRef>ch:1:sloid:7000</ParentRef></StopPoint></Place>
</Places></TripResponseContext>
<TripResult><Id>r1</Id><Trip><Id>t1</Id><Leg><Id>1</Id><TimedLeg>
<LegBoard><siri:StopPointRef>ch:1:sloid:3000:4:7</siri:StopPointRef><ServiceDeparture><TimetabledTime>2026-12-12T09:02:00Z</TimetabledTime></ServiceDeparture></LegBoard>
<LegAlight><siri:StopPointRef>ch:1:sloid:7000:2:3</siri:StopPointRef><ServiceArrival><TimetabledTime>2026-12-12T09:58:00Z</TimetabledTime></ServiceArrival></LegAlight>
</TimedLeg></Leg></Trip></TripResult>
</OJPTripDelivery></siri:ServiceDelivery></OJPResponse></OJP>`;
	const trips = leesTrips(trip);
	assert.equal(trips.length, 1);
	assert.deepEqual([trips[0].vertrek, trips[0].aankomst], ['2026-12-12T09:02:00Z', '2026-12-12T09:58:00Z']);
	assert.match(trips[0].xml, /<siri:StopPointRef>ch:1:sloid:3000<\/siri:StopPointRef>/);
	const verzoek = fareVerzoek(trips, 'test_prod');
	assert.match(verzoek, /<TripFareRequest><Trip>/);
	assert.match(verzoek, /<FareClass>secondClass<\/FareClass>/);
	const antwoord = `<OJP xmlns="http://www.vdv.de/ojp"><OJPResponse><OJPFareDelivery>
<FareResult><Id>1</Id>
<TripFareResult><FromLegIdRef>1</FromLegIdRef><ToLegIdRef>1</ToLegIdRef>
<FareProduct><FareProductId>2361</FareProductId><Price>9.00</Price><Currency>CHF</Currency><FareClass>secondClass</FareClass></FareProduct>
<FareProduct><FareProductId>10972</FareProductId><Price>56.00</Price><Currency>CHF</Currency><FareClass>secondClass</FareClass></FareProduct>
<FareProduct><FareProductId>10972</FareProductId><Price>98.00</Price><Currency>CHF</Currency><FareClass>firstClass</FareClass></FareProduct>
<FareProduct><FareProductId>11001</FareProductId><Price>31.40</Price><Currency>CHF</Currency><FareClass>secondClass</FareClass></FareProduct>
</TripFareResult></FareResult></OJPFareDelivery></OJPResponse></OJP>`;
	assert.deepEqual(leesPrijzen(antwoord), [{chf: 31.4, compleet: true}]); // dagkaart 2361 genegeerd
	assert.deepEqual(leesPrijzen(antwoord, 1), [{chf: 98, compleet: true}]);
});

const SNCF_FR = [
	{gare_origine: 'PARIS GARE DE LYON', gare_origine_code_uic: '87686006', gare_destination: 'GRENOBLE', gare_destination_code_uic: '87747006', classe: '2', profil_tarifaire: 'Tarif Normal', prix_minimum: 29, prix_maximum: 111},
	{gare_origine: 'PARIS GARE DE LYON', gare_origine_code_uic: '87686006', gare_destination: 'MARSEILLE ST CHARLES', gare_destination_code_uic: '87751008', classe: '2', profil_tarifaire: 'Tarif Normal', prix_minimum: 35, prix_maximum: 135},
];

test('Delft → Grenoble: NS International tot Parijs + SNCF voor de rest', async () => {
	const {zoeker, log} = maakTest({sncfRecords: SNCF_FR,
		reizen: [{type: 'journey', legs: [
			rit(DELFT, PARIS_NORD, '2026-12-11T08:13:00+01:00', '2026-12-11T11:47:00+01:00', 'EST 9318', 'Eurostar'),
			{walking: true},
			rit(PARIS_LYON, GRENOBLE, '2026-12-11T12:41:00+01:00', '2026-12-11T15:41:00+01:00', 'TGV 6911', 'SNCF'),
		]}],
		nsi: [['2026-12-11T08:13', '2026-12-11T11:47', 98, 200]],
	});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Grenoble', vertrek: '2026-12-11T08:00', personen: 2, leeftijden: [], studentenov: []});
	const j = r.reizen[0];
	assert.deepEqual(log.nsi[0], {van: 'NLDET', naar: 'FRPNO', tijd: '2026-12-11T08:13:00', personen: 2});
	const nsi = j.prijzen.find((p) => p.bron === 'NS International');
	assert.equal(nsi.deelprijs, true);
	assert.match(nsi.toelichting, /tot Paris Gare du Nord/);
	const combi = j.prijzen.find((p) => p.bron === 'NS International + SNCF (open data)');
	assert.equal(combi.totaal_eur, 98 + 70 * 2); // SNCF-midden (29+111)/2 = 70 p.p.
	assert.equal(combi.schatting, true);
	assert.equal(j.goedkoopst.bron, 'NS International + SNCF (open data)');
});

test('Binnen Frankrijk: NS International wordt ook gevraagd (Parijs via stadscode)', async () => {
	const {zoeker, log} = maakTest({sncfRecords: SNCF_FR,
		reizen: [{type: 'journey', legs: [rit(PARIS_LYON, MARSEILLE, '2026-12-12T10:00:00+01:00', '2026-12-12T13:20:00+01:00', 'TGV 6107', 'SNCF')]}],
		nsi: [['2026-12-12T10:00', '2026-12-12T13:20', 79, 160]],
	});
	const r = await zoeker.reizen({van: 'Parijs', naar: 'Marseille', vertrek: '2026-12-12T09:00', personen: 2, leeftijden: [], studentenov: []});
	assert.deepEqual([log.nsi[0].van, log.nsi[0].naar], ['FRPAR', 'FRMSC']);
	const j = r.reizen[0];
	assert.deepEqual(j.prijzen.map((p) => [p.bron, p.totaal_eur]), [['NS International', 79], ['SNCF (open data)', 170]]);
	assert.equal(j.goedkoopst.bron, 'NS International');
});

test('NS International: als één van twee zoekvragen faalt, zegt de status dat', async () => {
	const {zoeker} = maakTest({sncfRecords: SNCF_FR,
		reizen: [
			{type: 'journey', legs: [rit(DELFT, PARIS_NORD, '2026-12-11T08:13:00+01:00', '2026-12-11T11:47:00+01:00', 'EST 9318', 'Eurostar')]},
			{type: 'journey', legs: [
				rit(DELFT, PARIS_NORD, '2026-12-11T09:13:00+01:00', '2026-12-11T12:47:00+01:00', 'EST 9320', 'Eurostar'),
				{walking: true},
				rit(PARIS_LYON, MARSEILLE, '2026-12-11T13:30:00+01:00', '2026-12-11T16:50:00+01:00', 'TGV 6111', 'SNCF'),
			]},
		],
		nsi: (tijd) => {
			if (tijd.startsWith('2026-12-11T09:13')) {
				throw new Error('HTTP 500');
			}
			return [['2026-12-11T08:13', '2026-12-11T11:47', 98, 200]];
		},
	});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Marseille', vertrek: '2026-12-11T08:00', personen: 1, leeftijden: [], studentenov: []});
	assert.match(r.bronnen['NS International'], /^deels: 1 van 2 zoekvragen gelukt; fout: HTTP 500/);
	assert.equal(r.reizen[0].goedkoopst.bron, 'NS International');
});
