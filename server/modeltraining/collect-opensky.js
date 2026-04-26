require("dotenv").config();

const fs = require("fs");
const path = require("path");
const { getOpenSkyAircraft } = require("../services/openskyProvider");

const DATA_DIR = path.join(__dirname, "data");
const OUT_FILE = process.env.TRAINING_SNAPSHOT_FILE || path.join(DATA_DIR, "opensky-snapshots.jsonl");
const TARGET_SNAPSHOTS = Number(process.env.TRAINING_SAMPLES || 12);
const CONFIGURED_INTERVAL_MS = Number(process.env.TRAINING_INTERVAL_MS || 60000);
const INTERVAL_MS = Math.max(Number.isFinite(CONFIGURED_INTERVAL_MS) ? CONFIGURED_INTERVAL_MS : 60000, 60000);

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function collect() {
  ensureDir(DATA_DIR);
  console.log("[collect] OpenSky-only training collector");
  console.log(`[collect] writing snapshots to ${OUT_FILE}`);
  console.log(`[collect] target snapshots: ${TARGET_SNAPSHOTS}, interval: ${INTERVAL_MS}ms`);

  let successful = 0;
  let attempts = 0;

  while (successful < TARGET_SNAPSHOTS) {
    attempts += 1;
    try {
      const aircraft = await getOpenSkyAircraft();
      const snapshot = {
        snapshotId: `${Date.now()}-${successful + 1}`,
        collectedAt: new Date().toISOString(),
        source: "opensky",
        count: aircraft.length,
        aircraft,
      };

      fs.appendFileSync(OUT_FILE, `${JSON.stringify(snapshot)}\n`);
      successful += 1;
      console.log(`[collect] saved snapshot ${successful}/${TARGET_SNAPSHOTS}: ${aircraft.length} aircraft`);
    } catch (error) {
      console.warn(`[collect] skipped attempt ${attempts}: ${error.message}`);
      console.warn("[collect] OpenSky can return 429 if you poll too often. Waiting before retry.");
    }

    if (successful < TARGET_SNAPSHOTS) {
      await sleep(INTERVAL_MS);
    }
  }

  console.log("[collect] done");
}

collect().catch((error) => {
  console.error("[collect] failed", error);
  process.exitCode = 1;
});
