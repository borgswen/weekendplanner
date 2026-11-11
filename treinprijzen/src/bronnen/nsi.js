// NS International (nsinternational.com): internationale tickets vanuit NL en BE, ook naar Duitsland.
// Zelfde zoekvraag als de website stelt. Werkt dat niet (bijv. geblokkeerd), dan blijft de link over.
import {Rem} from '../cache.js';

export const NAAM = 'NS International';
const BASIS = 'https://www.nsinternational.com';

export const zoekLink = (vanCode, naarCode, datum, personen) =>
	`${BASIS}/en/traintickets-v3/#/search/${vanCode}/${naarCode}/${datum.replaceAll('-', '').slice(0, 8)}?pax=${Array(personen || 1).fill('A').join(',')}`;

export class GeblokkeerdError extends Error {}

export const maakNsi = ({userAgent, fetchFn = fetch} = {}) => {
	const rem = new Rem(2500);
	return {
		/**
		 * @param {string} vanCode Benerail-code, bijv. NLDET
		 * @param {string} naarCode bijv. DEKOH
		 * @param {string} lokaleTijd "2026-12-11T16:00:00" (lokale tijd, zonder offset)
		 * @returns lijst verbindingen met hun goedkoopste prijs per klasse
		 */
		async zoek(vanCode, naarCode, lokaleTijd, {personen = 1, aankomst = false} = {}) {
			await rem.wacht();
			const res = await fetchFn(`${BASIS}/api/v2/sales/traveloffers/search?returnAdmissionPricing=true&filterOnCheapestOffer=false`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Accept': 'application/json',
					'Accept-Language': 'nl-NL,nl;q=0.9,en;q=0.8',
					'Origin': BASIS,
					'Referer': `${BASIS}/en/traintickets-v3/`,
					'User-Agent': userAgent,
				},
				body: JSON.stringify({
					origin: vanCode,
					destination: naarCode,
					travelers: Array(personen).fill({ageType: 'A'}),
					outboundDatetime: {datetime: lokaleTijd.slice(0, 19).padEnd(19, ':00'), timetype: aankomst ? 'ARRIVAL' : 'DEPARTURE'},
				}),
				signal: AbortSignal.timeout(30_000),
			});
			if (res.status === 403 || res.status === 429) {
				throw new GeblokkeerdError(`NS International weigert het verzoek (HTTP ${res.status})`);
			}
			if (!res.ok) {
				throw new Error(`NS International gaf HTTP ${res.status}`);
			}
			const data = await res.json();
			return parseNsi(data);
		},
	};
};

export const parseNsi = (data) => {
	const aanbod = data?.data?.travelOffers;
	if (!Array.isArray(aanbod)) {
		throw new Error('NS International: onverwacht antwoord (geen travelOffers)');
	}
	return aanbod.map((o) => {
		const it = o.itinerary || {};
		const goedkoopst = {};
		for (const offer of o.offers || []) {
			const k = String(offer.classLevel || '2');
			const bedrag = offer.totalPrice?.amount;
			if (typeof bedrag !== 'number') {
				continue;
			}
			if (!goedkoopst[k] || bedrag < goedkoopst[k].bedrag) {
				goedkoopst[k] = {bedrag, tarief: (offer.name || '').trim(), flex: offer.flexLevel || null, beschikbaar: offer.availability || null};
			}
		}
		return {
			vertrek: it.origin?.departure?.plannedLocalDateTime?.slice(0, 16) || null,
			aankomst: it.destination?.arrival?.plannedLocalDateTime?.slice(0, 16) || null,
			van: it.origin?.code, naar: it.destination?.code,
			treinen: (it.modalities || []).filter((m) => m.type === 'TRAIN').map((m) => `${m.code || m.name || ''} ${m.number || ''}`.trim()),
			boekbaar: o.bookableStatus === 'BOOKABLE',
			prijs: goedkoopst, // {"1": {...}, "2": {...}}, bedrag voor de hele groep
		};
	});
};
