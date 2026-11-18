import { postAuditLog } from "./api.js";

const STORAGE_KEY = "flight-right-site-logs-v1";
const BOOT_FLAG_KEY = "flight-right-logger-boot-v1";
const MAX_ENTRIES = 2500;

function readStore() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeStore(entries) {
  try {
    const trimmed = entries.slice(-MAX_ENTRIES);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    /* quota or private mode */
  }
}

/**
 * Append a log line (persisted for this browser tab session).
 * Dispatches `site-log` for live UIs.
 */
export function appendSiteLog({ level = "info", source = "app", message, detail } = {}) {
  const entry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    ts: new Date().toISOString(),
    level: String(level),
    source: String(source),
    message: typeof message === "string" ? message : JSON.stringify(message),
    detail:
      detail == null
        ? undefined
        : typeof detail === "string"
          ? detail
          : (() => {
              try {
                return JSON.stringify(detail);
              } catch {
                return String(detail);
              }
            })(),
  };
  try {
    const next = [...readStore(), entry];
    writeStore(next);
    window.dispatchEvent(new CustomEvent("site-log", { detail: entry }));
  } catch {
    /* ignore */
  }
  return entry;
}

/**
 * Structured log for dashboard actions (shown as level "activity").
 */
export function logActivity(source, message, detail) {
  return appendSiteLog({
    level: "activity",
    source: String(source),
    message: String(message),
    detail: detail != null ? (typeof detail === "string" ? detail : JSON.stringify(detail)) : undefined,
  });
}

let lastPersistWarning = 0;

/**
 * Send one audit entry to the server's append-only audit log (ISSUES.md H1, fixed 25 Sep
 * 2026). Until then `logAudit` wrote only to sessionStorage, which is erased when the tab
 * closes: 44 call sites across 15 files, and `postAuditLog` was exported and never called.
 * Fire-and-forget so the UI never waits on it; a failure is reported honestly in the tab
 * log (at most once a minute) instead of being hidden.
 */
function persistAudit(source, message, detail) {
  let parsed = detail;
  if (typeof detail === "string") {
    try {
      parsed = JSON.parse(detail);
    } catch {
      parsed = { text: detail };
    }
  }
  const body = parsed && typeof parsed === "object" ? parsed : {};
  postAuditLog({
    level: "audit",
    source: `ui:${source}`,
    action: message,
    callsign: body.callsign || body.flightId || undefined,
    conflictId: body.conflictId || body.conflict_id || undefined,
    detail: body,
  }).catch((error) => {
    const now = Date.now();
    if (now - lastPersistWarning > 60_000) {
      lastPersistWarning = now;
      appendSiteLog({
        level: "warning",
        source: "audit",
        message: `Audit entries are NOT reaching the server audit log (${error?.message || "backend unreachable"}); they are kept in this tab only until it recovers.`,
      });
    }
  });
}

/**
 * User / operator control audit (level "audit") — navigation, chrome, log viewer, and explicit UI actions.
 * Recorded in this tab for the live view AND sent to the server's append-only audit log.
 * Use alongside `logActivity` for scenario semantics where both are needed.
 */
export function logAudit(source, message, detail) {
  const entry = appendSiteLog({
    level: "audit",
    source: String(source),
    message: String(message),
    detail: detail != null ? (typeof detail === "string" ? detail : JSON.stringify(detail)) : undefined,
  });
  persistAudit(String(source), String(message), detail);
  return entry;
}

export function getSiteLogs() {
  return readStore();
}

export function clearSiteLogs() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
    sessionStorage.removeItem(BOOT_FLAG_KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("site-log-cleared"));
}

/**
 * Hooks console + toasts + window errors. Idempotent across Vite HMR (single patch, one boot line per tab).
 */
export function initSiteLogger() {
  if (typeof window === "undefined") return;

  const W = window;
  if (!W.__FR_SITE_LOGGER__) {
    W.__FR_SITE_LOGGER__ = {
      originals: {
        log: console.log.bind(console),
        warn: console.warn.bind(console),
        error: console.error.bind(console),
      },
      listeners: false,
      consolePatched: false,
    };
  }
  const cfg = W.__FR_SITE_LOGGER__;

  if (!cfg.listeners) {
    cfg.listeners = true;
    window.addEventListener("show-toast", (e) => {
      const msg = typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail);
      appendSiteLog({ level: "toast", source: "toast", message: msg });
    });

    window.addEventListener("error", (e) => {
      appendSiteLog({
        level: "window:error",
        source: "window",
        message: e.message || "error",
        detail: e.filename ? `${e.filename}:${e.lineno}` : undefined,
      });
    });

    window.addEventListener("unhandledrejection", (e) => {
      const reason = e.reason;
      const msg =
        reason instanceof Error ? reason.stack || reason.message : String(reason);
      appendSiteLog({ level: "window:rejection", source: "window", message: msg });
    });
  }

  if (!cfg.consolePatched) {
    cfg.consolePatched = true;
    (["log", "warn", "error"]).forEach((method) => {
      const orig = cfg.originals[method];
      console[method] = (...args) => {
        try {
          orig(...args);
        } catch {
          /* ignore */
        }
        const parts = args.map((a) => {
          try {
            if (typeof a === "string") return a;
            if (a instanceof Error) return a.stack || a.message;
            if (typeof a === "object") return JSON.stringify(a);
            return String(a);
          } catch {
            return String(a);
          }
        });
        appendSiteLog({
          level:
            method === "log"
              ? "console:log"
              : method === "warn"
                ? "console:warn"
                : "console:error",
          source: "console",
          message: parts.join(" "),
        });
      };
    });
  }

  try {
    if (!sessionStorage.getItem(BOOT_FLAG_KEY)) {
      sessionStorage.setItem(BOOT_FLAG_KEY, "1");
      appendSiteLog({
        level: "info",
        source: "system",
        message:
          "Logger ready — console, toasts, window errors, dashboard activity (level: activity), and operator audit (level: audit) are recorded for this tab.",
      });
    }
  } catch {
    if (!W.__FR_BOOT_LOGGED__) {
      W.__FR_BOOT_LOGGED__ = true;
      appendSiteLog({
        level: "info",
        source: "system",
        message: "Logger ready (sessionStorage blocked — boot line not persisted).",
      });
    }
  }
}
