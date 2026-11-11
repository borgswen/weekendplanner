import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DateTime} from 'luxon';
import {createClient} from 'db-vendo-client';
import {profile as dbnav} from 'db-vendo-client/p/dbnav/index.js';
import {normaliseer} from '../src/zoek.js';
import {parseNsPrijs} from '../src/bronnen/ns.js';
import {maakTest, reisDelftKoeln, rit, AMSTERDAM, DELFT, LUX, ETTELBRUCK} from './helpers.js';

test('Delft → Keulen: DB- en NS International-prijs bij dezelfde trein, goedkoopste gekozen', async () => {
	const {zoeker, log} = maakTest({
		reizen: [reisDelftKoeln('2026-12-11T16:20', '2026-12-11T19:40', 79.98), reisDelftKoeln('2026-12-11T17:20', '2026-12-11T20:40', 99.98)],
		nsi: [['2026-12-11T16:20', '2026-12-11T19:40', 69.98, 109.98], ['2026-12-11T17:20', '2026-12-11T20:40', 109.98, 149.98]],
	});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Keulen', vertrek: '2026-12-11T16:00', personen: 2, leeftijden: [], studentenov: []});

	assert.equal(r.reizen.length, 2);
	const [a, b] = r.reizen;
	assert.deepEqual(a.landen, ['NL', 'DE']);
	assert.equal(a.duur_min, 200);
	assert.equal(a.overstappen, 1);
	assert.deepEqual(a.prijzen.map((p) => [p.bron, p.totaal_eur]), [['bahn.de', 79.98], ['NS International', 69.98]]);
	assert.deepEqual(a.goedkoopst, {bron: 'NS International', totaal_eur: 69.98, per_persoon_eur: 34.99});
	assert.equal(a.prijzen[1].tarief, 'Second Class');
	assert.equal(a.prijzen[1].flexibel, 'nee');
	assert.equal(b.goedkoopst.bron, 'bahn.de');
	assert.equal(r.bronnen['NS International'], 'ok');
	// De NS International-zoekvraag gebruikt de lokale vertrektijd en de stationscodes
	assert.deepEqual(log.nsi[0], {van: 'NLDET', naar: 'DEKOH', tijd: '2026-12-11T16:20:00', personen: 2});
	assert.match(r.links.ns_international, /search\/NLDET\/DEKOH\/20261211\?pax=A,A$/);
	assert.match(a.prijzen[0].boeken, /^https:\/\/int\.bahn\.de\/nl\/buchung\/fahrplan\/suche#.*so=Delft.*hd=2026-12-11T16%3A20%3A00/);
	// Tijd in de DB-vraag: 16:00 Nederlandse tijd
	assert.equal(log.db[0].vertrek.toISOString(), '2026-12-11T15:00:00.000Z');
	assert.deepEqual(log.db[0].leeftijden, []);
	assert.equal(log.db[0].personen, 2);
});

test('NS International wordt een tweede keer gevraagd voor latere treinen', async () => {
	const {zoeker, log} = maakTest({
		reizen: [reisDelftKoeln('2026-12-11T16:20', '2026-12-11T19:40', 80), reisDelftKoeln('2026-12-11T18:20', '2026-12-11T21:40', 80)],
		nsi: (tijd) => (tijd.startsWith('2026-12-11T16:20')
			? [['2026-12-11T16:20', '2026-12-11T19:40', 60, 90]]
			: [['2026-12-11T18:20', '2026-12-11T21:40', 50, 90]]),
	});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Keulen', vertrek: '2026-12-11T16:00', personen: 1, leeftijden: [], studentenov: []});
	assert.equal(log.nsi.length, 2);
	assert.equal(log.nsi[1].tijd, '2026-12-11T18:20:00');
	assert.deepEqual(r.reizen.map((x) => x.goedkoopst.totaal_eur), [60, 50]);
});

test('NS International geblokkeerd: DB-prijs blijft, status zegt waarom', async () => {
	const {zoeker} = maakTest({reizen: [reisDelftKoeln('2026-12-11T16:20', '2026-12-11T19:40', 79.98)], nsiFout: true});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Keulen', vertrek: '2026-12-11T16:00', personen: 2, leeftijden: [], studentenov: []});
	assert.match(r.bronnen['NS International'], /^geblokkeerd/);
	assert.equal(r.reizen[0].goedkoopst.bron, 'bahn.de');
	assert.ok(r.links.ns_international, 'de zoeklink blijft er');
});

test('deelprijs van DB telt niet als goedkoopste', async () => {
	const {zoeker} = maakTest({reizen: [reisDelftKoeln('2026-12-11T16:20', '2026-12-11T19:40', 20, {partialFare: true})], nsi: []});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Keulen', vertrek: '2026-12-11T16:00', personen: 1, leeftijden: [], studentenov: []});
	assert.equal(r.reizen[0].prijzen[0].deelprijs, true);
	assert.equal(r.reizen[0].goedkoopst, null);
});

const binnenland = (vertrek) => [{type: 'journey', legs: [rit(DELFT, AMSTERDAM, `${vertrek}:00+01:00`, '2026-12-11T17:05:00+01:00', 'IC 2100', 'NS')]}];

test('binnenland met NS-prijs en studentenreisproduct (vrijdagmiddag: weekend gratis)', async () => {
	const {zoeker, log} = maakTest({reizen: binnenland('2026-12-11T16:10'), nsPrijs: {bedrag: 28.4, perPersoon: 14.2, product: 'Enkele reis'}});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Amsterdam', vertrek: '2026-12-11T16:00', personen: 2, leeftijden: [], studentenov: ['weekend', 'week']});
	const j = r.reizen[0];
	assert.deepEqual(j.landen, ['NL']);
	assert.equal(log.nsi.length, 0, 'geen NS International voor binnenland');
	assert.deepEqual(j.prijzen.map((p) => [p.bron, p.totaal_eur]), [['NS', 28.4], ['NS + studentenreisproduct', 0]]);
	assert.equal(j.prijzen[1].toelichting, 'reiziger 1: gratis, reiziger 2: gratis');
	assert.equal(j.goedkoopst.totaal_eur, 0);
	assert.equal(log.ns[0].van, '8400170');
	assert.equal(r.bronnen.NS, 'ok');
});

test('binnenland op zaterdag: weekabonnement krijgt 40% korting', async () => {
	const {zoeker} = maakTest({reizen: binnenland('2026-12-12T10:10'), nsPrijs: {bedrag: 28.4, perPersoon: 14.2, product: 'Enkele reis'}});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Amsterdam', vertrek: '2026-12-12T10:00', personen: 2, leeftijden: [], studentenov: ['weekend', 'week']});
	assert.equal(r.reizen[0].prijzen[1].totaal_eur, 8.52); // 0 + 14.20 × 0,6
});

test('binnenland zonder NS-sleutel: duidelijke status en reisplannerlink', async () => {
	const {zoeker} = maakTest({reizen: binnenland('2026-12-11T16:10')});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Amsterdam', vertrek: '2026-12-11T16:00', personen: 1, leeftijden: [], studentenov: []});
	assert.match(r.bronnen.NS, /NS_API_KEY/);
	assert.match(r.links.ns, /^https:\/\/www\.ns\.nl\/reisplanner\/#\/\?vertrek=Delft&aankomst=Amsterdam/);
});

test('Luxemburg binnenland is gratis', async () => {
	const {zoeker} = maakTest({reizen: [{type: 'journey', legs: [rit(LUX, ETTELBRUCK, '2026-12-12T10:00:00+01:00', '2026-12-12T10:30:00+01:00', 'RE 3809', 'CFL')]}]});
	const r = await zoeker.reizen({van: 'Luxemburg', naar: 'Ettelbruck', vertrek: '2026-12-12T09:00', personen: 2, leeftijden: [], studentenov: []});
	assert.equal(r.reizen[0].goedkoopst.totaal_eur, 0);
});

test('onbekend station geeft een invoerfout', async () => {
	const {zoeker} = maakTest();
	await assert.rejects(zoeker.reizen({van: 'Nergenshuizen', naar: 'Keulen', leeftijden: [], studentenov: []}), {name: 'Error', message: /niet gevonden/});
});

test('leeftijden uit de instellingen gaan mee naar DB', async () => {
	const {zoeker, log} = maakTest({reizen: [], config: {leeftijden: [22, 23]}});
	const r = await zoeker.reizen({van: 'Delft', naar: 'Keulen', vertrek: '2026-12-11T16:00', leeftijden: [], studentenov: []});
	assert.deepEqual(log.db[0].leeftijden, [22, 23]);
	assert.equal(r.reizigers.personen, 2);
});

test('goedkoopste dag over een periode', async () => {
	const prijzen = {'2026-12-11': 59.98, '2026-12-12': 39.98, '2026-12-13': 49.98};
	const {zoeker} = maakTest({
		dagreizen: (datum) => [reisDelftKoeln('2026-12-11T16:20', '2026-12-11T19:40', prijzen[DateTime.fromJSDate(datum).setZone('Europe/Amsterdam').toISODate()])],
	});
	const r = await zoeker.goedkoopsteDag({van: 'Delft', naar: 'Keulen', van_datum: '2026-12-11', tot_datum: '2026-12-13', personen: 2, leeftijden: [], studentenov: []});
	assert.deepEqual(r.dagen.map((d) => [d.datum, d.goedkoopst.totaal_eur]), [['2026-12-11', 59.98], ['2026-12-12', 39.98], ['2026-12-13', 49.98]]);
	await assert.rejects(zoeker.goedkoopsteDag({van: 'Delft', naar: 'Keulen', van_datum: '2026-12-01', tot_datum: '2026-12-31'}), /14 dagen/);
});

test('echte DB Navigator-reis (fixture van db-vendo-client) wordt goed omgezet', () => {
	const raw = JSON.parse(readFileSync(new URL('./fixtures/dbnav-reis.json', import.meta.url)));
	// Zo staat de prijs in een "fahrplan"-antwoord (voor alle reizigers samen)
	raw.angebote.preise = {gesamt: {ab: {betrag: 59.98, waehrung: 'EUR'}}, istTeilpreis: false};
	const client = createClient(dbnav, 'test', {enrichStations: false});
	const journey = client.profile.parseJourney({profile: client.profile, opt: {remarks: false, stopovers: false}, common: null, res: raw}, raw);
	const r = normaliseer(journey, 2, 2);
	assert.equal(r.van, 'Frankfurt(Main)Hbf');
	assert.ok(r.ritten.length >= 1);
	assert.deepEqual(r.landen, ['DE']);
	assert.equal(r.prijzen[0].totaal_eur, 59.98);
	assert.equal(r.prijzen[0].per_persoon_eur, 29.99);
	assert.ok(r.duur_min > 0);
});

test('NS-API prijsantwoord', () => {
	const p = parseNsPrijs({payload: {prices: [
		{travelClass: 'FIRST_CLASS', discountType: 'NONE', totalPriceInCents: 4000, pricePerAdultInCents: 2000},
		{travelClass: 'SECOND_CLASS', discountType: 'DISCOUNT_40_PERCENT', totalPriceInCents: 1500, pricePerAdultInCents: 750},
		{travelClass: 'SECOND_CLASS', discountType: 'NONE', totalPriceInCents: 2840, pricePerAdultInCents: 1420, displayName: 'Enkele reis'},
	]}});
	assert.deepEqual(p, {bedrag: 28.4, perPersoon: 14.2, product: 'Enkele reis'});
});
