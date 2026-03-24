import { useState, useRef } from "react";
import { timelineRows } from "@/data/mockData";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronUp, ChevronDown, RotateCcw } from "lucide-react";

const TYPE_STYLES = {
  landing:   { bg: "rgba(0,229,204,0.15)",  border: "var(--teal)",         text: "var(--teal)" },
  takeoff:   { bg: "rgba(245,166,35,0.15)", border: "var(--amber)",        text: "var(--amber)" },
  holding:   { bg: "rgba(255,221,0,0.15)",  border: "var(--yellow)",       text: "var(--yellow)" },
  cruise:    { bg: "rgba(107,101,95,0.15)", border: "var(--border-bright)", text: "var(--text-muted)" },
  conflict:  { bg: "rgba(255,45,45,0.15)",  border: "var(--red)",          text: "var(--red)" },
  optimized: { bg: "rgba(0,255,136,0.15)",  border: "var(--green)",        text: "var(--green)" },
};

const TOTAL_MINUTES = 120;
const NOW_MINUTE    = 37;
const LOOKAHEAD_MIN = 15; // AI predictive zone width

// ── Tooltip component ──────────────────────────────────────────────────────
function BarTooltip({ bar, onUndo, anchorRef }) {
  if (!bar.xaiDetail && !bar.holdExit) return null;
  return (
    <div
      className="absolute bottom-full mb-2 left-0 w-64 p-3 rounded-md shadow-2xl"
      style={{
        zIndex: 9999,
        background: 'var(--bg-panel-alt)',
        border: '1px solid var(--border-bright)',
        color: 'var(--text-secondary)',
        fontSize: 11,
        lineHeight: 1.6,
        pointerEvents: 'auto',
      }}
    >
      {bar.xaiDetail && (
        <>
          <p className="font-display text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--green)' }}>AI Action — Explanation</p>
          <p style={{ color: 'var(--text-secondary)' }}>{bar.xaiDetail}</p>
          <button
            onClick={() => {
              onUndo();
              window.dispatchEvent(new CustomEvent("show-toast", { detail: "Resequence reverted to manual." }));
            }}
            className="mt-2 flex items-center gap-1 font-display text-[10px] tracking-widest px-2 py-1 rounded transition-colors hover:bg-white/10 active:scale-95"
            style={{ border: '1px solid var(--red)', color: 'var(--red)', background: 'rgba(255,45,45,0.08)' }}
          >
            <RotateCcw className="w-3 h-3" /> Undo resequence
          </button>
        </>
      )}
      {bar.holdExit && !bar.xaiDetail && (
        <>
          <p className="font-display text-[10px] uppercase tracking-widest mb-1" style={{ color: 'var(--yellow)' }}>Hold Estimate</p>
          <p>Expected exit hold at <strong style={{ color: 'var(--text-primary)' }}>{bar.holdExit}</strong> UTC based on current traffic flow.</p>
        </>
      )}
    </div>
  );
}

export default function TimelinePanel({ isOpen, onToggle }) {
  const ticks = Array.from({ length: 25 }, (_, i) => i * 5);
  const [tooltip, setTooltip] = useState(null); // { rowFlight, barIndex }

  return (
    <div className="w-full shrink-0 flex flex-col items-center relative" style={{ zIndex: 50 }}>
      {/* Timeline Tab button */}
      <button
        onClick={onToggle}
        className="flex items-center gap-3 px-8 py-2 rounded-t-md transition-colors"
        style={{
          background: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderBottom: 'none',
          boxShadow: '0 -4px 20px rgba(0,0,0,0.2)',
        }}
        aria-label="Toggle Timeline"
      >
        <span className="font-display text-[12px] tracking-widest uppercase" style={{ color: 'var(--text-primary)' }}>
          System Timeline
        </span>
        {isOpen
          ? <ChevronDown className="w-4 h-4" style={{ color: 'var(--amber)' }} />
          : <ChevronUp   className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="w-full"
            style={{
              background: 'var(--bg-panel-alt)',
              borderTop: '2px solid var(--amber)',
              boxShadow: '0 -10px 30px rgba(0,0,0,0.3)',
            }}
          >
            <div className="p-6">
              {/* Header row */}
              <div className="flex items-center justify-between mb-4 px-2">
                <h3 className="font-display text-[13px] tracking-widest" style={{ color: 'var(--text-secondary)' }}>
                  13:00 — 15:00 UTC
                </h3>
                <div className="flex items-center gap-4">
                  {/* Legend */}
                  {['CRUISE','LANDING','TAKEOFF','HOLDING','CONFLICT','AI RESEQ'].map(t => (
                    <div key={t} className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: TYPE_STYLES[t.toLowerCase().replace(' reseq','').replace('ai ','optimized').replace('ai','optimized')]?.border || TYPE_STYLES[t === 'AI RESEQ' ? 'optimized' : t.toLowerCase()]?.border || 'var(--text-muted)' }} />
                      <span className="font-display text-[9px] uppercase" style={{ color: 'var(--text-muted)' }}>{t}</span>
                    </div>
                  ))}
                  {/* AI managed vs controller legend */}
                  <div className="flex items-center gap-1.5 ml-2 pl-2" style={{ borderLeft: '1px solid var(--border-default)' }}>
                    <span className="w-2 h-2" style={{ border: '2px solid var(--teal)', borderRadius: 1 }} />
                    <span className="font-display text-[9px] uppercase" style={{ color: 'var(--teal)' }}>AI Managed</span>
                  </div>
                </div>
              </div>

              {/* Time ticks */}
              <div className="ml-[100px] mb-2 border-b" style={{ borderColor: 'var(--border-default)' }}>
                <div className="flex justify-between pb-1">
                  {ticks.filter((_, i) => i % 3 === 0).map(t => (
                    <span key={t} className="font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      {`${13 + Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`}
                    </span>
                  ))}
                </div>
              </div>

              {/* Rows */}
              <div className="space-y-1 relative pt-2 pb-4">
                {/* NOW line */}
                <div
                  className="absolute top-0 bottom-0 z-10"
                  style={{ left: `calc(100px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)`, width: '1px', background: 'var(--red)', opacity: 0.8 }}
                />
                <div
                  className="absolute -top-3 z-10 font-display text-[10px] px-1 animate-pulse"
                  style={{ left: `calc(100px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)`, color: '#fff', background: 'var(--red)', transform: 'translateX(-50%)' }}
                >
                  NOW
                </div>

                {/* AI Predictive lookahead zone (NOW → NOW+15min) */}
                <div
                  className="absolute top-0 bottom-0 pointer-events-none"
                  style={{
                    left:  `calc(100px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)`,
                    width: `${(LOOKAHEAD_MIN / TOTAL_MINUTES) * 100}%`,
                    background: 'rgba(0,229,204,0.04)',
                    borderLeft: '1px dashed rgba(0,229,204,0.3)',
                    borderRight: '1px dashed rgba(0,229,204,0.2)',
                    zIndex: 2,
                  }}
                >
                  <span
                    className="absolute top-1 left-1 font-display text-[9px] tracking-widest"
                    style={{ color: 'rgba(0,229,204,0.45)', whiteSpace: 'nowrap' }}
                  >
                    AI PREDICTED +15 MIN
                  </span>
                </div>

                {timelineRows.map((row) => (
                  <div
                    key={row.flight}
                    className="flex items-center h-[32px] group hover:bg-white/5 transition-colors rounded"
                    style={{
                      // AI-managed rows: dim teal left border + faint teal bg tint
                      borderLeft: row.aiManaged ? '3px solid rgba(0,229,204,0.5)' : '3px solid transparent',
                      background: row.aiManaged ? 'rgba(0,229,204,0.03)' : 'transparent',
                    }}
                  >
                    <span
                      className="w-[100px] font-display text-[13px] text-right pr-4 shrink-0"
                      style={{
                        color: row.aiManaged ? 'rgba(0,229,204,0.75)' : 'var(--text-primary)',
                        fontWeight: row.aiManaged ? 400 : 700,
                      }}
                    >
                      {row.flight}
                    </span>

                    <div className="flex-1 relative h-[20px] rounded-sm" style={{ background: 'var(--bg-base)' }}>
                      {row.bars.map((bar, bi) => {
                        const style    = TYPE_STYLES[bar.type] || TYPE_STYLES.cruise;
                        const leftPct  = (bar.startMin / TOTAL_MINUTES) * 100;
                        const widthPct = (bar.dur / TOTAL_MINUTES) * 100;
                        const tooltipKey = `${row.flight}-${bi}`;
                        const showTip = tooltip === tooltipKey;
                        const hasTooltip = !!(bar.xaiDetail || bar.holdExit);

                        // In the predictive zone?
                        const inAiZone = bar.startMin >= NOW_MINUTE && bar.startMin < NOW_MINUTE + LOOKAHEAD_MIN;

                        return (
                          <div
                            key={bi}
                            className={`absolute top-0 h-full flex items-center px-2 shadow-sm transition-opacity ${bar.type === 'conflict' ? 'animate-blink' : ''}`}
                            style={{
                              left: `${leftPct}%`,
                              width: `${widthPct}%`,
                              background: style.bg,
                              borderLeft: `3px solid ${style.border}`,
                              // AI predicted zone gets dashed border
                              outline: inAiZone ? `1px dashed ${style.border}` : 'none',
                              cursor: hasTooltip ? 'pointer' : 'default',
                              position: 'absolute',
                              zIndex: showTip ? 999 : 1,
                            }}
                            onMouseEnter={() => hasTooltip && setTooltip(tooltipKey)}
                            onMouseLeave={() => setTooltip(null)}
                          >
                            <span className="font-display text-[11px] truncate tracking-wider" style={{ color: style.text }}>
                              {bar.label}
                            </span>

                            {/* Hover tooltip */}
                            {showTip && (
                              <BarTooltip bar={bar} onUndo={() => setTooltip(null)} />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
