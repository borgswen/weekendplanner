// ÖBB (shop.oebbtickets.at): Oostenrijk, Nightjets en reizen via Oostenrijk naar Zwitserland/Italië.
// Zelfde stappen als de webshop: anonieme sessie → travelAction → dienstregeling → "vanaf"-prijzen.
// ÖBB gebruikt dezelfde stationsnummers (EVA) als DB.
import {Rem} from '../cache.js';
import {GeblokkeerdError} from './nsi.js';

export const NAAM = 'ÖBB';

export const zoekLink = () => 'https://shop.oebbtickets.at/nl/ticket';

export const maakOebb = ({userAgent, basis = 'https://shop.oebbtickets.at', fetchFn = fetch} = {}) => {
	const rem = new Rem(1500);
	let sessie = null; // {accessToken, sessionId, tot}

	const verzoek = async (pad, {method = 'GET', body, query, auth = true} = {}) => {
		await rem.wacht();
		const url = new URL(basis + pad);
		for (const [k, v] of Object.entries(query || {})) {
			for (const w of [].concat(v)) {
				url.searchParams.append(Array.isArray(v) ? `${k}[]` : k, w);
			}
		}
		const headers = {'Accept': 'application/json', 'User-Agent': userAgent, 'Channel': 'inet', 'Lang': 'de'};
		if (auth && sessie) {
			headers.AccessToken = sessie.accessToken;
			headers.SessionId = sessie.sessionId;
		}
		if (body) {
			headers['Content-Type'] = 'application/json';
		}
		const res = await fetchFn(url, {method, headers, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(30_000)});
		const type = res.headers.get('content-type') || '';
		if (res.status === 403 || res.status === 429 || (res.ok && !type.includes('json'))) {
			throw new GeblokkeerdError(`ÖBB weigert het verzoek (HTTP ${res.status}${type.includes('html') ? ', botcontrole' : ''})`);
		}
		if (!res.ok) {
			throw new Error(`ÖBB gaf HTTP ${res.status} op ${pad}`);
		}
		return res.json();
	};

	const login = async () => {
		if (sessie && sessie.tot > Date.now()) {
			return;
		}
		let laatsteFout;
		// De webshop gebruikt anonymousToken; oudere versies van de app gebruiken init.
		for (const pad of ['/api/domain/v1/anonymousToken', '/api/domain/v4/init']) {
			try {
				const t = await verzoek(pad, {auth: false});
				if (t?.accessToken) {
					sessie = {accessToken: t.accessToken, sessionId: t.sessionId || t.accessToken, tot: Date.now() + 20 * 60_000};
					return;
				}
			} catch (e) {
				laatsteFout = e;
				if (e instanceof GeblokkeerdError) {
					throw e;
				}
			}
		}
		throw laatsteFout || new Error('ÖBB: geen sessie gekregen');
	};

	return {
		/**
		 * @param {string} vanEva  bijv. 8400058
		 * @param {string} naarEva bijv. 8103000
		 * @param {string} lokaleTijd "2026-12-11T16:00" (Midden-Europese tijd)
		 * @returns verbindingen met prijs per persoon (Sparschiene/standaard "vanaf"-prijs, 2e klas)
		 */
		async zoek(vanEva, naarEva, lokaleTijd, {vanNaam = '', naarNaam = ''} = {}) {
			await login();
			const iso = `${lokaleTijd.slice(0, 16)}:00.000`;
			const acties = await verzoek('/api/offer/v2/travelActions', {method: 'POST', body: {
				datetime: iso,
				from: {number: Number(vanEva), name: vanNaam},
				to: {number: Number(naarEva), name: naarNaam},
				customerVias: [], ignoreHistory: true, filterHistory: false, sortType: 'DEPARTURE',
			}});
			const actie = (acties.travelActions || []).find((a) => a?.entrypoint?.id === 'timetable') || acties.travelActions?.[0];
			if (!actie?.id) {
				return [];
			}
			const tt = await verzoek('/api/hafas/v4/timetable', {method: 'POST', body: {
				travelActionId: actie.id,
				datetimeDeparture: iso,
				filter: {regionaltrains: false, direct: false, wheelchair: false, bikes: false, trains: false, motorail: false, connections: []},
				passengers: [{type: 'ADULT', id: 1, me: false, remembered: false, challengedFlags: {hasHandicappedPass: false, hasAssistanceDog: false, hasWheelchair: false, hasAttendant: false}, relations: [], cards: [], birthdateChangeable: true, birthdateDeletable: true, nameChangeable: true, passengerDeletable: true, isSelected: false}],
				entryPointId: 'timetable', count: 5, debugFilter: {noAggregationFilter: false, noEqclassFilter: false, noNrtpathFilter: false, noPaymentFilter: false, useTripartFilter: false, noVbxFilter: false, noCategoriesFilter: false}, sortType: 'DEPARTURE',
			}});
			const verbindingen = tt.connections || [];
			if (!verbindingen.length) {
				return [];
			}
			const prijzen = await verzoek('/api/offer/v1/prices', {query: {connectionIds: verbindingen.map((c) => c.id), sortType: 'DEPARTURE', bestPriceId: 'undefined'}});
			return parseOebb(tt, prijzen);
		},
	};
};

export const parseOebb = (tijdschema, prijzen) => {
	const perId = new Map((prijzen?.offers || [])
		.filter((o) => typeof o.price === 'number' && !o.offerError)
		.map((o) => [o.connectionId, o]));
	return (tijdschema?.connections || []).map((c) => ({
		vertrek: c.from?.departure?.slice(0, 16) || null,
		aankomst: c.to?.arrival?.slice(0, 16) || null,
		treinen: (c.sections || []).filter((s) => s.category).map((s) => `${s.category.displayName || s.category.name || ''} ${s.category.number || ''}`.trim()),
		perPersoon: perId.get(c.id)?.price ?? null,
		eersteKlas: perId.get(c.id)?.firstClass ?? false,
	}));
};
