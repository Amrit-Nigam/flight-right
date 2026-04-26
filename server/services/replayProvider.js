const { REPLAY_AIRCRAFT } = require("../data/replayAircraft");
const { normalizeReplayAircraft } = require("./aircraftNormalizer");

let tick = 0;

function advanceAircraft(raw, seconds) {
  const speedKt = Number(raw.speedKt || 0);
  if (speedKt <= 0) return raw;

  const headingRad = ((Number(raw.heading || 0) - 90) * Math.PI) / 180;
  const nm = (speedKt * seconds) / 3600;
  const latDelta = (nm * Math.sin(headingRad)) / 60;
  const lonDelta = (nm * Math.cos(headingRad)) / (60 * Math.cos((Number(raw.lat) * Math.PI) / 180));

  return {
    ...raw,
    lat: Number(raw.lat) + latDelta,
    lng: Number(raw.lng) + lonDelta,
  };
}

async function getReplayAircraft() {
  tick += 1;
  const now = new Date();
  const seconds = (tick % 60) * 2;
  return REPLAY_AIRCRAFT.map((aircraft) => normalizeReplayAircraft(advanceAircraft(aircraft, seconds), now));
}

module.exports = { getReplayAircraft };
