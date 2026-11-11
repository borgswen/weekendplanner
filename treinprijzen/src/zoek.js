// Eerst de dienstregeling (DB), dan per verbinding de prijzen bij de verkopers die die reis verkopen.
import {DateTime} from 'luxon';
import {land, nsiCode} from './stations.js';
import {tarief, KORTING} from './studentenov.js';
import {NAAM as DB} from './bronnen/db.js';
import {NAAM as NSI, zoekLink as nsiLink, GeblokkeerdError} from './bronnen/nsi.js';
import {NAAM as NS, reisplannerLink} from './bronnen/ns.js';
import {NAAM as OEBB, zoekLink as oebbLink} from './bronnen/oebb.js';
import {nmbsPrijs, afstandKm} from './nmbs.js';

const ZONE = 'Europe/Amsterdam'; // NL, BE, LU en DE hebben dezelfde klok
const r2 = (x) => Math.round(x * 100) / 100;

export const lokaal = (iso) => (iso ? DateTime.fromISO(iso, {setZone: true}).setZone(ZONE).toFormat("yyyy-MM-dd'T'HH:mm") : null);
export const naarDatum = (tekst) => {
	const dt = tekst ? DateTime.fromISO(tekst, {zone: ZONE}) : DateTime.now().setZone(ZONE);
	if (!dt.isValid) {
		throw new InvoerFout(`Ongeldige tijd: ${tekst} (gebruik bijv. 2026-12-11T16:00)`);
	}
	return dt;
};

export class InvoerFout extends Error {}

export const bahnLink = (van, naar, tijd, personen = 1, klasse = 2) => 'https://int.bahn.de/nl/buchung/fahrplan/suche#' + new URLSearchParams({
	sts: 'true', so: van, zo: naar, kl: String(klasse), hd: `${tijd.slice(0, 16)}:00`, r: `13:16:KLASSENLOS:${personen}`,
}).toString();

const korteMelding = (e) => (e instanceof GeblokkeerdError ? `geblokkeerd: ${e.message}` : `fout: ${e.message}`);

// --- normaliseren ----------------------------------------------------------------

export const normaliseer = (j, personen, klasse) => {
	const ritten = j.legs.filter((l) => !l.walking).map((l) => ({
		trein: l.line?.name || l.line?.productName || '?',
		vervoerder: l.line?.operator?.name || null,
		van: l.origin?.name, van_id: String(l.origin?.id || ''),
		vertrek: l.plannedDeparture || l.departure,
		naar: l.destination?.name, naar_id: String(l.destination?.id || ''),
		aankomst: l.plannedArrival || l.arrival,
		...(l.cancelled ? {uitgevallen: true} : {}),
	}));
	if (!ritten.length) {
		return null;
	}
	const eerste = ritten[0], laatste = ritten[ritten.length - 1];
	const landen = [...new Set(ritten.flatMap((r) => [land(r.van_id), land(r.naar_id)]).filter(Boolean))];
	const reis = {
		vertrek: eerste.vertrek,
		aankomst: laatste.aankomst,
		duur_min: Math.round((Date.parse(laatste.aankomst) - Date.parse(eerste.vertrek)) / 60000),
		overstappen: ritten.length - 1,
		van: eerste.van, van_id: eerste.van_id,
		naar: laatste.naar, naar_id: laatste.naar_id,
		landen,
		ritten,
		km: afstandKm(j.legs),
		prijzen: [],
		goedkoopst: null,
	};
	if (ritten.some((r) => r.uitgevallen)) {
		reis.uitgevallen = true;
	}
	if (j.price?.amount) {
		reis.prijzen.push({
			bron: DB,
			totaal_eur: r2(j.price.amount),
			per_persoon_eur: r2(j.price.amount / personen),
			klasse,
			// Deelprijs: DB verkoopt maar een deel van de reis, de rest moet je los kopen.
			deelprijs: Boolean(j.price.partialFare),
			boeken: bahnLink(reis.van, reis.naar, lokaal(reis.vertrek), personen, klasse),
		});
	}
	return reis;
};

const kiesGoedkoopst = (reis) => {
	const heel = reis.prijzen.filter((p) => !p.deelprijs && typeof p.totaal_eur === 'number');
	if (!heel.length) {
		return null;
	}
	const p = heel.reduce((a, b) => (a.totaal_eur <= b.totaal_eur ? a : b));
	return {bron: p.bron, totaal_eur: p.totaal_eur, per_persoon_eur: p.per_persoon_eur, ...(p.schatting ? {schatting: true} : {})};
};

// --- de zoekmachine ----------------------------------------------------------------

export const maakZoeker = ({db: dbBron, nsi, ns, oebb, cache, config}) => {
	const minuten = config.cacheMinuten;
	const aan = (b) => config.bronnen.has(b);

	const vindStation = async (tekst) => {
		if (/^\d{7}$/.test(tekst)) {
			return {id: tekst, naam: tekst};
		}
		const res = await cache.haal(`loc:${tekst.toLowerCase()}`, 24 * 60, () => dbBron.locaties(tekst, 3)).catch((e) => {
			e.message = `stations zoeken bij bahn.de lukt niet: ${e.message}`;
			throw e;
		});
		if (!res.length) {
			throw new InvoerFout(`Station of plaats niet gevonden: ${tekst}`);
		}
		return res[0];
	};

	const reizigers = (q) => {
		let leeftijden = q.leeftijden?.length ? q.leeftijden : config.leeftijden;
		const personen = q.personen || leeftijden.length || 1;
		if (leeftijden.length && leeftijden.length !== personen) {
			leeftijden = Array.from({length: personen}, (_, i) => leeftijden[i] ?? 30);
		}
		const ov = q.studentenov?.length ? q.studentenov : config.studentenOv;
		return {personen, leeftijden, studentenov: Array.from({length: personen}, (_, i) => ov[i] || 'geen')};
	};

	// Zoek bij een verkoper die zijn eigen dienstregeling heeft en koppel op vertrek- en aankomsttijd.
	// Vraagt een tweede keer als er latere treinen nog geen prijs hebben.
	const koppelOpTijd = async (kandidaten, zoek) => {
		const gevonden = new Map();
		let vanaf = lokaal(kandidaten[0].vertrek);
		for (let poging = 0; poging < 2; poging++) {
			const lijst = await zoek(vanaf);
			for (const v of lijst) {
				gevonden.set(`${v.vertrek}|${v.aankomst}`, v);
			}
			const open = kandidaten.filter((r) => !gevonden.has(`${lokaal(r.vertrek)}|${lokaal(r.aankomst)}`));
			const laatste = lijst.map((v) => v.vertrek).filter(Boolean).sort().at(-1);
			const volgende = open.map((r) => lokaal(r.vertrek)).find((t) => laatste && t > laatste);
			if (!volgende) {
				break;
			}
			vanaf = volgende;
		}
		return (r) => gevonden.get(`${lokaal(r.vertrek)}|${lokaal(r.aankomst)}`);
	};

	// NS International: internationale reizen vanuit/naar NL of BE.
	const nsiPrijzen = async (reizen, {personen, klasse, status, links}) => {
		const kandidaten = reizen.filter((r) => r.landen.length > 1 && r.landen.some((l) => l === 'NL' || l === 'BE'));
		if (!kandidaten.length) {
			return;
		}
		const vanCode = nsiCode(kandidaten[0].van_id), naarCode = nsiCode(kandidaten[0].naar_id);
		if (!vanCode || !naarCode) {
			status[NSI] = 'geen NS International-code voor dit station';
			return;
		}
		links.ns_international = nsiLink(vanCode, naarCode, lokaal(kandidaten[0].vertrek), personen);
		let vind;
		try {
			vind = await koppelOpTijd(kandidaten, (tijd) => cache.haal(`nsi:${vanCode}:${naarCode}:${tijd}:${personen}`, minuten,
				() => nsi.zoek(vanCode, naarCode, `${tijd}:00`, {personen})));
			status[NSI] = 'ok';
		} catch (e) {
			status[NSI] = korteMelding(e);
			return;
		}
		for (const r of kandidaten) {
			const v = vind(r);
			const p = v?.prijs?.[String(klasse)];
			if (!p || !v.boekbaar) { // een tarief zonder boekbare reis telt niet
				continue;
			}
			r.prijzen.push({
				bron: NSI,
				totaal_eur: r2(p.bedrag),
				per_persoon_eur: r2(p.bedrag / personen),
				klasse,
				tarief: p.tarief,
				flexibel: p.flex === 'FULL_FLEXIBLE' ? 'ja' : p.flex === 'SEMI_FLEXIBLE' ? 'deels' : 'nee',
				deelprijs: false,
				boeken: nsiLink(v.van, v.naar, lokaal(r.vertrek), personen),
			});
		}
	};

	// ÖBB: reizen van, naar of door Oostenrijk, en nachttreinen naar Zwitserland.
	const oebbPrijzen = async (reizen, {personen, klasse, status, links}) => {
		if (!oebb || klasse !== 2) {
			return;
		}
		const kandidaten = reizen.filter((r) => r.landen.includes('AT') || (r.landen.includes('CH') && r.landen.length > 1));
		if (!kandidaten.length) {
			return;
		}
		const {van_id: van, naar_id: naar, van: vanNaam, naar: naarNaam} = kandidaten[0];
		links.oebb = oebbLink();
		let vind;
		try {
			vind = await koppelOpTijd(kandidaten, (tijd) => cache.haal(`oebb:${van}:${naar}:${tijd}`, minuten,
				() => oebb.zoek(van, naar, tijd, {vanNaam, naarNaam})));
			status[OEBB] = 'ok';
		} catch (e) {
			status[OEBB] = korteMelding(e);
			return;
		}
		for (const r of kandidaten) {
			const v = vind(r);
			if (typeof v?.perPersoon !== 'number') {
				continue;
			}
			r.prijzen.push({
				bron: OEBB,
				totaal_eur: r2(v.perPersoon * personen),
				per_persoon_eur: r2(v.perPersoon),
				klasse,
				tarief: 'laagste prijs (vaak Sparschiene, per persoon × aantal)',
				deelprijs: false,
				boeken: oebbLink(),
			});
		}
	};

	// België binnenland: NMBS rekent per kilometer. Zonder officiële bron is dit een schatting.
	const belgieSchatting = (reizen, {personen, klasse, leeftijden, status, links}) => {
		const be = reizen.filter((r) => r.landen.length === 1 && r.landen[0] === 'BE');
		if (!be.length) {
			return;
		}
		links.nmbs = 'https://www.belgiantrain.be/nl';
		status.NMBS = 'schatting op basis van de kilometertarieven; controleer op belgiantrain.be';
		for (const r of be) {
			const km = r.km;
			if (!km) {
				continue;
			}
			const per = Array.from({length: personen}, (_, i) => nmbsPrijs(km, {leeftijd: leeftijden[i], klasse, moment: r.vertrek}));
			const totaal = per.reduce((a, b) => a + b, 0);
			r.prijzen.push({bron: 'NMBS (schatting)', totaal_eur: r2(totaal), per_persoon_eur: r2(totaal / personen), klasse,
				deelprijs: false, schatting: true, toelichting: `ca. ${Math.round(km)} km`, boeken: links.nmbs});
		}
	};

	// Zwitserland en Frankrijk binnenland: (nog) geen bron die een server mag/kan bevragen.
	const zonderBron = (reizen, {status, links}) => {
		if (reizen.some((r) => r.landen.length === 1 && r.landen[0] === 'CH')) {
			links.sbb = 'https://www.sbb.ch/nl';
			status.SBB = 'geen prijzen voor reizen binnen Zwitserland; zie de link (tip: Supersaver-tickets)';
		}
		if (reizen.some((r) => r.landen.length === 1 && r.landen[0] === 'FR')) {
			links.sncf = 'https://www.sncf-connect.com';
			status['SNCF Connect'] = 'geen prijzen voor reizen binnen Frankrijk; zie de link';
		}
	};

	// NS binnenland (+ studentenreisproduct) en Luxemburg (gratis OV).
	const binnenlandPrijzen = async (reizen, {personen, klasse, studentenov, status, links}) => {
		for (const r of reizen) {
			if (r.landen.length === 1 && r.landen[0] === 'LU' && klasse === 2) {
				r.prijzen.push({bron: 'Luxemburg', totaal_eur: 0, per_persoon_eur: 0, klasse, deelprijs: false,
					toelichting: 'Openbaar vervoer in Luxemburg is gratis (2e klas)'});
			}
		}
		const nl = reizen.filter((r) => r.landen.length === 1 && r.landen[0] === 'NL');
		if (!nl.length) {
			return;
		}
		links.ns = reisplannerLink(nl[0].van, nl[0].naar, lokaal(nl[0].vertrek));
		if (!ns.actief) {
			status[NS] = 'geen NS_API_KEY ingesteld (gratis aan te vragen op apiportal.ns.nl)';
			return;
		}
		try {
			for (const r of nl) {
				const p = await cache.haal(`ns:${r.van_id}:${r.naar_id}:${personen}:${klasse}`, 12 * 60,
					() => ns.prijs(r.van_id, r.naar_id, {personen, klasse, vertrek: r.vertrek}));
				if (!p) {
					continue;
				}
				r.prijzen.push({bron: NS, totaal_eur: r2(p.bedrag), per_persoon_eur: r2(p.perPersoon), klasse,
					tarief: p.product, deelprijs: false, boeken: reisplannerLink(r.van, r.naar, lokaal(r.vertrek))});
				if (klasse === 2 && studentenov.some((s) => s !== 'geen')) {
					const soorten = studentenov.map((s) => tarief(s, r.vertrek));
					const totaal = soorten.reduce((som, t) => som + (t === 'gratis' ? 0 : t === 'korting' ? p.perPersoon * (1 - KORTING) : p.perPersoon), 0);
					r.prijzen.push({bron: 'NS + studentenreisproduct', totaal_eur: r2(totaal), per_persoon_eur: r2(totaal / personen),
						klasse, deelprijs: false, toelichting: soorten.map((t, i) => `reiziger ${i + 1}: ${t}`).join(', ')});
				}
			}
			status[NS] = 'ok';
		} catch (e) {
			status[NS] = korteMelding(e);
		}
	};

	const zoeker = {
		vindStation,

		async stations(tekst) {
			const res = await cache.haal(`locs:${tekst.toLowerCase()}`, 24 * 60, () => dbBron.locaties(tekst, 6));
			return res.map((s) => ({...s, land: land(s.id), ns_international: nsiCode(s.id)}));
		},

		async reizen(q) {
			if (!q.van || !q.naar) {
				throw new InvoerFout('Geef van= en naar= mee');
			}
			const klasse = q.klasse === 1 ? 1 : 2;
			const {personen, leeftijden, studentenov} = reizigers(q);
			const [van, naar] = await Promise.all([vindStation(q.van), vindStation(q.naar)]);
			const moment = naarDatum(q.aankomst || q.vertrek);
			const status = {}, links = {};

			const sleutel = `db:${van.id}:${naar.id}:${q.aankomst ? 'a' : 'v'}${moment.toISO()}:${leeftijden.join('-') || personen}:${klasse}`;
			const dbRes = await cache.haal(sleutel, minuten, () => dbBron.reizen(van.id, naar.id, {
				[q.aankomst ? 'aankomst' : 'vertrek']: moment.toJSDate(), leeftijden, personen, klasse,
			})).catch((e) => {
				e.message = `dienstregeling van bahn.de niet bereikbaar: ${e.message}`;
				throw e;
			});
			status[DB] = 'ok';
			let reizen = dbRes.reizen.map((j) => normaliseer(j, personen, klasse)).filter(Boolean);
			if (q.aantal) {
				reizen = reizen.slice(0, q.aantal);
			}
			links.bahn_de = bahnLink(van.naam, naar.naam, moment.toFormat("yyyy-MM-dd'T'HH:mm"), personen, klasse);

			if (aan('nsi')) {
				await nsiPrijzen(reizen, {personen, klasse, status, links});
			}
			if (aan('oebb')) {
				await oebbPrijzen(reizen, {personen, klasse, status, links});
			}
			if (aan('ns')) {
				await binnenlandPrijzen(reizen, {personen, klasse, studentenov, status, links});
			}
			belgieSchatting(reizen, {personen, klasse, leeftijden, status, links});
			zonderBron(reizen, {status, links});
			for (const r of reizen) {
				r.goedkoopst = kiesGoedkoopst(r);
			}
			return {
				van: van.naam, van_id: van.id, naar: naar.naam, naar_id: naar.id,
				reizigers: {personen, leeftijden, studentenov, klasse},
				reizen, bronnen: status, links,
				let_op: 'Prijzen zijn voor alle reizigers samen, enkele reis, op het moment van opvragen. Check ze voor het boeken.',
			};
		},

		// Goedkoopste reizen van één dag volgens DB (bahn.de "Bestpreise").
		async dagprijzen(q) {
			if (!q.van || !q.naar) {
				throw new InvoerFout('Geef van= en naar= mee');
			}
			const klasse = q.klasse === 1 ? 1 : 2;
			const {personen, leeftijden} = reizigers(q);
			const [van, naar] = await Promise.all([vindStation(q.van), vindStation(q.naar)]);
			const dag = naarDatum(q.datum || q.vertrek).startOf('day');
			const ruw = await cache.haal(`best:${van.id}:${naar.id}:${dag.toISODate()}:${leeftijden.join('-') || personen}:${klasse}`, minuten,
				() => dbBron.dagprijzen(van.id, naar.id, {datum: dag.toJSDate(), leeftijden, personen, klasse}));
			const reizen = ruw.map((j) => normaliseer(j, personen, klasse)).filter((r) => r?.prijzen.length);
			for (const r of reizen) {
				r.goedkoopst = kiesGoedkoopst(r);
			}
			reizen.sort((a, b) => (a.goedkoopst?.totaal_eur ?? 1e9) - (b.goedkoopst?.totaal_eur ?? 1e9));
			return {
				van: van.naam, naar: naar.naam, datum: dag.toISODate(), reizigers: {personen, leeftijden, klasse},
				goedkoopst: reizen[0]?.goedkoopst || null,
				reizen: reizen.slice(0, q.aantal || 6),
				links: {bahn_de: bahnLink(van.naam, naar.naam, dag.toFormat("yyyy-MM-dd'T'08:00"), personen, klasse)},
				let_op: 'Alleen DB-prijzen (bahn.de). Prijzen voor alle reizigers samen, enkele reis.',
			};
		},

		// Per dag de goedkoopste prijs in een periode (max. 14 dagen), om de goedkoopste dag te kiezen.
		async goedkoopsteDag(q) {
			const begin = naarDatum(q.van_datum).startOf('day');
			const eind = naarDatum(q.tot_datum || q.van_datum).startOf('day');
			const dagen = Math.round(eind.diff(begin, 'days').days) + 1;
			if (dagen < 1 || dagen > 14) {
				throw new InvoerFout('Periode moet 1 t/m 14 dagen zijn (van_datum, tot_datum)');
			}
			const uit = [];
			for (let i = 0; i < dagen; i++) {
				const d = begin.plus({days: i}).toISODate();
				try {
					const r = await zoeker.dagprijzen({...q, datum: d, aantal: 1});
					uit.push({datum: d, goedkoopst: r.goedkoopst, reis: r.reizen[0] || null});
				} catch (e) {
					if (e instanceof InvoerFout) {
						throw e;
					}
					uit.push({datum: d, fout: e.message});
				}
			}
			return {van: q.van, naar: q.naar, dagen: uit};
		},
	};
	return zoeker;
};
