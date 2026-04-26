const { isValidAircraft, normalizeOpenSkyState } = require("./aircraftNormalizer");

const DEFAULT_BOUNDS = {
  lamin: Number(process.env.OPENSKY_LAMIN || 16.0),
  lamax: Number(process.env.OPENSKY_LAMAX || 23.5),
  lomin: Number(process.env.OPENSKY_LOMIN || 68.0),
  lomax: Number(process.env.OPENSKY_LOMAX || 77.5),
};

function buildOpenSkyUrl(bounds = DEFAULT_BOUNDS) {
  const params = new URLSearchParams({
    lamin: String(bounds.lamin),
    lamax: String(bounds.lamax),
    lomin: String(bounds.lomin),
    lomax: String(bounds.lomax),
  });
  return `https://opensky-network.org/api/states/all?${params.toString()}`;
}

async function getOpenSkyAircraft() {
  if (typeof fetch !== "function") {
    throw new Error("Node fetch is unavailable. Use Node 18+ or switch to replay mode.");
  }

  const headers = {};
  if (process.env.OPENSKY_USERNAME && process.env.OPENSKY_PASSWORD) {
    const token = Buffer.from(`${process.env.OPENSKY_USERNAME}:${process.env.OPENSKY_PASSWORD}`).toString("base64");
    headers.Authorization = `Basic ${token}`;
  }

  const response = await fetch(buildOpenSkyUrl(), { headers });
  if (!response.ok) {
    throw new Error(`OpenSky responded with ${response.status}`);
  }

  const payload = await response.json();
  const states = Array.isArray(payload.states) ? payload.states : [];
  const now = new Date();
  return states.map((state) => normalizeOpenSkyState(state, now)).filter(isValidAircraft);
}

module.exports = { getOpenSkyAircraft, buildOpenSkyUrl, DEFAULT_BOUNDS };
