import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseOebb, maakOebb} from '../src/bronnen/oebb.js';
import {nmbsPrijs, afstandKm} from '../src/nmbs.js';
import {nsiCode, land} from '../src/stations.js';
import {maakTest, rit, AMSTERDAM, SALZBURG, WIEN, BRUSSEL, BRUGGE, ZUERICH, BERN} from './helpers.js';

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

test('NMBS-schatting: grenzen, jongeren, weekend en 1e klas', () => {
	assert.equal(nmbsPrijs(1), 2.6);
	assert.equal(nmbsPrijs(200), 20.9);
	assert.equal(nmbsPrijs(200, {leeftijd: 23}), 12.5); // 40% korting
	assert.equal(nmbsPrijs(200, {moment: '2026-12-12T10:00:00+01:00'}), 14.6); // zaterdag: 30% korting
	assert.equal(nmbsPrijs(200, {klasse: 1}), 33.5);
	const km = afstandKm([rit(BRUSSEL, BRUGGE, 'a', 'b', 'IC')]);
	assert.ok(km > 100 && km < 120, `Brussel–Brugge ca. 110 spoor-km, kreeg ${km}`);
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

test('Zwitserland binnenland: geen prijs maar wel status en link', async () => {
	const {zoeker} = maakTest({reizen: [{type: 'journey', legs: [rit(ZUERICH, BERN, '2026-12-12T10:02:00+01:00', '2026-12-12T10:58:00+01:00', 'IC 8', 'SBB')]}]});
	const r = await zoeker.reizen({van: 'Zürich', naar: 'Bern', vertrek: '2026-12-12T10:00', personen: 2, leeftijden: [], studentenov: []});
	assert.equal(r.reizen[0].goedkoopst, null);
	assert.match(r.bronnen.SBB, /Zwitserland/);
	assert.ok(r.links.sbb);
});
