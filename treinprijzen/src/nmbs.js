// Schatting van NMBS-prijzen in België (sinds 15 oktober 2025 per kilometer).
// Tarief oktober 2025: €2,50 bij 3 km tot €20,90 vanaf 116 km; sinds 1 februari 2026 +2,14% en minimaal €2,60.
// Jongeren onder 26 en 65-plussers 40% korting (max. €12,50 in 2025), volwassenen in het weekend 30%
// (max. €14,60 in 2025), 1e klas ×1,4 / ×1,5 / ×1,6 per afstandsschijf.
// De officiële tariefkilometers kennen we niet. Met tussenstops: de afstand langs de stops × 1,05;
// zonder: hemelsbreed × 1,2. Vergeleken met echte prijzen (Turnhout → Antwerpen, Mechelen, Brussel,
// Oostende) zat de schatting 3% te laag tot 8% te hoog.
import {DateTime} from 'luxon';

const MIN_KM = 3, MAX_KM = 116;
const BASIS_MIN = 2.5, BASIS_MAX = 20.9; // tarief oktober 2025
const INDEXATIE = 1.0214; // 1 februari 2026
const MIN_PRIJS = 2.6;

const rad = (g) => (g * Math.PI) / 180;
const haversine = (a, b) => {
	const dLat = rad(b.latitude - a.latitude), dLon = rad(b.longitude - a.longitude);
	const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(dLon / 2) ** 2;
	return 2 * 6371 * Math.asin(Math.sqrt(h));
};

const plek = (s) => s?.location?.latitude ? s.location : (s?.latitude ? s : null);

// Geschatte spoorafstand van een reis (km), of null als coördinaten ontbreken.
export const afstandKm = (legs) => {
	let km = 0;
	for (const l of legs || []) {
		if (l.walking) {
			continue;
		}
		const tussen = (l.stopovers || []).map((s) => plek(s.stop)).filter(Boolean);
		const a = plek(l.origin), b = plek(l.destination);
		if (!a || !b) {
			return null;
		}
		if (tussen.length) {
			const punten = [a, ...tussen, b];
			let stuk = 0;
			for (let i = 1; i < punten.length; i++) {
				stuk += haversine(punten[i - 1], punten[i]);
			}
			km += stuk * 1.05;
		} else {
			km += haversine(a, b) * 1.2;
		}
	}
	return km || null;
};

const afronden = (p) => (p < 25 ? Math.round(p * 10) / 10 : p < 50 ? Math.round(p * 2) / 2 : Math.round(p));

export const nmbsPrijs = (km, {leeftijd, klasse = 2, moment} = {}) => {
	const t = Math.min(MAX_KM, Math.max(MIN_KM, Math.round(km)));
	let p = (BASIS_MIN + ((t - MIN_KM) * (BASIS_MAX - BASIS_MIN)) / (MAX_KM - MIN_KM)) * INDEXATIE;
	if (klasse === 1) {
		p *= t <= 36 ? 1.4 : t <= 51 ? 1.5 : 1.6;
	}
	const dag = moment ? DateTime.fromISO(moment, {setZone: true}).setZone('Europe/Brussels').weekday : 1;
	if (leeftijd && (leeftijd < 26 || leeftijd >= 65)) {
		p *= 0.6;
	} else if (dag >= 6) {
		p *= 0.7;
	}
	return Math.max(MIN_PRIJS, afronden(p));
};
