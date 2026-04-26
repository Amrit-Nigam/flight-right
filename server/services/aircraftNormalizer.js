function formatAltitude(altitudeFt) {
  const ft = Number(altitudeFt);
  if (!Number.isFinite(ft) || ft <= 0) return "GND";
  if (ft >= 10000) return `FL${Math.round(ft / 100)}`;
  return `${Math.round(ft)}ft`;
}

function formatSpeed(speedKt) {
  const kt = Number(speedKt);
  return `${Number.isFinite(kt) ? Math.max(0, Math.round(kt)) : 0} kt`;
}

function inferStatus({ altitudeFt, speedKt, verticalRateFpm, onGround, sourceStatus }) {
  if (sourceStatus) return String(sourceStatus).toUpperCase();
  if (onGround) return speedKt > 20 ? "DEPARTING" : "DEPARTING";
  if (altitudeFt < 10000 && verticalRateFpm < -150) return "LANDING";
  if (altitudeFt < 10000 && verticalRateFpm > 150) return "TAKEOFF";
  if (altitudeFt < 12000) return "APPROACH";
  return "CRUISE";
}

function inferWaypoint({ lat, lng, altitudeFt, heading }) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "TMA";
  if (altitudeFt < 7000 && lng < 72.75) return "27L ILS";
  if (altitudeFt < 7000 && heading > 240 && heading < 300) return "27R ILS";
  if (lat > 20) return "OKLOV";
  if (lng > 73.2) return "DISHA";
  return "DEGAN";
}

function normalizeReplayAircraft(raw, now = new Date()) {
  const altitudeFt = Number(raw.altitudeFt ?? 0);
  const speedKt = Number(raw.speedKt ?? 0);
  const verticalRateFpm = Number(raw.verticalRateFpm ?? 0);
  const lat = Number(raw.lat);
  const lng = Number(raw.lng);
  const heading = Number(raw.heading ?? 0);

  return {
    icao24: String(raw.icao24 || raw.callsign || "").trim().toLowerCase(),
    callsign: String(raw.callsign || raw.icao24 || "UNKNOWN").trim(),
    originCountry: raw.originCountry || "Unknown",
    lat,
    lng,
    altitude: raw.altitude || formatAltitude(altitudeFt),
    altitudeFt,
    speed: raw.speed || formatSpeed(speedKt),
    speedKt,
    heading,
    verticalRateFpm,
    status: inferStatus({ altitudeFt, speedKt, verticalRateFpm, onGround: raw.onGround, sourceStatus: raw.status }),
    route: raw.route || "BOM TMA",
    aircraft: raw.aircraft || "UNK",
    eta: raw.eta || "TBD",
    squawk: raw.squawk || "----",
    fuel: raw.fuel || "TBD",
    waypoint: raw.waypoint || inferWaypoint({ lat, lng, altitudeFt, heading }),
    cpaPair: raw.cpaPair,
    cpaSeconds: raw.cpaSeconds,
    updatedAt: now.toISOString(),
    source: raw.source || "replay",
  };
}

function normalizeOpenSkyState(state, now = new Date()) {
  const [
    icao24,
    callsign,
    originCountry,
    timePosition,
    lastContact,
    longitude,
    latitude,
    baroAltitudeM,
    onGround,
    velocityMs,
    trueTrack,
    verticalRateMs,
    ,
    geoAltitudeM,
    squawk,
  ] = state;

  const lat = Number(latitude);
  const lng = Number(longitude);
  const altitudeM = Number.isFinite(Number(geoAltitudeM)) ? Number(geoAltitudeM) : Number(baroAltitudeM);
  const altitudeFt = Number.isFinite(altitudeM) ? altitudeM * 3.28084 : 0;
  const speedKt = Number.isFinite(Number(velocityMs)) ? Number(velocityMs) * 1.94384 : 0;
  const verticalRateFpm = Number.isFinite(Number(verticalRateMs)) ? Number(verticalRateMs) * 196.8504 : 0;
  const heading = Number.isFinite(Number(trueTrack)) ? Number(trueTrack) : 0;

  return normalizeReplayAircraft(
    {
      icao24,
      callsign: String(callsign || icao24 || "UNKNOWN").trim() || String(icao24 || "UNKNOWN").toUpperCase(),
      originCountry,
      lat,
      lng,
      altitudeFt,
      speedKt,
      heading,
      verticalRateFpm,
      onGround,
      squawk,
      route: "OpenSky live",
      aircraft: "ADS-B",
      eta: "LIVE",
      fuel: "N/A",
      source: "opensky",
      lastContact,
      timePosition,
    },
    now
  );
}

function isValidAircraft(aircraft) {
  return (
    aircraft &&
    Number.isFinite(aircraft.lat) &&
    Number.isFinite(aircraft.lng) &&
    aircraft.lat >= -90 &&
    aircraft.lat <= 90 &&
    aircraft.lng >= -180 &&
    aircraft.lng <= 180
  );
}

module.exports = {
  formatAltitude,
  formatSpeed,
  normalizeReplayAircraft,
  normalizeOpenSkyState,
  isValidAircraft,
};
