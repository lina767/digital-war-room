export interface GeointAnomaly {
  latitude: number;
  longitude: number;
  frp: number;
  confidence: string;
  classification: string;
}

export interface SigintAircraft {
  flight: string;
  lat: number;
  lon: number;
  category?: string;
  /** Country of registration / operator (derived from ICAO hex or registration). */
  country?: string;
}

export interface SigintShip {
  name: string;
  lat: number;
  lon: number;
  type?: string;
}
