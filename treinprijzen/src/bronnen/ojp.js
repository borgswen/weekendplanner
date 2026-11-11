// Zwitserland binnenland: OJP Fare van opentransportdata.swiss (officieel open data van de Zwitserse OV-sector).
// Stap 1: OJPTripRequest (OJP 2.0) voor de verbindingen; stap 2: OJPFareRequest met diezelfde trips → NOVA-prijs.
// Let op: dit is een bètadienst met gegevens uit het testsysteem van NOVA. Prijzen zijn een richtprijs.
// Gratis sleutel: https://api-manager.opentransportdata.swiss (abonneer op "OJP 2.0" en "OJP Fare").
import {Rem} from '../cache.js';

export const NAAM = 'SBB (OJP Fare)';
const TRIP_URL = 'https://api.opentransportdata.swiss/ojp20';
const FARE_URL = 'https://api.opentransportdata.swiss/ojpfare';
const DAGKAART = '2361'; // volgens de handleiding soms onterecht als goedkoopste: wegfilteren

const esc = (s) => String(s).replace(/[<&>]/g, (c) => ({'<': '&lt;', '&': '&amp;', '>': '&gt;'}[c]));
const kop = (requestor) => `<?xml version="1.0" encoding="UTF-8"?>
<OJP xmlns="http://www.vdv.de/ojp" xmlns:ojp="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri" version="2.0">
<OJPRequest><siri:ServiceRequest><siri:RequestTimestamp>${new Date().toISOString()}</siri:RequestTimestamp><siri:RequestorRef>${esc(requestor)}</siri:RequestorRef>`;
const staart = '</siri:ServiceRequest></OJPRequest></OJP>';

export const tripVerzoek = (vanId, naarId, isoTijd, requestor) => `${kop(requestor)}
<OJPTripRequest><siri:RequestTimestamp>${new Date().toISOString()}</siri:RequestTimestamp>
<Origin><PlaceRef><siri:StopPointRef>${esc(vanId)}</siri:StopPointRef><Name><Text>van</Text></Name></PlaceRef><DepArrTime>${esc(isoTijd)}</DepArrTime></Origin>
<Destination><PlaceRef><siri:StopPointRef>${esc(naarId)}</siri:StopPointRef><Name><Text>naar</Text></Name></PlaceRef></Destination>
<Params><NumberOfResults>5</NumberOfResults><IncludeIntermediateStops>true</IncludeIntermediateStops><UseRealtimeData>none</UseRealtimeData></Params>
</OJPTripRequest>${staart}`;

// Regex-hulp die werkt met en zonder namespace-voorvoegsel (ojp:, siri:)
const T = (naam) => `(?:[\\w-]+:)?${naam}`;
const alle = (xml, naam) => [...xml.matchAll(new RegExp(`<${T(naam)}(?:\\s[^>]*)?>([\\s\\S]*?)</${T(naam)}>`, 'g'))].map((m) => m[1]);
const eerste = (xml, naam) => alle(xml, naam)[0]?.trim() ?? null;

// Trips uit de TripDelivery, met de perrons vervangen door het hele station (nodig voor NOVA).
export const leesTrips = (xml) => {
	const ouder = new Map();
	for (const sp of alle(xml, 'StopPoint')) {
		const ref = eerste(sp, 'StopPointRef'), parent = eerste(sp, 'ParentRef');
		if (ref && parent) {
			ouder.set(ref, parent);
		}
	}
	const trips = [];
	for (const m of xml.matchAll(new RegExp(`<${T('Trip')}>[\\s\\S]*?</${T('Trip')}>`, 'g'))) {
		let tripXml = m[0];
		tripXml = tripXml.replace(new RegExp(`(<${T('StopPointRef')}>)([^<]+)(</${T('StopPointRef')}>)`, 'g'),
			(_, a, ref, b) => `${a}${esc(ouder.get(ref.trim()) || ref.trim())}${b}`);
		const legs = alle(tripXml, 'TimedLeg');
		const vertrek = legs.length ? eerste(eerste(legs[0], 'LegBoard') || '', 'TimetabledTime') : eerste(tripXml, 'StartTime');
		const aankomst = legs.length ? eerste(eerste(legs.at(-1), 'LegAlight') || '', 'TimetabledTime') : eerste(tripXml, 'EndTime');
		trips.push({id: eerste(tripXml, 'Id'), vertrek, aankomst, xml: tripXml});
	}
	return trips;
};

export const fareVerzoek = (trips, requestor, klasse = 2) => `${kop(requestor)}
${trips.map((t) => `<OJPFareRequest><siri:RequestTimestamp>${new Date().toISOString()}</siri:RequestTimestamp>
<TripFareRequest>${t.xml}</TripFareRequest>
<Params><FareAuthorityFilter>ch:1:NOVA</FareAuthorityFilter><PassengerCategory>Adult</PassengerCategory><FareClass>${klasse === 1 ? 'firstClass' : 'secondClass'}</FareClass><Traveller><PassengerCategory>Adult</PassengerCategory></Traveller></Params>
</OJPFareRequest>`).join('\n')}${staart}`;

// Per FareResult (één per trip) de goedkoopste prijs per deeltraject, opgeteld. In CHF.
export const leesPrijzen = (xml, klasse = 2) => alle(xml, 'FareResult').map((fr) => {
	let totaal = 0, compleet = true;
	const delen = alle(fr, 'TripFareResult');
	if (!delen.length || eerste(fr, 'ErrorCondition')) {
		compleet = false;
	}
	for (const deel of delen) {
		const producten = alle(deel, 'FareProduct').map((p) => ({
			id: eerste(p, 'FareProductId'), naam: eerste(p, 'FareProductName'),
			prijs: Number(eerste(p, 'Price')), munt: eerste(p, 'Currency') || 'CHF',
			klasse: eerste(p, 'FareClass') || eerste(p, 'TravelClass') || '',
		})).filter((p) => Number.isFinite(p.prijs) && p.id !== DAGKAART)
			.filter((p) => !p.klasse || (klasse === 1 ? /first/i.test(p.klasse) : /second/i.test(p.klasse)));
		if (!producten.length) {
			compleet = false;
			continue;
		}
		totaal += Math.min(...producten.map((p) => p.prijs));
	}
	return {chf: Math.round(totaal * 100) / 100, compleet};
});

export const maakOjp = ({tripKey, fareKey, requestor = 'weekendplanner_prod', fetchFn = fetch} = {}) => {
	const rem = new Rem(1000);
	const post = async (url, key, body) => {
		await rem.wacht();
		const res = await fetchFn(url, {
			method: 'POST', body,
			headers: {'Authorization': `Bearer ${key}`, 'Content-Type': 'application/xml; charset=utf-8', 'Accept': 'application/xml'},
			signal: AbortSignal.timeout(40_000),
		});
		if (!res.ok) {
			throw new Error(`opentransportdata.swiss gaf HTTP ${res.status}`);
		}
		return res.text();
	};
	return {
		actief: Boolean(fareKey),
		/** @returns [{vertrek, aankomst (ISO), chf, compleet}] voor één reiziger */
		async zoek(vanId, naarId, isoTijd, {klasse = 2} = {}) {
			const tripXml = await post(TRIP_URL, tripKey || fareKey, tripVerzoek(vanId, naarId, isoTijd, requestor));
			const trips = leesTrips(tripXml);
			if (!trips.length) {
				return [];
			}
			const prijzen = leesPrijzen(await post(FARE_URL, fareKey, fareVerzoek(trips, requestor, klasse)), klasse);
			return trips.map((t, i) => ({vertrek: t.vertrek, aankomst: t.aankomst, ...(prijzen[i] || {chf: null, compleet: false})}));
		},
	};
};
