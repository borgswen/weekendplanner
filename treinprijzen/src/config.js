// Instellingen uit de omgeving (docker-compose / Portainer).

const lijst = (s) => (s || '').split(',').map((x) => x.trim()).filter(Boolean);

export const config = {
	poort: Number(process.env.POORT || 8089),
	// Wie wij zijn tegenover de boekingssites. Eerlijk en herkenbaar.
	userAgent: process.env.USER_AGENT || 'weekendplanner-treinprijzen/1.0 (zelfgehost, prive gebruik)',
	// Standaard reizigers als de vraag niets meegeeft: leeftijden, kommagescheiden ("22,23").
	leeftijden: lijst(process.env.LEEFTIJDEN).map(Number).filter((n) => n > 0 && n < 120),
	// Studentenreisproduct per reiziger, in dezelfde volgorde: "weekend", "week" of "geen".
	studentenOv: lijst(process.env.STUDENTENOV),
	// Gratis sleutel van https://apiportal.ns.nl (product "Ns-App"): binnenlandse NS-prijzen.
	nsApiKey: process.env.NS_API_KEY || '',
	// Bronnen aan/uit zetten: "db,nsi,ns,oebb".
	bronnen: new Set(lijst(process.env.BRONNEN || 'db,nsi,ns,oebb')),
	// Hoe lang een gevonden prijs in de cache blijft (minuten).
	cacheMinuten: Number(process.env.CACHE_MINUTEN || 30),
};
