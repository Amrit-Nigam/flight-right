import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { aiAuditLog } from "@/data/mockData";
import { History, ChevronDown, ChevronUp, RotateCcw, CheckCircle, XCircle, AlertCircle } from "lucide-react";

const OUTCOME_STYLES = {
  accepted: { color: "var(--green)",  icon: CheckCircle,   label: "Accepted" },
  rejected: { color: "var(--red)",    icon: XCircle,       label: "Rejected" },
  modified: { color: "var(--amber)",  icon: AlertCircle,   label: "Modified" },
  pending:  { color: "var(--teal)",   icon: AlertCircle,   label: "Pending" },
};

export default function AIAuditTrail({ isOpen, onToggle }) {
  const [undoneIds, setUndoneIds] = useState(new Set());

  const handleUndo = (idx) => {
    setUndoneIds(p => new Set([...p, idx]));
  };

  return (
    <div className="relative z-30">
      {/* Toggle button */}
      <button
        onClick={onToggle}
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
        {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
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
                <span className="font-display text-[10px]" style={{ color: 'var(--text-muted)' }}>Current session · {aiAuditLog.length} actions</span>
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--teal)' }} />
              </div>
            </div>

            {/* Log entries */}
            <div className="overflow-y-auto max-h-[280px] no-scrollbar">
              {aiAuditLog.map((entry, idx) => {
                const os = OUTCOME_STYLES[entry.outcome] || OUTCOME_STYLES.pending;
                const Icon = os.icon;
                const isUndone = undoneIds.has(idx);

                return (
                  <div
                    key={idx}
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
                        onClick={() => handleUndo(idx)}
                        className="shrink-0 flex items-center gap-1 px-2 py-1 self-start rounded font-display text-[9px] tracking-widest transition-colors hover:bg-white/10"
                        style={{ border: '1px solid var(--border-default)', color: 'var(--text-muted)' }}
                        title="Undo this AI action"
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
              All AI actions are logged for ATCO review. Undo reverts to pre-intervention state.
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
