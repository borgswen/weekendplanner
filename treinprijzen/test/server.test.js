import {test} from 'node:test';
import assert from 'node:assert/strict';
import {maakServer, leesVraag} from '../src/server.js';
import {maakTest, reisDelftKoeln} from './helpers.js';

const start = async (zoeker) => {
	const server = maakServer(zoeker);
	await new Promise((r) => server.listen(0, r));
	return {server, basis: `http://127.0.0.1:${server.address().port}`};
};

test('vraag lezen', () => {
	const q = leesVraag(new URLSearchParams('van=Delft&naar=Keulen&personen=2&leeftijden=22,23&klasse=1&studentenov=weekend,geen'));
	assert.deepEqual([q.personen, q.leeftijden, q.klasse, q.studentenov], [2, [22, 23], 1, ['weekend', 'geen']]);
});

test('HTTP: /reizen, invoerfout, onbekend pad', async () => {
	const {zoeker} = maakTest({reizen: [reisDelftKoeln('2026-12-11T16:20', '2026-12-11T19:40', 79.98)], nsi: []});
	const {server, basis} = await start(zoeker);
	try {
		const ok = await fetch(`${basis}/reizen?van=Delft&naar=Keulen&vertrek=2026-12-11T16:00&personen=2`);
		assert.equal(ok.status, 200);
		const data = await ok.json();
		assert.equal(data.reizen[0].goedkoopst.totaal_eur, 79.98);

		const fout = await fetch(`${basis}/reizen?van=Delft`);
		assert.equal(fout.status, 400);
		assert.match((await fout.json()).fout, /naar=/);

		const tijd = await fetch(`${basis}/reizen?van=Delft&naar=Keulen&vertrek=morgen`);
		assert.equal(tijd.status, 400);

		assert.equal((await fetch(`${basis}/bestaatniet`)).status, 404);
		assert.equal((await fetch(`${basis}/health`)).status, 200);
	} finally {
		server.close();
	}
});
