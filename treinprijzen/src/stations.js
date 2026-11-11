// Stationsgegevens: land en NS International-code (Benerail) per EVA-nummer/UIC-code.
// data/stations.json komt uit de open stationslijst van Trainline (ODbL), zie scripts/maak_stations.py.
import {readFileSync} from 'node:fs';

const TABEL = JSON.parse(readFileSync(new URL('../data/stations.json', import.meta.url), 'utf8'));

const LAND_VAN_PREFIX = {80: 'DE', 81: 'AT', 82: 'LU', 84: 'NL', 85: 'CH', 87: 'FR', 88: 'BE', 70: 'GB', 74: 'SE', 86: 'DK', 54: 'CZ', 51: 'PL'};

export const station = (id) => {
	const s = TABEL[String(id)];
	const land = s?.land || LAND_VAN_PREFIX[String(id).slice(0, 2)] || null;
	return {id: String(id), land, nsi: s?.nsi || null};
};

export const land = (id) => station(id).land;
export const nsiCode = (id) => station(id).nsi;
