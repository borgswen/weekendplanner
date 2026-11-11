import {test} from 'node:test';
import assert from 'node:assert/strict';
import {tarief, feestdagen} from '../src/studentenov.js';

test('feestdagen 2027: Pasen 28 maart, Koningsdag dinsdag 27 april', () => {
	const f = feestdagen(2027);
	assert.equal(f.goedeVrijdag, '2027-03-26');
	assert.ok(f.alle.has('2027-03-29')); // 2e paasdag
	assert.ok(f.alle.has('2027-05-06')); // Hemelvaart
	assert.ok(f.alle.has('2027-04-27'));
});

test('weekendabonnement', () => {
	const w = (t) => tarief('weekend', t);
	assert.equal(w('2026-12-11T16:00'), 'gratis'); // vrijdagmiddag
	assert.equal(w('2026-12-11T10:00'), 'korting'); // vrijdagochtend
	assert.equal(w('2026-12-08T08:00'), 'vol'); // dinsdag in de spits
	assert.equal(w('2026-12-08T10:00'), 'korting');
	assert.equal(w('2026-12-13T23:00'), 'gratis'); // zondagavond
	assert.equal(w('2026-12-14T03:30'), 'gratis'); // nacht naar maandag
	assert.equal(w('2026-12-14T05:00'), 'korting'); // maandag
	assert.equal(w('2026-12-25T08:00'), 'gratis'); // 1e kerstdag
	assert.equal(w('2027-04-26T13:00'), 'gratis'); // middag voor Koningsdag
	assert.equal(w('2027-04-26T11:00'), 'korting');
});

test('weekabonnement', () => {
	const w = (t) => tarief('week', t);
	assert.equal(w('2026-12-09T10:00'), 'gratis'); // woensdag
	assert.equal(w('2026-12-12T03:00'), 'gratis'); // nacht naar zaterdag
	assert.equal(w('2026-12-12T10:00'), 'korting'); // zaterdag
	assert.equal(w('2027-07-20T10:00'), 'korting'); // zomerperiode
	assert.equal(w('2026-12-25T10:00'), 'korting'); // kerst
	assert.equal(w('2027-03-26T10:00'), 'gratis'); // Goede Vrijdag
});

test('geen abonnement', () => {
	assert.equal(tarief('geen', '2026-12-11T16:00'), 'vol');
});
