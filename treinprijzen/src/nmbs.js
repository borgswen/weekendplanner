// Schatting van NMBS-prijzen in België (sinds 15 oktober 2025 per kilometer).
// Bekend: minimaal ±€2,60 (3 km), maximaal €20,90 (tariefafstand 116-118 km), weekend 30% korting voor
// volwassenen, jongeren onder 26 en 65-plussers 40% korting, 1e klas ×1,4 / ×1,5 / ×1,6 per afstandsschijf.
// De officiële tariefkilometers kennen we niet; we schatten ze uit de hemelsbrede afstand × 1,2.
import {DateTime} from 'luxon';

const MIN_KM = 3, MAX_KM = 118;
const MIN_PRIJS = 2.6, MAX_PRIJS = 20.9;

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
		const a = plek(l.origin), b = plek(l.destination);
		if (!a || !b) {
			return null;
		}
		km += haversine(a, b) * 1.2;
	}
	return km || null;
};

const afronden = (p) => (p < 25 ? Math.round(p * 10) / 10 : p < 50 ? Math.round(p * 2) / 2 : Math.round(p));

export const nmbsPrijs = (km, {leeftijd, klasse = 2, moment} = {}) => {
	const t = Math.min(MAX_KM, Math.max(MIN_KM, Math.round(km)));
	let p = MIN_PRIJS + ((t - MIN_KM) * (MAX_PRIJS - MIN_PRIJS)) / (MAX_KM - MIN_KM);
	if (klasse === 1) {
		p *= t <= 36 ? 1.4 : t <= 51 ? 1.5 : 1.6;
	}
	const dag = moment ? DateTime.fromISO(moment, {setZone: true}).setZone('Europe/Brussels').weekday : 1;
	if (leeftijd && (leeftijd < 26 || leeftijd >= 65)) {
		p *= 0.6;
	} else if (dag >= 6) {
		p *= 0.7;
	}
	return afronden(p);
};
