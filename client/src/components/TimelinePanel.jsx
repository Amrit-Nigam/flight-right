import { timelineRows } from "@/data/mockData";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronUp, ChevronDown } from "lucide-react";

const TYPE_STYLES = {
  landing:   { bg: "rgba(0,229,204,0.15)", border: "var(--teal)", text: "var(--teal)" },
  takeoff:   { bg: "rgba(245,166,35,0.15)", border: "var(--amber)", text: "var(--amber)" },
  holding:   { bg: "rgba(255,221,0,0.15)", border: "var(--yellow)", text: "var(--yellow)" },
  cruise:    { bg: "rgba(107,101,95,0.15)", border: "var(--border-bright)", text: "var(--text-muted)" },
  conflict:  { bg: "rgba(255,45,45,0.15)", border: "var(--red)", text: "var(--red)" },
  optimized: { bg: "rgba(0,255,136,0.15)", border: "var(--green)", text: "var(--green)" },
};

const TOTAL_MINUTES = 120;
const NOW_MINUTE = 37;

export default function TimelinePanel({ isOpen, onToggle }) {
  const ticks = Array.from({ length: 25 }, (_, i) => i * 5);

  return (
    <div className="w-full shrink-0 flex flex-col items-center relative z-20">
      {/* TIMELINE TAB */}
      <button 
        onClick={onToggle}
        className="flex items-center gap-3 px-8 py-2 rounded-t-md transition-colors"
        style={{ 
          background: 'var(--bg-panel)', 
          border: '1px solid var(--border-default)', 
          borderBottom: 'none',
          boxShadow: '0 -4px 20px rgba(0,0,0,0.2)' 
        }}
        aria-label="Toggle Timeline"
      >
        <span className="font-display text-[12px] tracking-widest uppercase" style={{ color: 'var(--text-primary)' }}>
          System Timeline
        </span>
        {isOpen ? (
          <ChevronDown className="w-4 h-4" style={{ color: 'var(--amber)' }} />
        ) : (
          <ChevronUp className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
        )}
      </button>

      {/* TIMELINE DRAWER CONTENT */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="w-full overflow-hidden"
            style={{ 
              background: 'var(--bg-panel-alt)', 
              borderTop: '2px solid var(--amber)',
              boxShadow: '0 -10px 30px rgba(0,0,0,0.3)'
            }}
          >
            <div className="p-6">
              <div className="flex items-center justify-between mb-4 px-2">
                <h3 className="font-display text-[13px] tracking-widest" style={{ color: 'var(--text-secondary)' }}>
                  13:00 — 15:00 UTC
                </h3>
                <div className="flex items-center gap-4">
                  {['CRUISE', 'LANDING', 'TAKEOFF', 'HOLDING'].map(t => (
                    <div key={t} className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: TYPE_STYLES[t.toLowerCase()]?.border || 'var(--text-muted)' }} />
                      <span className="font-display text-[10px] uppercase" style={{ color: 'var(--text-muted)' }}>{t}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Time ticks header */}
              <div className="ml-[100px] mb-2 border-b" style={{ borderColor: 'var(--border-default)' }}>
                <div className="flex justify-between pb-1">
                  {ticks.filter((_, i) => i % 3 === 0).map((t) => (
                    <span key={t} className="font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      {`${13 + Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`}
                    </span>
                  ))}
                </div>
              </div>

              {/* Timeline Rows */}
              <div className="space-y-1 relative pt-2 pb-4">
                {/* NOW Line */}
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

                {timelineRows.map((row) => (
                  <div key={row.flight} className="flex items-center h-[32px] group hover:bg-white/5 transition-colors rounded">
                    <span className="w-[100px] font-display text-[13px] text-right pr-4 shrink-0 font-bold" style={{ color: 'var(--text-primary)' }}>
                      {row.flight}
                    </span>
                    <div className="flex-1 relative h-[20px] rounded-sm" style={{ background: 'var(--bg-base)' }}>
                      {row.bars.map((bar, bi) => {
                        const style = TYPE_STYLES[bar.type] || TYPE_STYLES.cruise;
                        const leftPct = (bar.startMin / TOTAL_MINUTES) * 100;
                        const widthPct = (bar.dur / TOTAL_MINUTES) * 100;
                        return (
                          <div
                            key={bi}
                            className={`absolute top-0 h-full flex items-center px-2 shadow-sm ${bar.type === 'conflict' ? 'animate-blink' : ''}`}
                            style={{ 
                              left: `${leftPct}%`, 
                              width: `${widthPct}%`, 
                              background: style.bg, 
                              borderLeft: `3px solid ${style.border}` 
                            }}
                          >
                            <span className="font-display text-[11px] truncate tracking-wider" style={{ color: style.text }}>
                              {bar.label}
                            </span>
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
