// Eenvoudige cache in het geheugen, plus een rem zodat we de sites niet bestoken.

export class Cache {
	constructor(maxItems = 2000) {
		this.map = new Map();
		this.maxItems = maxItems;
	}

	async haal(sleutel, minuten, maak) {
		const nu = Date.now();
		const hit = this.map.get(sleutel);
		if (hit && hit.tot > nu) {
			return hit.waarde;
		}
		// Gelijktijdige vragen naar hetzelfde delen één verzoek.
		const belofte = maak();
		this.map.set(sleutel, {tot: nu + minuten * 60_000, waarde: belofte});
		try {
			const waarde = await belofte;
			this.map.set(sleutel, {tot: nu + minuten * 60_000, waarde});
			this.#opruimen();
			return waarde;
		} catch (e) {
			this.map.delete(sleutel);
			throw e;
		}
	}

	#opruimen() {
		while (this.map.size > this.maxItems) {
			this.map.delete(this.map.keys().next().value);
		}
	}
}

// Maximaal één verzoek per `afstandMs` naar dezelfde site.
export class Rem {
	constructor(afstandMs) {
		this.afstandMs = afstandMs;
		this.volgende = 0;
	}

	async wacht() {
		const nu = Date.now();
		const start = Math.max(nu, this.volgende);
		this.volgende = start + this.afstandMs;
		if (start > nu) {
			await new Promise((r) => setTimeout(r, start - nu));
		}
	}
}
