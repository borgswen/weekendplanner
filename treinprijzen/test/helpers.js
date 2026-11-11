// Nagebootste bronnen voor de tests.
import {Cache} from '../src/cache.js';
import {GeblokkeerdError, parseNsi} from '../src/bronnen/nsi.js';
import {parseOebb} from '../src/bronnen/oebb.js';
import {bouwIndex} from '../src/bronnen/sncf.js';
import {maakZoeker} from '../src/zoek.js';

const COORD = {
	8400170: [52.007, 4.356], 8400621: [52.089, 5.110], 8000207: [50.943, 6.959], 8400058: [52.379, 4.900],
	8200100: [49.600, 6.134], 8200510: [49.847, 6.104], 8892007: [51.036, 3.710], 8814001: [50.836, 4.336],
	8891009: [51.197, 3.217], 8103000: [48.185, 16.376], 8100002: [47.813, 13.046], 8503000: [47.378, 8.540],
	8507000: [46.949, 7.439], 8727100: [48.881, 2.355], 8768600: [48.844, 2.374], 8772319: [45.761, 4.860], 8774100: [45.188, 5.715],
};
export const station = (id, name) => ({type: 'station', id, name,
	...(COORD[id] ? {location: {type: 'location', latitude: COORD[id][0], longitude: COORD[id][1]}} : {})});

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
export const GENT = ['8892007', 'Gent-Sint-Pieters'];
export const BRUSSEL = ['8814001', 'Brussel-Zuid'];
export const BRUGGE = ['8891009', 'Brugge'];
export const WIEN = ['8103000', 'Wien Hbf'];
export const SALZBURG = ['8100002', 'Salzburg Hbf'];
export const ZUERICH = ['8503000', 'Zürich HB'];
export const BERN = ['8507000', 'Bern'];
export const PARIS_LYON = ['8768600', 'Paris Gare de Lyon'];
export const LYON = ['8772319', 'Lyon Part-Dieu'];
export const GRENOBLE = ['8774100', 'Grenoble'];

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
		travelOffers: verbindingen.map(([vertrek, aankomst, prijs2, prijs1, status = 'BOOKABLE']) => ({
			id: vertrek, bookableStatus: status,
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

export const oebbAntwoord = (verbindingen) => ({
	tijdschema: {connections: verbindingen.map(([vertrek, aankomst], i) => ({
		id: `c${i}`, from: {departure: `${vertrek}:00.000`}, to: {arrival: `${aankomst}:00.000`},
		sections: [{category: {displayName: 'NJ', number: '40421'}}],
	}))},
	prijzen: {offers: verbindingen.map(([, , prijs], i) => ({connectionId: `c${i}`, price: prijs, offerError: prijs == null, firstClass: false}))},
});

export const maakTest = ({reizen = [], dagreizen = [], nsi = [], nsiFout, nsPrijs, oebb = null, sncfRecords = null, ojpTrips = null, config = {}} = {}) => {
	const log = {db: [], nsi: [], ns: [], oebb: [], ojp: []};
	const db = {
		async locaties(tekst) {
			const bekend = {delft: DELFT, keulen: KOELN, 'köln': KOELN, amsterdam: AMSTERDAM, luxemburg: LUX, ettelbruck: ETTELBRUCK, gent: GENT, brussel: BRUSSEL, brugge: BRUGGE, wenen: WIEN, salzburg: SALZBURG, 'zürich': ZUERICH, bern: BERN, parijs: PARIS_LYON, lyon: LYON, grenoble: GRENOBLE};
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
	const oebbBron = {
		async zoek(van, naar, tijd, opt) {
			log.oebb.push({van, naar, tijd, ...opt});
			if (oebb === 'blokkade') {
				throw new GeblokkeerdError('ÖBB weigert het verzoek (HTTP 403, botcontrole)');
			}
			const {tijdschema, prijzen} = oebbAntwoord(oebb || []);
			return parseOebb(tijdschema, prijzen);
		},
	};
	const sncf = sncfRecords && {index: async () => bouwIndex(sncfRecords)};
	const ojp = ojpTrips && {
		actief: true,
		async zoek(van, naar, iso, opt) {
			log.ojp.push({van, naar, iso, ...opt});
			return ojpTrips;
		},
	};
	const zoeker = maakZoeker({
		db, nsi: nsiBron, ns, oebb: oebbBron, sncf, ojp, cache: new Cache(),
		config: {cacheMinuten: 30, bronnen: new Set(['db', 'nsi', 'ns', 'oebb', 'sncf', 'ojp']), leeftijden: [], studentenOv: [], chfNaarEur: 1.08, ...config},
	});
	return {zoeker, log};
};
