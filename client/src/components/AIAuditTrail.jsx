import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuditLog } from "@/hooks/useAuditLog";
import { logActivity, logAudit } from "@/lib/siteLogger";
import { History, ChevronDown, ChevronUp, RotateCcw, CheckCircle, XCircle, AlertCircle } from "lucide-react";

const OUTCOME_STYLES = {
  accepted: { color: "var(--green)",  icon: CheckCircle,   label: "Accepted" },
  rejected: { color: "var(--red)",    icon: XCircle,       label: "Rejected" },
  modified: { color: "var(--amber)",  icon: AlertCircle,   label: "Modified" },
  pending:  { color: "var(--teal)",   icon: AlertCircle,   label: "Pending" },
};

// Map a stored audit row onto the shape this list renders. The outcome comes from the
// controller's recorded decision, not from anything the system did on its own.
function present(entry) {
  const outcome = entry.decision === "accepted" ? "accepted"
    : entry.decision === "dismissed" ? "rejected"
    : entry.level === "system" ? "pending" : "modified";
  return {
    id: entry.id,
    time: new Date(entry.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    action: entry.action,
    flight: entry.callsign || entry.conflictId || entry.source,
    outcome,
    by: entry.userId || entry.source,
    confidence: entry.confidence != null ? `${Math.round(entry.confidence * 100)}%` : "--",
  };
}

export default function AIAuditTrail({ isOpen, onToggle }) {
  const { entries: raw, total, error } = useAuditLog({ limit: 40, poll: isOpen });
  const entries = raw.map(present);
  const [undoneIds, setUndoneIds] = useState(new Set());

  const handleUndo = (id) => {
    const entry = entries.find((e) => e.id === id);
    logAudit("ai:audit", "Audit entry marked as reverted by the controller", {
      id, flight: entry?.flight, outcome: entry?.outcome,
    });
    logActivity("ai:audit", "Controller marked an entry reverted", { id });
    setUndoneIds(p => new Set([...p, id]));
    window.dispatchEvent(new CustomEvent("show-toast", { detail: "Marked as reverted. The original entry is kept: the log is append-only." }));
  };

  return (
    <div className="relative z-30">
      {/* Toggle button */}
      <button
        type="button"
        onClick={() => {
          logAudit("ai:audit", `AI LOG chrome ${isOpen ? "close" : "open"}`, { drawer: "audit-trail" });
          onToggle();
        }}
        className="flex items-center gap-2 px-4 py-2 rounded transition-all font-display text-[11px] tracking-widest"
        style={{
          background: isOpen ? 'rgba(0,229,204,0.12)' : 'var(--bg-panel-alt)',
          border: `1px solid ${isOpen ? 'var(--teal)' : 'var(--border-default)'}`,
          color: isOpen ? 'var(--teal)' : 'var(--text-muted)',
        }}
        title="AI Audit Trail"
      >
        <History className="w-3.5 h-3.5" />
        AI LOG
        {isOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {/* Drawer */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="absolute right-0 top-full mt-2 w-[420px] rounded-md shadow-2xl overflow-hidden"
            style={{
              background: 'var(--bg-panel-alt)',
              border: '1px solid var(--border-bright)',
              zIndex: 60,
            }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-default)' }}>
              <div className="flex items-center gap-2">
                <History className="w-4 h-4" style={{ color: 'var(--teal)' }} />
                <span className="font-display text-[12px] tracking-widest" style={{ color: 'var(--teal)' }}>AI AUDIT TRAIL</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-display text-[10px]" style={{ color: 'var(--text-muted)' }}>{total} recorded · server-side</span>
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--teal)' }} />
              </div>
            </div>

            {/* Log entries */}
            <div className="overflow-y-auto max-h-[280px] no-scrollbar">
              {entries.length === 0 && (
                <div className="px-4 py-4 font-body text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {error ? `Audit log unavailable: ${error}` : "No recorded actions yet."}
                </div>
              )}
              {entries.map((entry) => {
                const os = OUTCOME_STYLES[entry.outcome] || OUTCOME_STYLES.pending;
                const Icon = os.icon;
                const isUndone = undoneIds.has(entry.id);

                return (
                  <div
                    key={entry.id}
                    className="flex gap-3 px-4 py-3 transition-colors hover:bg-white/5"
                    style={{
                      borderBottom: '1px solid var(--border-default)',
                      opacity: isUndone ? 0.4 : 1,
                    }}
                  >
                    {/* Time + outcome dot */}
                    <div className="flex flex-col items-center gap-1 shrink-0">
                      <span className="font-display text-[11px] tabular-nums" style={{ color: 'var(--text-muted)' }}>{entry.time}</span>
                      <Icon className="w-3.5 h-3.5" style={{ color: os.color }} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <p className="font-body text-[12px] leading-snug" style={{ color: 'var(--text-secondary)' }}>
                        {entry.action}
                      </p>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="font-display text-[10px]" style={{ color: 'var(--text-muted)' }}>
                          {entry.flight}
                        </span>
                        <span className="font-display text-[10px]" style={{ color: os.color }}>
                          {os.label}{entry.by ? ` · ${entry.by}` : ''}
                        </span>
                        <span className="font-display text-[9px]" style={{ color: 'rgba(0,229,204,0.6)' }}>
                          conf {entry.confidence}
                        </span>
                      </div>
                    </div>

                    {/* Undo button (only for accepted/modified within this session) */}
                    {(entry.outcome === "accepted" || entry.outcome === "modified") && !isUndone && (
                      <button
                        onClick={() => handleUndo(entry.id)}
                        className="shrink-0 flex items-center gap-1 px-2 py-1 self-start rounded font-display text-[9px] tracking-widest transition-colors hover:bg-white/10"
                        style={{ border: '1px solid var(--border-default)', color: 'var(--text-muted)' }}
                        title="Mark this entry reverted. The log is append-only, so the original stays."
                      >
                        <RotateCcw className="w-2.5 h-2.5" />
                        UNDO
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Footer note */}
            <div className="px-4 py-2 font-body text-[10px]" style={{ background: 'rgba(0,229,204,0.04)', color: 'var(--text-muted)', borderTop: '1px solid var(--border-default)' }}>
Every suggestion and decision is written to the server-side append-only log. Nothing is ever
              edited or deleted, so "reverted" is recorded as a further entry rather than an erasure.
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
