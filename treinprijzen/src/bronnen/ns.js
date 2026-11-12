// NS binnenland via de officiële NS-API (gratis sleutel op https://apiportal.ns.nl).
// Prijzen in Nederland hangen af van de afstand, niet van de trein: één vraag per stationspaar.
import {Rem} from '../cache.js';

export const NAAM = 'NS';
const BASIS = 'https://gateway.apiportal.ns.nl/reisinformatie-api/api/v3';

export const reisplannerLink = (van, naar, tijd) =>
	'https://www.ns.nl/reisplanner/#/?' + new URLSearchParams({vertrek: van, aankomst: naar, type: 'vertrek', tijd: tijd.slice(0, 16)});

export const maakNs = ({apiKey, fetchFn = fetch} = {}) => {
	const rem = new Rem(300);
	return {
		actief: Boolean(apiKey),
		/**
		 * @returns {{bedrag: number, perPersoon: number, product: string}|null} enkele reis, hele groep
		 */
		async prijs(vanUic, naarUic, {personen = 1, klasse = 2, vertrek} = {}) {
			if (!apiKey) {
				return null;
			}
			await rem.wacht();
			const q = new URLSearchParams({
				fromStation: vanUic, toStation: naarUic,
				travelClass: klasse === 1 ? 'FIRST_CLASS' : 'SECOND_CLASS',
				travelType: 'single', adults: String(personen), children: '0',
			});
			if (vertrek) {
				q.set('plannedDepartureTime', vertrek);
			}
			const res = await fetchFn(`${BASIS}/price?${q}`, {
				headers: {'Ocp-Apim-Subscription-Key': apiKey, 'Accept': 'application/json'},
				signal: AbortSignal.timeout(20_000),
			});
			if (!res.ok) {
				throw new Error(`NS-API gaf HTTP ${res.status}`);
			}
			return parseNsPrijs(await res.json(), klasse);
		},
	};
};

export const parseNsPrijs = (data, klasse = 2) => {
	const prijzen = (data?.payload?.prices || data?.prices || [])
		.filter((p) => p.travelClass === (klasse === 1 ? 'FIRST_CLASS' : 'SECOND_CLASS'))
		.filter((p) => !p.discountType || p.discountType === 'NONE' || p.discountType === 'NO_DISCOUNT');
	if (!prijzen.length) {
		return null;
	}
	const p = prijzen.find((x) => x.isBestOption) || prijzen.reduce((a, b) => (a.totalPriceInCents <= b.totalPriceInCents ? a : b));
	return {
		bedrag: p.totalPriceInCents / 100,
		perPersoon: (p.pricePerAdultInCents ?? p.totalPriceInCents) / 100,
		product: p.displayName || 'Enkele reis',
	};
};
