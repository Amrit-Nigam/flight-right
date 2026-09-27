import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";
import { logActivity, logAudit } from "@/lib/siteLogger";

export default function AISuggestionsPanel({ suggestions, onAccept, onDismiss, aiEnabled, acceptedCount }) {
  const [showMedium, setShowMedium] = useState(false);

  const critical = suggestions.filter(s => s.priority === 'CRITICAL');
  const high = suggestions.filter(s => s.priority === 'HIGH');
  const medium = suggestions.filter(s => s.priority === 'MEDIUM');

  const renderSuggestion = (s) => (
    <motion.div
      key={s.id}
      layout
      initial={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: "100%" }}
      className="p-3 mb-2 relative overflow-hidden group"
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        borderLeft: `4px solid ${s.typeColor}`,
      }}
    >
      {/* Background glow for critical */}
      {s.priority === 'CRITICAL' && (
        <div className="absolute inset-0 z-0 bg-red-500/5 animate-pulse" />
      )}
      
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="font-display text-[10px] uppercase tracking-wider px-2 py-0.5" style={{ borderWidth: '1px', borderStyle: 'solid', borderColor: s.typeColor, color: s.typeColor, background: `${s.typeColor}10` }}>
              {s.type}
            </span>
            <span className="font-display text-[10px] px-2 py-0.5" style={{
              color: s.priority === 'CRITICAL' ? 'var(--red)' : s.priority === 'HIGH' ? 'var(--amber)' : 'var(--text-muted)',
              borderBottom: `2px solid ${s.priority === 'CRITICAL' ? 'var(--red)' : s.priority === 'HIGH' ? 'var(--amber)' : 'var(--text-muted)'}`
            }}>
              {s.priority}
            </span>
          </div>
          <span className="font-display text-[10px]" style={{ color: 'var(--text-muted)' }}>{s.confidence}</span>
        </div>

        <div className="flex gap-1 mb-2">
          {s.flights.map((f) => (
            <span key={f} className="font-display text-[10px] px-2 py-0.5" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}>
              {f}
            </span>
          ))}
        </div>

        <p className="font-body text-[12px] leading-relaxed mb-3" style={{ color: 'var(--text-secondary)' }}>{s.text}</p>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              logAudit("ai:suggestions:ui", "ACCEPT control on suggestion card", { id: s.id, type: s.type });
              onAccept(s);
            }}
            className="flex-1 font-display text-[11px] py-1.5 transition-all hover:bg-white/5 bg-[rgba(0,255,136,0.05)] border border-[var(--green)] text-[var(--green)]"
          >
            ✓ ACCEPT
          </button>
          <button
            type="button"
            onClick={() => {
              logAudit("ai:suggestions:ui", "DISMISS control on suggestion card", { id: s.id, type: s.type });
              onDismiss(s.id);
            }}
            className="flex-1 font-display text-[11px] py-1.5 transition-all hover:bg-white/5 border border-[var(--border-default)] text-[var(--text-muted)]"
          >
            ✕ DISMISS
          </button>
        </div>
      </div>
    </motion.div>
  );

  return (
    // shrink-0, not h-full: this panel sits in the scrolling right-hand column, where h-full let the
    // column squash it to 2 px at every screen size (found in the 27 Sep demo run). Capped so a long
    // queue scrolls inside the panel.
    <div className="panel flex flex-col shrink-0 max-h-[560px] relative overflow-hidden">
      <div className="panel-header py-3 px-4 flex items-center justify-between gap-3">
        <h3 className="font-display text-[13px] tracking-widest text-[var(--amber)]">
          ✦ AI suggestions queue
        </h3>
        {acceptedCount > 0 && (
          <span className="font-display text-[10px] text-[var(--green)] px-2 border border-[var(--green)] bg-[rgba(0,255,136,0.1)] shrink-0">
            {acceptedCount} RESOLVED
          </span>
        )}
      </div>
      <p className="font-body text-[11px] text-[var(--text-muted)] leading-snug px-4 py-2 border-b border-[var(--border-default)] bg-[var(--bg-base)]">
        Proposed actions only — review each suggestion before accepting. Nothing here applies to live traffic.
      </p>

      {!aiEnabled && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-[var(--bg-base)] bg-opacity-95 backdrop-blur-sm">
          <span className="text-[24px] mb-2 opacity-50">✦</span>
          <p className="font-display text-[14px] tracking-wider text-[var(--text-muted)]">AI SYSTEM DISENGAGED</p>
        </div>
      )}

      {/* PINNED CRITICAL SECTION */}
      {critical.length > 0 && (
        <div className="p-3 border-b-2 border-[var(--red)] bg-[rgba(255,45,45,0.03)] shrink-0 shadow-sm relative z-20">
          <div className="flex items-center gap-2 mb-2 px-1">
            <span className="w-2 h-2 rounded-full bg-[var(--red)] animate-blink" />
            <span className="font-display text-[11px] uppercase tracking-widest text-[var(--red)] font-bold">CRITICAL ACTION REQUIRED</span>
          </div>
          <AnimatePresence>
            {critical.map(renderSuggestion)}
          </AnimatePresence>
        </div>
      )}

      {/* SCROLLABLE HIGH & MEDIUM SECTION */}
      <div className="flex-1 overflow-y-auto p-3 relative z-10 w-full no-scrollbar">
        <AnimatePresence>
          {high.map(renderSuggestion)}
        </AnimatePresence>

        {medium.length > 0 && (
          <div className="mt-4 border-t border-[var(--border-default)] pt-4 pb-4">
            <button 
              onClick={() =>
                setShowMedium((v) => {
                  const next = !v;
                  logAudit("ai:suggestions:ui", "Medium-priority queue disclosure toggled", {
                    expanded: next,
                    count: medium.length,
                  });
                  logActivity("ai:suggestions", `Medium-priority queue ${next ? "expanded" : "collapsed"}`, {
                    count: medium.length,
                  });
                  return next;
                })
              }
              className="w-full flex items-center justify-between px-3 py-2 border border-[var(--border-default)] bg-[var(--bg-raised)] transition-colors hover:bg-white/5"
            >
              <span className="font-display text-[11px] text-[var(--text-muted)] tracking-widest">
                MEDIUM PRIORITY WAITING
              </span>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 text-[10px] bg-[var(--bg-panel)] border border-[var(--border-default)] text-[var(--text-primary)]">
                  {medium.length}
                </span>
                {showMedium ? <ChevronUp className="w-3 h-3 text-[var(--text-muted)]" /> : <ChevronDown className="w-3 h-3 text-[var(--text-muted)]" />}
              </div>
            </button>
            <AnimatePresence>
              {showMedium && (
                <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden mt-3">
                  {medium.map(renderSuggestion)}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {suggestions.length === 0 && (
          <div className="flex items-center justify-center py-10 opacity-50">
            <p className="font-display text-[11px] tracking-widest text-[var(--text-muted)]">— NO PENDING ACTIONS —</p>
          </div>
        )}
      </div>
    </div>
  );
}
