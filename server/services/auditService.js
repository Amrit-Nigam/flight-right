const mongoose = require("mongoose");
const AuditLog = require("../models/AuditLog");

const memoryAuditLogs = [];
const MAX_MEMORY_LOGS = 1000;

function normalizeAuditPayload(payload = {}) {
  const detail =
    typeof payload.detail === "string"
      ? (() => {
          try {
            return JSON.parse(payload.detail);
          } catch {
            return payload.detail;
          }
        })()
      : payload.detail;

  return {
    ts: new Date(),
    level: String(payload.level || "audit"),
    source: String(payload.source || "app"),
    message: String(payload.message || payload.action || "Audit event"),
    detail,
    userId: String(payload.userId || "demo-controller"),
    sessionId: String(payload.sessionId || "local-session"),
    clientTs: payload.ts ? new Date(payload.ts) : undefined,
  };
}

async function appendAuditLog(payload) {
  const entry = normalizeAuditPayload(payload);

  if (mongoose.connection.readyState === 1) {
    const saved = await AuditLog.create(entry);
    return { storedIn: "mongodb", entry: saved.toObject() };
  }

  memoryAuditLogs.push({ id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`, ...entry });
  if (memoryAuditLogs.length > MAX_MEMORY_LOGS) memoryAuditLogs.splice(0, memoryAuditLogs.length - MAX_MEMORY_LOGS);
  return { storedIn: "memory", entry: memoryAuditLogs[memoryAuditLogs.length - 1] };
}

async function listAuditLogs({ limit = 100, level, source } = {}) {
  const safeLimit = Math.min(Math.max(Number(limit) || 100, 1), 500);

  if (mongoose.connection.readyState === 1) {
    const query = {};
    if (level) query.level = level;
    if (source) query.source = source;
    const rows = await AuditLog.find(query).sort({ ts: -1 }).limit(safeLimit).lean();
    return { storedIn: "mongodb", entries: rows };
  }

  let rows = [...memoryAuditLogs];
  if (level) rows = rows.filter((row) => row.level === level);
  if (source) rows = rows.filter((row) => row.source === source);
  return { storedIn: "memory", entries: rows.slice(-safeLimit).reverse() };
}

module.exports = { appendAuditLog, listAuditLogs };
