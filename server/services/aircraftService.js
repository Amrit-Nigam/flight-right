const { getOpenSkyAircraft } = require("./openskyProvider");
const { getReplayAircraft } = require("./replayProvider");

const SOURCE = (process.env.AIRCRAFT_SOURCE || "replay").toLowerCase();
const POLL_MS = Number(process.env.AIRCRAFT_POLL_MS || 10000);

let cache = {
  flights: [],
  source: SOURCE,
  provider: "none",
  updatedAt: null,
  error: null,
  pollMs: POLL_MS,
};

let pollTimer = null;

async function refreshAircraft() {
  const requestedSource = SOURCE === "opensky" ? "opensky" : "replay";

  try {
    const flights = requestedSource === "opensky" ? await getOpenSkyAircraft() : await getReplayAircraft();
    cache = {
      flights,
      source: requestedSource,
      provider: requestedSource,
      updatedAt: new Date().toISOString(),
      error: null,
      pollMs: POLL_MS,
    };
  } catch (error) {
    const fallbackFlights = await getReplayAircraft();
    cache = {
      flights: fallbackFlights,
      source: requestedSource,
      provider: "replay-fallback",
      updatedAt: new Date().toISOString(),
      error: error.message,
      pollMs: POLL_MS,
    };
  }

  return cache;
}

function getAircraftSnapshot() {
  return cache;
}

function startAircraftPolling() {
  if (pollTimer) return;
  refreshAircraft();
  pollTimer = setInterval(refreshAircraft, POLL_MS);
}

function stopAircraftPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

module.exports = {
  getAircraftSnapshot,
  refreshAircraft,
  startAircraftPolling,
  stopAircraftPolling,
};
