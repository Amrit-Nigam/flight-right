const mongoose = require("mongoose");

const AuditLogSchema = new mongoose.Schema(
  {
    ts: { type: Date, default: Date.now, index: true },
    level: { type: String, default: "audit", index: true },
    source: { type: String, default: "app", index: true },
    message: { type: String, required: true },
    detail: { type: mongoose.Schema.Types.Mixed },
    userId: { type: String, default: "demo-controller", index: true },
    sessionId: { type: String, default: "local-session", index: true },
    clientTs: { type: Date },
  },
  { collection: "audit_logs" }
);

module.exports = mongoose.models.AuditLog || mongoose.model("AuditLog", AuditLogSchema);
