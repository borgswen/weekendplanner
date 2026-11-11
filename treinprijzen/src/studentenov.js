// Studentenreisproduct (DUO): wanneer reis je gratis, met 40% korting of voor de volle prijs?
// Bron: https://www.studentenreisproduct.nl/en/productvoorwaarden/ (geldt alleen binnen Nederland).
import {DateTime} from 'luxon';

const ZONE = 'Europe/Amsterdam';

const pasen = (jaar) => {
	// Anonieme Gregoriaanse berekening
	const a = jaar % 19, b = Math.floor(jaar / 100), c = jaar % 100;
	const d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
	const g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
	const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
	const m = Math.floor((a + 11 * h + 22 * l) / 451);
	const maand = Math.floor((h + l - 7 * m + 114) / 31), dag = ((h + l - 7 * m + 114) % 31) + 1;
	return DateTime.fromObject({year: jaar, month: maand, day: dag}, {zone: ZONE});
};

const iso = (dt) => dt.toISODate();

export const feestdagen = (jaar) => {
	const p = pasen(jaar);
	let koningsdag = DateTime.fromObject({year: jaar, month: 4, day: 27}, {zone: ZONE});
	if (koningsdag.weekday === 7) {
		koningsdag = koningsdag.minus({days: 1});
	}
	const bevrijdingsdag = DateTime.fromObject({year: jaar, month: 5, day: 5}, {zone: ZONE});
	const goedeVrijdag = p.minus({days: 2});
	const hemelvaart = p.plus({days: 39});
	const alle = [
		DateTime.fromObject({year: jaar, month: 1, day: 1}, {zone: ZONE}),
		goedeVrijdag, p, p.plus({days: 1}), koningsdag, bevrijdingsdag, hemelvaart,
		p.plus({days: 49}), p.plus({days: 50}),
		DateTime.fromObject({year: jaar, month: 12, day: 25}, {zone: ZONE}),
		DateTime.fromObject({year: jaar, month: 12, day: 26}, {zone: ZONE}),
	];
	return {
		alle: new Set(alle.map(iso)),
		goedeVrijdag: iso(goedeVrijdag),
		// Vanaf 12:00 de dag ervoor al gratis met een weekendabonnement
		metVooravond: new Set([goedeVrijdag, koningsdag, bevrijdingsdag, hemelvaart].map(iso)),
	};
};

/**
 * @param {'week'|'weekend'|'geen'} abonnement
 * @param {string|DateTime} moment vertrektijd (inchecken)
 * @returns {'gratis'|'korting'|'vol'}
 */
export const tarief = (abonnement, moment) => {
	if (abonnement !== 'week' && abonnement !== 'weekend') {
		return 'vol';
	}
	const t = (typeof moment === 'string' ? DateTime.fromISO(moment, {zone: ZONE}) : moment).setZone(ZONE);
	// Een "reisdag" loopt van 04:00 tot 04:00.
	const dag = t.minus({hours: 4});
	const fd = feestdagen(dag.year);
	const isFeestdag = fd.alle.has(iso(dag));

	if (abonnement === 'week') {
		if (iso(dag) === fd.goedeVrijdag) {
			return 'gratis';
		}
		const zomer = (dag.month === 7 && dag.day >= 16) || (dag.month === 8 && dag.day < 16);
		if (isFeestdag || zomer) {
			return 'korting';
		}
		return dag.weekday <= 5 ? 'gratis' : 'korting';
	}

	// Weekendabonnement
	if (isFeestdag) {
		return 'gratis';
	}
	const morgen = dag.plus({days: 1});
	const vooravond = feestdagen(morgen.year).metVooravond.has(iso(morgen));
	const naTwaalfUur = !t.hasSame(dag, 'day') || t.hour >= 12;
	if (vooravond && naTwaalfUur) {
		return 'gratis';
	}
	if (dag.weekday === 6 || dag.weekday === 7 || (dag.weekday === 5 && naTwaalfUur)) {
		return 'gratis';
	}
	if (t.weekday >= 2 && t.weekday <= 5 && t.hour >= 4 && t.hour < 9) {
		return 'vol';
	}
	return 'korting';
};

export const KORTING = 0.4;
