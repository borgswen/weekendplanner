// Deutsche Bahn via de DB Navigator-API (db-vendo-client, profiel "dbnav").
// Levert de dienstregeling voor heel Benelux + Duitsland, en de prijs waarvoor bahn.de/DB Navigator
// de reis verkoopt (voor de hele groep). Grens: ±60 verzoeken per minuut, dus remmen en cachen.
import {createClient} from 'db-vendo-client';
import {profile as dbnav} from 'db-vendo-client/p/dbnav/index.js';
import {Rem} from '../cache.js';

export const NAAM = 'bahn.de';

export const maakDb = ({userAgent, client} = {}) => {
	const c = client || createClient(dbnav, userAgent, {enrichStations: false});
	const rem = new Rem(1100);

	const reizigers = ({leeftijden, personen}) => leeftijden?.length
		? {age: leeftijden}
		: {ageGroup: Array(personen || 1).fill('E')};

	return {
		async locaties(tekst, aantal = 5) {
			await rem.wacht();
			const res = await c.locations(tekst, {results: aantal, addresses: false, poi: false, stops: true});
			return res.filter((l) => l.id && (l.type === 'station' || l.type === 'stop'))
				.map((l) => ({id: String(l.id), naam: l.name, lat: l.location?.latitude, lon: l.location?.longitude}));
		},

		async reizen(van, naar, {vertrek, aankomst, leeftijden, personen, klasse = 2, later}) {
			await rem.wacht();
			const opt = {
				...reizigers({leeftijden, personen}),
				firstClass: klasse === 1,
				stopovers: false,
				remarks: false,
				language: 'nl',
			};
			if (later) {
				opt.laterThan = later;
			} else if (aankomst) {
				opt.arrival = aankomst;
			} else {
				opt.departure = vertrek;
			}
			const res = await c.journeys(van, naar, opt);
			return {reizen: res.journeys, later: res.laterRef};
		},

		// Goedkoopste reizen van een hele dag ("Bestpreise" / Tagesbestpreis).
		async dagprijzen(van, naar, {datum, leeftijden, personen, klasse = 2}) {
			await rem.wacht();
			const res = await c.journeys(van, naar, {
				...reizigers({leeftijden, personen}),
				firstClass: klasse === 1,
				bestprice: true,
				departure: datum,
				remarks: false,
				language: 'nl',
			});
			return res.journeys;
		},
	};
};
