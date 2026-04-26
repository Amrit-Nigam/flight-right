const express = require("express");
const { appendAuditLog, listAuditLogs } = require("../services/auditService");

const router = express.Router();

router.get("/", async (req, res, next) => {
  try {
    const result = await listAuditLogs({
      limit: req.query.limit,
      level: req.query.level,
      source: req.query.source,
    });
    res.json({ ok: true, count: result.entries.length, ...result });
  } catch (error) {
    next(error);
  }
});

router.post("/", async (req, res, next) => {
  try {
    const result = await appendAuditLog(req.body);
    res.status(201).json({ ok: true, ...result });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
