import { logAudit } from "@/lib/siteLogger";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronUp, ChevronDown } from "lucide-react";

// Predicted closest approaches on a time axis anchored to the time the picture describes.
//
// Rewritten 27 Sep 2026. The old panel had a fixed "13:00 — 15:00 UTC" axis with "now" at
// minute 37 of 120, and placed each bar at "minutes from now" measured from the axis START --
// so every predicted closest approach was drawn about half an hour in the past. Its legend and
// tooltips offered "AI RESEQ", "Undo resequence" and "Expected exit hold", none of which any part
// of the system produces. Now: the axis runs from 1 min before to 11 min after the data time,
// the shaded zone is the models' real 10-minute look-ahead, and each mark is a pair's predicted
// closest approach, as wide as the 15 s prediction grid.

const BEFORE_MIN = 1;
const AFTER_MIN = 11;
const SPAN = BEFORE_MIN + AFTER_MIN;
const pct = (minutesFromNow) => ((minutesFromNow + BEFORE_MIN) / SPAN) * 100;

const TYPE_STYLES = {
  conflict: { bg: "rgba(255,45,45,0.18)", border: "var(--red)", text: "var(--red)", label: "Alarm (tier 1, 0–3 min)" },
  holding: { bg: "rgba(255,221,0,0.15)", border: "var(--yellow)", text: "var(--yellow)", label: "Watch list (tier 2, 3–10 min)" },
};

export default function TimelinePanel({ isOpen, onToggle, rows = [], dataTimeUtc = null, lookAheadSeconds = null }) {
  const now = dataTimeUtc ? Date.parse(dataTimeUtc) : null;
  const lookAheadMin = (lookAheadSeconds ?? 600) / 60;
  const ticks = Array.from({ length: SPAN / 2 + 1 }, (_, i) => -BEFORE_MIN + i * 2);
  const tickLabel = (m) => (now ? new Date(now + m * 60000).toISOString().slice(11, 16) : `${m >= 0 ? "+" : ""}${m} min`);

  return (
    <div className="w-full shrink-0 flex flex-col items-center relative" style={{ zIndex: 50 }}>
      <button
        type="button"
        onClick={() => { logAudit("timeline:panel", `System timeline tab ${isOpen ? "collapse" : "expand"} requested`); onToggle(); }}
        className="flex items-center gap-3 px-8 py-2 rounded-t-md transition-colors"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border-default)", borderBottom: "none", boxShadow: "0 -4px 20px rgba(0,0,0,0.2)" }}
        aria-label="Toggle Timeline"
      >
        <span className="font-display text-[12px] tracking-widest uppercase" style={{ color: "var(--text-primary)" }}>System Timeline</span>
        {isOpen ? <ChevronDown className="w-4 h-4" style={{ color: "var(--amber)" }} /> : <ChevronUp className="w-4 h-4" style={{ color: "var(--text-muted)" }} />}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                      transition={{ type: "spring", stiffness: 300, damping: 30 }} className="w-full"
                      style={{ background: "var(--bg-panel-alt)", borderTop: "2px solid var(--amber)", boxShadow: "0 -10px 30px rgba(0,0,0,0.3)" }}>
            <div className="p-6">
              <div className="flex items-center justify-between mb-4 px-2">
                <h3 className="font-display text-[13px] tracking-widest" style={{ color: "var(--text-secondary)" }}>
                  PREDICTED CLOSEST APPROACHES · {now ? `${tickLabel(-BEFORE_MIN)} — ${tickLabel(AFTER_MIN)} UTC` : "waiting for data time"}
                </h3>
                <div className="flex items-center gap-4">
                  {Object.values(TYPE_STYLES).map((t) => (
                    <div key={t.label} className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: t.border }} />
                      <span className="font-display text-[9px] uppercase" style={{ color: "var(--text-muted)" }}>{t.label}</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-1.5 ml-2 pl-2" style={{ borderLeft: "1px solid var(--border-default)" }}>
                    <span className="w-2 h-2" style={{ border: "2px solid var(--teal)", borderRadius: 1 }} />
                    <span className="font-display text-[9px] uppercase" style={{ color: "var(--teal)" }}>Manoeuvres offered</span>
                  </div>
                </div>
              </div>

              <div className="ml-[160px] mb-2 border-b relative h-5" style={{ borderColor: "var(--border-default)" }}>
                {ticks.map((m) => (
                  <span key={m} className="absolute font-display text-[11px]" style={{ left: `${pct(m)}%`, transform: "translateX(-50%)", color: "var(--text-muted)" }}>
                    {tickLabel(m)}
                  </span>
                ))}
              </div>

              <div className="space-y-1 relative pt-2 pb-4">
                <div className="absolute top-0 bottom-0 z-10" style={{ left: `calc(160px + (100% - 160px) * ${pct(0) / 100})`, width: "1px", background: "var(--red)", opacity: 0.8 }} />
                <div className="absolute -top-3 z-10 font-display text-[10px] px-1" style={{ left: `calc(160px + (100% - 160px) * ${pct(0) / 100})`, color: "#fff", background: "var(--red)", transform: "translateX(-50%)" }}>
                  NOW
                </div>
                <div className="absolute top-0 bottom-0 pointer-events-none"
                     style={{ left: `calc(160px + (100% - 160px) * ${pct(0) / 100})`, width: `calc((100% - 160px) * ${lookAheadMin / SPAN})`,
                              background: "rgba(0,229,204,0.04)", borderLeft: "1px dashed rgba(0,229,204,0.3)", borderRight: "1px dashed rgba(0,229,204,0.3)", zIndex: 2 }}>
                  <span className="absolute top-1 left-1 font-display text-[9px] tracking-widest" style={{ color: "rgba(0,229,204,0.6)", whiteSpace: "nowrap" }}>
                    {Math.round(lookAheadMin)}-MIN PREDICTION WINDOW
                  </span>
                </div>

                {rows.length === 0 && (
                  <div className="px-3 py-4 font-body text-[11px]" style={{ color: "var(--text-muted)" }}>
                    No predicted closest approaches inside the ten-minute look-ahead.
                  </div>
                )}
                {rows.map((row) => (
                  <div key={row.flight} className="flex items-center h-[32px] rounded"
                       style={{ borderLeft: row.aiManaged ? "3px solid rgba(0,229,204,0.5)" : "3px solid transparent" }}>
                    <span className="w-[157px] font-display text-[12px] text-right pr-4 shrink-0" style={{ color: "var(--text-primary)" }}>{row.flight}</span>
                    <div className="flex-1 relative h-[20px] rounded-sm" style={{ background: "var(--bg-base)" }}>
                      {row.bars.map((bar, bi) => {
                        const style = TYPE_STYLES[bar.type] || TYPE_STYLES.holding;
                        return (
                          <div key={bi} className={`absolute top-0 h-full ${bar.type === "conflict" ? "animate-blink" : ""}`}
                               title={bar.label}
                               style={{ left: `${pct(bar.startMin)}%`, width: `max(4px, ${(bar.dur / SPAN) * 100}%)`, background: style.border }}>
                            <span className="absolute left-2 top-0 font-display text-[11px] whitespace-nowrap tracking-wider" style={{ color: style.text, transform: "translateX(6px)" }}>
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
