// HTTP-API: treinverbindingen met prijzen. Zie README.md voor de endpoints.
import http from 'node:http';
import {config} from './config.js';
import {Cache} from './cache.js';
import {maakDb} from './bronnen/db.js';
import {maakNsi} from './bronnen/nsi.js';
import {maakNs} from './bronnen/ns.js';
import {maakZoeker, InvoerFout} from './zoek.js';

const lijst = (s) => (s ? String(s).split(',').map((x) => x.trim()).filter(Boolean) : []);

export const leesVraag = (params) => {
	const q = Object.fromEntries(params.entries());
	return {
		van: q.van, naar: q.naar,
		vertrek: q.vertrek, aankomst: q.aankomst, datum: q.datum,
		van_datum: q.van_datum, tot_datum: q.tot_datum,
		personen: q.personen ? Math.max(1, Math.min(9, Number(q.personen) || 1)) : undefined,
		leeftijden: lijst(q.leeftijden).map(Number).filter((n) => n > 0 && n < 120),
		studentenov: lijst(q.studentenov),
		klasse: q.klasse === '1' ? 1 : 2,
		aantal: q.aantal ? Math.max(1, Math.min(20, Number(q.aantal) || 5)) : undefined,
	};
};

const UITLEG = {
	naam: 'treinprijzen',
	endpoints: {
		'/reizen?van=Delft&naar=Keulen&vertrek=2026-12-11T16:00&personen=2': 'Verbindingen met prijzen per verkoper (DB, NS International, NS). Of aankomst= in plaats van vertrek=.',
		'/dagprijzen?van=Delft&naar=Berlijn&datum=2026-12-11&personen=2': 'De goedkoopste DB-reizen van één dag.',
		'/goedkoopste-dag?van=Delft&naar=Berlijn&van_datum=2026-12-11&tot_datum=2026-12-13': 'Per dag de laagste DB-prijs (max. 14 dagen).',
		'/stations?q=Winterberg': 'Stations zoeken (id = EVA-nummer, bruikbaar als van/naar).',
		'/health': 'Draait de service?',
	},
	opties: 'personen=2, leeftijden=22,23, klasse=1|2, studentenov=weekend,week, aantal=5',
};

export const maakServer = (zoeker) => http.createServer(async (req, res) => {
	const url = new URL(req.url, 'http://localhost');
	const stuur = (code, data) => {
		res.writeHead(code, {'Content-Type': 'application/json; charset=utf-8'});
		res.end(JSON.stringify(data, null, 2));
	};
	if (req.method !== 'GET') {
		return stuur(405, {fout: 'Alleen GET'});
	}
	const q = leesVraag(url.searchParams);
	try {
		switch (url.pathname) {
		case '/':
			return stuur(200, UITLEG);
		case '/health':
			return stuur(200, {ok: true});
		case '/stations':
			if (!url.searchParams.get('q')) {
				throw new InvoerFout('Geef q= mee');
			}
			return stuur(200, await zoeker.stations(url.searchParams.get('q')));
		case '/reizen':
			return stuur(200, await zoeker.reizen(q));
		case '/dagprijzen':
			return stuur(200, await zoeker.dagprijzen(q));
		case '/goedkoopste-dag':
			return stuur(200, await zoeker.goedkoopsteDag(q));
		default:
			return stuur(404, {fout: 'Onbekend pad', ...UITLEG});
		}
	} catch (e) {
		if (e instanceof InvoerFout) {
			return stuur(400, {fout: e.message});
		}
		console.error(new Date().toISOString(), url.pathname, url.search, e);
		return stuur(502, {fout: `${e.name}: ${e.message}`});
	}
});

if (import.meta.url === `file://${process.argv[1]}`) {
	const zoeker = maakZoeker({
		db: maakDb({userAgent: config.userAgent}),
		nsi: maakNsi({userAgent: config.userAgent}),
		ns: maakNs({apiKey: config.nsApiKey}),
		cache: new Cache(),
		config,
	});
	maakServer(zoeker).listen(config.poort, () => {
		console.log(`treinprijzen luistert op :${config.poort} (bronnen: ${[...config.bronnen].join(', ')}; NS-sleutel: ${config.nsApiKey ? 'ja' : 'nee'})`);
	});
}
