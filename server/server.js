require("dotenv").config();

const express = require("express");
const cors = require("cors");
const aircraftRoutes = require("./routes/aircraftRoutes");
const auditRoutes = require("./routes/auditRoutes");
const { getAircraftSnapshot, startAircraftPolling } = require("./services/aircraftService");
const { connectMongo, getMongoStatus } = require("./services/db");

const app = express();
const PORT = Number(process.env.PORT || 3000);
const CLIENT_ORIGIN = process.env.CLIENT_ORIGIN || "http://localhost:5173";

app.use(
  cors({
    origin: [CLIENT_ORIGIN, "http://127.0.0.1:5173"],
    credentials: true,
  })
);
app.use(express.json({ limit: "1mb" }));

app.get("/", (req, res) => {
  res.json({
    ok: true,
    name: "Flight Right API",
    docs: ["/api/health", "/api/aircraft/latest", "/api/audit"],
  });
});

app.get("/api/health", (req, res) => {
  const snapshot = getAircraftSnapshot();
  res.json({
    ok: true,
    uptime: process.uptime(),
    mongo: getMongoStatus(),
    aircraft: {
      count: snapshot.flights.length,
      source: snapshot.source,
      provider: snapshot.provider,
      updatedAt: snapshot.updatedAt,
      error: snapshot.error,
    },
  });
});

app.use("/api/aircraft", aircraftRoutes);
app.use("/api/audit", auditRoutes);

app.use((req, res) => {
  res.status(404).json({ ok: false, error: "Not found" });
});

app.use((error, req, res, next) => {
  console.error("[api:error]", error);
  res.status(500).json({ ok: false, error: error.message || "Internal server error" });
});

async function start() {
  await connectMongo();
  startAircraftPolling();

  app.listen(PORT, () => {
    console.log(`Flight Right API running on http://localhost:${PORT}`);
  });
}

start();