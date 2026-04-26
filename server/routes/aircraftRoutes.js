const express = require("express");
const { getAircraftSnapshot, refreshAircraft } = require("../services/aircraftService");

const router = express.Router();

router.get("/latest", (req, res) => {
  const snapshot = getAircraftSnapshot();
  res.json({
    ok: true,
    count: snapshot.flights.length,
    source: snapshot.source,
    provider: snapshot.provider,
    updatedAt: snapshot.updatedAt,
    error: snapshot.error,
    flights: snapshot.flights,
  });
});

router.get("/source", (req, res) => {
  const snapshot = getAircraftSnapshot();
  res.json({
    ok: true,
    source: snapshot.source,
    provider: snapshot.provider,
    updatedAt: snapshot.updatedAt,
    error: snapshot.error,
    pollMs: snapshot.pollMs,
  });
});

router.post("/refresh", async (req, res, next) => {
  try {
    const snapshot = await refreshAircraft();
    res.json({ ok: true, ...snapshot, count: snapshot.flights.length });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
