// Nagebootste bronnen voor de tests.
import {Cache} from '../src/cache.js';
import {GeblokkeerdError, parseNsi} from '../src/bronnen/nsi.js';
import {maakZoeker} from '../src/zoek.js';

export const station = (id, name) => ({type: 'station', id, name});

export const rit = (van, naar, vertrek, aankomst, name, operator) => ({
	origin: station(...van), destination: station(...naar),
	plannedDeparture: vertrek, departure: vertrek, plannedArrival: aankomst, arrival: aankomst,
	line: {name, operator: operator ? {name: operator} : undefined},
});

export const DELFT = ['8400170', 'Delft'];
export const ROTTERDAM = ['8400530', 'Rotterdam Centraal'];
export const UTRECHT = ['8400621', 'Utrecht Centraal'];
export const KOELN = ['8000207', 'Köln Hbf'];
export const AMSTERDAM = ['8400058', 'Amsterdam Centraal'];
export const LUX = ['8200100', 'Luxembourg'];
export const ETTELBRUCK = ['8200510', 'Ettelbruck'];

export const reisDelftKoeln = (vertrek, aankomst, prijs, extra = {}) => ({
	type: 'journey',
	legs: [
		rit(DELFT, UTRECHT, `${vertrek}:00+01:00`, '2026-12-11T17:00:00+01:00', 'IC 2245', 'NS'),
		{walking: true},
		rit(UTRECHT, KOELN, '2026-12-11T17:20:00+01:00', `${aankomst}:00+01:00`, 'ICE 125', 'DB Fernverkehr AG'),
	],
	price: prijs ? {amount: prijs, currency: 'EUR', partialFare: false, ...extra} : undefined,
});

export const nsiAntwoord = (verbindingen) => ({
	data: {
		travelOffers: verbindingen.map(([vertrek, aankomst, prijs2, prijs1]) => ({
			id: vertrek, bookableStatus: 'BOOKABLE',
			itinerary: {
				origin: {code: 'NLDET', departure: {plannedLocalDateTime: `${vertrek}:00`}},
				destination: {code: 'DEKOH', arrival: {plannedLocalDateTime: `${aankomst}:00`}},
				modalities: [{type: 'TRAIN', code: 'IC', number: '2245'}, {type: 'TRAIN', code: 'ICE', number: '125'}],
			},
			offers: [
				{name: 'Second Class', classLevel: '2', flexLevel: 'NON_FLEXIBLE', totalPrice: {amount: prijs2, currency: 'EUR'}},
				{name: ' Second Class Flex', classLevel: '2', flexLevel: 'FULL_FLEXIBLE', totalPrice: {amount: prijs2 + 60, currency: 'EUR'}},
				{name: 'Comfort Class', classLevel: '1', flexLevel: 'NON_FLEXIBLE', totalPrice: {amount: prijs1, currency: 'EUR'}},
			],
		})),
	},
});

export const maakTest = ({reizen = [], dagreizen = [], nsi = [], nsiFout, nsPrijs, config = {}} = {}) => {
	const log = {db: [], nsi: [], ns: []};
	const db = {
		async locaties(tekst) {
			const bekend = {delft: DELFT, keulen: KOELN, 'köln': KOELN, amsterdam: AMSTERDAM, luxemburg: LUX, ettelbruck: ETTELBRUCK};
			const s = bekend[tekst.toLowerCase()];
			return s ? [{id: s[0], naam: s[1]}] : [];
		},
		async reizen(van, naar, opt) {
			log.db.push({van, naar, ...opt});
			return {reizen: typeof reizen === 'function' ? reizen(van, naar) : reizen};
		},
		async dagprijzen(van, naar, opt) {
			log.db.push({van, naar, best: true, ...opt});
			return typeof dagreizen === 'function' ? dagreizen(opt.datum) : dagreizen;
		},
	};
	const nsiBron = {
		async zoek(van, naar, tijd, opt) {
			log.nsi.push({van, naar, tijd, ...opt});
			if (nsiFout) {
				throw new GeblokkeerdError('NS International weigert het verzoek (HTTP 403)');
			}
			const lijst = typeof nsi === 'function' ? nsi(tijd) : nsi;
			return parseNsi(nsiAntwoord(lijst));
		},
	};
	const ns = {
		actief: nsPrijs !== undefined,
		async prijs(van, naar, opt) {
			log.ns.push({van, naar, ...opt});
			return nsPrijs;
		},
	};
	const zoeker = maakZoeker({
		db, nsi: nsiBron, ns, cache: new Cache(),
		config: {cacheMinuten: 30, bronnen: new Set(['db', 'nsi', 'ns']), leeftijden: [], studentenOv: [], ...config},
	});
	return {zoeker, log};
};
