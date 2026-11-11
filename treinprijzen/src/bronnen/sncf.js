// Frankrijk binnenland: de officiële open data van SNCF Voyageurs (ODbL), "Tarifs TGV INOUI et OUIGO".
// Per herkomst-bestemming en klasse een prijsrange (minimum–maximum, vol tarief). Geen prijs per trein:
// de echte prijs hangt af van het moment van boeken. Alleen TGV INOUI en OUIGO, geen TER of Intercités.
// https://ressources.data.sncf.com/explore/dataset/tarifs-tgv-inoui-ouigo/

export const NAAM = 'SNCF (open data)';
export const BRONNEN = [
	'https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/tarifs-tgv-inoui-ouigo/exports/json',
	'https://www.data.gouv.fr/api/1/datasets/r/83ead953-b2a9-4c90-ac28-48091bb10187',
];

const normNaam = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
	.replace(/\(.*?\)/g, ' ').replace(/[^a-z0-9]+/g, ' ').trim();
// UIC-codes komen voor als 87271007 (met controlecijfer) of 8727100; DB gebruikt 7 cijfers.
const normUic = (s) => {
	const d = String(s ?? '').replace(/\D/g, '');
	return d.length >= 7 ? d.slice(0, 7) : null;
};
const getal = (v) => (typeof v === 'number' ? v : Number(String(v ?? '').replace(',', '.').replace(/[^\d.]/g, '')) || null);

// De veldnamen staan niet vast; zoek ze op naam.
export const vindVelden = (record) => {
	const keys = Object.keys(record);
	const zoek = (...patronen) => keys.find((k) => patronen.every((p) => p.test(k.toLowerCase())));
	return {
		herkomstUic: zoek(/orig/, /uic/),
		bestemmingUic: zoek(/dest/, /uic/),
		herkomst: keys.find((k) => /orig/i.test(k) && !/uic|code|id$/i.test(k)),
		bestemming: keys.find((k) => /dest/i.test(k) && !/uic|code|id$/i.test(k)),
		min: zoek(/min/),
		max: zoek(/max/),
		klasse: zoek(/classe|class/),
		vervoerder: zoek(/transporteur|carrier|marque/),
		profiel: zoek(/profil/),
	};
};

export const bouwIndex = (records) => {
	const perUic = new Map(), perNaam = new Map();
	if (!records?.length) {
		return {perUic, perNaam, aantal: 0};
	}
	const v = vindVelden(records[0]);
	for (const r of records) {
		const min = getal(r[v.min]), max = getal(r[v.max]);
		if (!min && !max) {
			continue;
		}
		const item = {
			min: min ?? max, max: max ?? min,
			klasse: String(r[v.klasse] ?? '2'),
			vervoerder: String(r[v.vervoerder] ?? ''),
			profiel: String(r[v.profiel] ?? ''),
		};
		const a = normUic(r[v.herkomstUic]), b = normUic(r[v.bestemmingUic]);
		if (a && b) {
			const k = `${a}|${b}`;
			perUic.set(k, [...(perUic.get(k) || []), item]);
		}
		const na = normNaam(r[v.herkomst]), nb = normNaam(r[v.bestemming]);
		if (na && nb) {
			const k = `${na}|${nb}`;
			perNaam.set(k, [...(perNaam.get(k) || []), item]);
		}
	}
	return {perUic, perNaam, aantal: records.length};
};

const isTweede = (k) => /2|second|seconde/i.test(k) || k === '';
const isNormaal = (p) => p === '' || /normal|plein|standard|adulte|loisir/i.test(p);

// Prijsrange per persoon voor één rit, of null.
export const zoekRange = (index, {vanId, naarId, vanNaam, naarNaam}, klasse = 2) => {
	const kandidaten = index.perUic.get(`${vanId}|${naarId}`) || index.perUic.get(`${naarId}|${vanId}`)
		|| index.perNaam.get(`${normNaam(vanNaam)}|${normNaam(naarNaam)}`) || index.perNaam.get(`${normNaam(naarNaam)}|${normNaam(vanNaam)}`);
	if (!kandidaten?.length) {
		return null;
	}
	let lijst = kandidaten.filter((k) => (klasse === 1 ? !isTweede(k.klasse) : isTweede(k.klasse)));
	if (lijst.some((k) => isNormaal(k.profiel))) {
		lijst = lijst.filter((k) => isNormaal(k.profiel));
	}
	if (!lijst.length) {
		return null;
	}
	return {
		min: Math.min(...lijst.map((k) => k.min)),
		max: Math.max(...lijst.map((k) => k.max)),
		vervoerders: [...new Set(lijst.map((k) => k.vervoerder).filter(Boolean))],
	};
};

export const maakSncf = ({userAgent, fetchFn = fetch, bronnen = BRONNEN} = {}) => {
	let index = null, geladenOp = 0, laden = null;
	const laad = async () => {
		let fout;
		for (const url of bronnen) {
			try {
				const res = await fetchFn(url, {headers: {'User-Agent': userAgent, 'Accept': 'application/json'}, signal: AbortSignal.timeout(120_000)});
				if (!res.ok) {
					throw new Error(`HTTP ${res.status}`);
				}
				const data = await res.json();
				const records = Array.isArray(data) ? data : (data.results || data.records?.map((r) => r.fields || r) || []);
				const idx = bouwIndex(records);
				if (idx.perUic.size || idx.perNaam.size) {
					return idx;
				}
				throw new Error('onbekend formaat');
			} catch (e) {
				fout = e;
			}
		}
		throw new Error(`SNCF open data niet te laden: ${fout?.message}`);
	};
	return {
		async index() {
			if (index && Date.now() - geladenOp < 24 * 3600_000) {
				return index;
			}
			laden ||= laad().finally(() => {
				laden = null;
			});
			index = await laden;
			geladenOp = Date.now();
			return index;
		},
	};
};
