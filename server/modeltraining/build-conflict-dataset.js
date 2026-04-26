const fs = require("fs");
const path = require("path");
const {
  bearingDiffDeg,
  closingSpeedKt,
  haversineNm,
  minProjectedSeparation,
  verticalSeparationFt,
} = require("./lib/geo");

const DATA_DIR = path.join(__dirname, "data");
const INPUT_FILE = process.env.TRAINING_SNAPSHOT_FILE || path.join(DATA_DIR, "opensky-snapshots.jsonl");
const OUT_FILE = process.env.CONFLICT_DATASET_FILE || path.join(DATA_DIR, "conflict-pairs.jsonl");

const LOOKAHEAD_MINUTES = Number(process.env.CONFLICT_LOOKAHEAD_MINUTES || 10);
const LATERAL_THRESHOLD_NM = Number(process.env.CONFLICT_LATERAL_NM || 5);
const VERTICAL_THRESHOLD_FT = Number(process.env.CONFLICT_VERTICAL_FT || 1000);
const MAX_PAIR_DISTANCE_NM = Number(process.env.CONFLICT_MAX_PAIR_DISTANCE_NM || 120);

function readSnapshots(file) {
  if (!fs.existsSync(file)) {
    throw new Error(`Missing snapshot file: ${file}. Run npm run collect:opensky first.`);
  }

  return fs
    .readFileSync(file, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function validTrainingAircraft(aircraft) {
  return (
    aircraft &&
    Number.isFinite(Number(aircraft.lat)) &&
    Number.isFinite(Number(aircraft.lng)) &&
    Number.isFinite(Number(aircraft.heading)) &&
    Number.isFinite(Number(aircraft.speedKt)) &&
    Number(aircraft.speedKt) > 30
  );
}

function pairFeatures(a, b, snapshot) {
  const currentDistanceNm = haversineNm(a, b);
  const verticalFt = verticalSeparationFt(a, b);
  const headingDiffDeg = bearingDiffDeg(a.heading, b.heading);
  const speedDiffKt = Math.abs(Number(a.speedKt || 0) - Number(b.speedKt || 0));
  const relAltitudeFt = Math.abs(Number(a.altitudeFt || 0) - Number(b.altitudeFt || 0));
  const relVerticalRateFpm = Math.abs(Number(a.verticalRateFpm || 0) - Number(b.verticalRateFpm || 0));
  const closureKt = closingSpeedKt(a, b);
  const cpa = minProjectedSeparation(a, b, LOOKAHEAD_MINUTES, 1);
  const conflict =
    cpa.minDistanceNm <= LATERAL_THRESHOLD_NM &&
    verticalFt <= VERTICAL_THRESHOLD_FT;

  return {
    snapshotId: snapshot.snapshotId,
    collectedAt: snapshot.collectedAt,
    aircraftA: a.callsign,
    aircraftB: b.callsign,
    features: {
      currentDistanceNm,
      verticalSeparationFt: verticalFt,
      headingDiffDeg,
      speedDiffKt,
      relAltitudeFt,
      relVerticalRateFpm,
      closingSpeedKt: closureKt,
      minProjectedDistanceNm: cpa.minDistanceNm,
      timeToMinMinutes: cpa.timeToMinMinutes,
      speedA: Number(a.speedKt || 0),
      speedB: Number(b.speedKt || 0),
      altitudeA: Number(a.altitudeFt || 0),
      altitudeB: Number(b.altitudeFt || 0),
    },
    label: conflict ? 1 : 0,
    labelReason: conflict ? "projected_cpa_below_threshold" : "no_projected_threshold_breach",
  };
}

function buildDataset() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const snapshots = readSnapshots(INPUT_FILE);
  const rows = [];

  for (const snapshot of snapshots) {
    const aircraft = (snapshot.aircraft || []).filter(validTrainingAircraft);
    for (let i = 0; i < aircraft.length; i += 1) {
      for (let j = i + 1; j < aircraft.length; j += 1) {
        const a = aircraft[i];
        const b = aircraft[j];
        const distanceNm = haversineNm(a, b);
        if (!Number.isFinite(distanceNm) || distanceNm > MAX_PAIR_DISTANCE_NM) continue;
        rows.push(pairFeatures(a, b, snapshot));
      }
    }
  }

  fs.writeFileSync(OUT_FILE, rows.map((row) => JSON.stringify(row)).join("\n") + (rows.length ? "\n" : ""));
  const positives = rows.filter((row) => row.label === 1).length;
  console.log(`[dataset] snapshots: ${snapshots.length}`);
  console.log(`[dataset] rows: ${rows.length}`);
  console.log(`[dataset] positives: ${positives}`);
  console.log(`[dataset] wrote ${OUT_FILE}`);
}

try {
  buildDataset();
} catch (error) {
  console.error("[dataset] failed", error.message);
  process.exitCode = 1;
}
