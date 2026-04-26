const fs = require("fs");
const path = require("path");

const DATA_DIR = path.join(__dirname, "data");
const ARTIFACT_DIR = path.join(__dirname, "artifacts");
const INPUT_FILE = process.env.CONFLICT_DATASET_FILE || path.join(DATA_DIR, "conflict-pairs.jsonl");
const MODEL_FILE = process.env.CONFLICT_MODEL_FILE || path.join(ARTIFACT_DIR, "conflict-baseline-model.json");

const FEATURE_NAMES = [
  "currentDistanceNm",
  "verticalSeparationFt",
  "headingDiffDeg",
  "speedDiffKt",
  "relAltitudeFt",
  "relVerticalRateFpm",
  "closingSpeedKt",
  "minProjectedDistanceNm",
  "timeToMinMinutes",
  "speedA",
  "speedB",
  "altitudeA",
  "altitudeB",
];

const EPOCHS = Number(process.env.TRAINING_EPOCHS || 600);
const LEARNING_RATE = Number(process.env.TRAINING_LR || 0.08);
const L2 = Number(process.env.TRAINING_L2 || 0.001);

function sigmoid(x) {
  if (x < -30) return 0;
  if (x > 30) return 1;
  return 1 / (1 + Math.exp(-x));
}

function readRows() {
  if (!fs.existsSync(INPUT_FILE)) {
    throw new Error(`Missing dataset file: ${INPUT_FILE}. Run npm run dataset:conflicts first.`);
  }
  return fs
    .readFileSync(INPUT_FILE, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function vectorize(row) {
  return FEATURE_NAMES.map((name) => Number(row.features?.[name] ?? 0));
}

function fitScaler(vectors) {
  const means = FEATURE_NAMES.map((_, idx) => vectors.reduce((sum, row) => sum + row[idx], 0) / vectors.length);
  const stds = FEATURE_NAMES.map((_, idx) => {
    const variance = vectors.reduce((sum, row) => sum + (row[idx] - means[idx]) ** 2, 0) / vectors.length;
    return Math.sqrt(variance) || 1;
  });
  return { means, stds };
}

function scale(row, scaler) {
  return row.map((value, idx) => (value - scaler.means[idx]) / scaler.stds[idx]);
}

function predictProba(weights, bias, row) {
  const z = row.reduce((sum, value, idx) => sum + value * weights[idx], bias);
  return sigmoid(z);
}

function evaluate(weights, bias, x, y) {
  let tp = 0;
  let tn = 0;
  let fp = 0;
  let fn = 0;

  x.forEach((row, idx) => {
    const pred = predictProba(weights, bias, row) >= 0.5 ? 1 : 0;
    if (pred === 1 && y[idx] === 1) tp += 1;
    else if (pred === 0 && y[idx] === 0) tn += 1;
    else if (pred === 1 && y[idx] === 0) fp += 1;
    else fn += 1;
  });

  const accuracy = (tp + tn) / Math.max(1, x.length);
  const precision = tp / Math.max(1, tp + fp);
  const recall = tp / Math.max(1, tp + fn);
  const f1 = (2 * precision * recall) / Math.max(1e-9, precision + recall);
  return { accuracy, precision, recall, f1, tp, tn, fp, fn };
}

function train() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
  const rows = readRows();
  if (rows.length < 10) {
    throw new Error(`Need at least 10 pair rows to train; found ${rows.length}. Collect more OpenSky snapshots.`);
  }

  const positives = rows.filter((row) => row.label === 1).length;
  if (positives === 0) {
    throw new Error("Dataset has 0 positive conflict labels. Collect more data or use a wider scenario/threshold for training.");
  }

  const vectors = rows.map(vectorize);
  const labels = rows.map((row) => Number(row.label || 0));
  const scaler = fitScaler(vectors);
  const x = vectors.map((row) => scale(row, scaler));
  const y = labels;

  const weights = new Array(FEATURE_NAMES.length).fill(0);
  let bias = 0;
  const posWeight = (rows.length - positives) / Math.max(1, positives);

  for (let epoch = 0; epoch < EPOCHS; epoch += 1) {
    const gradW = new Array(FEATURE_NAMES.length).fill(0);
    let gradB = 0;

    x.forEach((row, idx) => {
      const weight = y[idx] === 1 ? posWeight : 1;
      const pred = predictProba(weights, bias, row);
      const error = (pred - y[idx]) * weight;
      row.forEach((value, featureIdx) => {
        gradW[featureIdx] += error * value;
      });
      gradB += error;
    });

    weights.forEach((_, idx) => {
      gradW[idx] = gradW[idx] / rows.length + L2 * weights[idx];
      weights[idx] -= LEARNING_RATE * gradW[idx];
    });
    bias -= LEARNING_RATE * (gradB / rows.length);
  }

  const metrics = evaluate(weights, bias, x, y);
  const artifact = {
    modelType: "logistic_regression_baseline",
    createdAt: new Date().toISOString(),
    source: "opensky-derived conflict-pairs dataset",
    featureNames: FEATURE_NAMES,
    scaler,
    weights,
    bias,
    threshold: 0.5,
    training: {
      rows: rows.length,
      positives,
      negatives: rows.length - positives,
      epochs: EPOCHS,
      learningRate: LEARNING_RATE,
      l2: L2,
      metrics,
    },
  };

  fs.writeFileSync(MODEL_FILE, JSON.stringify(artifact, null, 2));
  console.log(`[train] rows: ${rows.length}, positives: ${positives}`);
  console.log(`[train] metrics: ${JSON.stringify(metrics)}`);
  console.log(`[train] wrote ${MODEL_FILE}`);
}

try {
  train();
} catch (error) {
  console.error("[train] failed", error.message);
  process.exitCode = 1;
}
