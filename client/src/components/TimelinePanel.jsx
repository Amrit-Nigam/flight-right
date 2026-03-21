import { timelineRows } from "@/data/mockData";

const TYPE_STYLES = {
  landing:   { bg: "rgba(0,230,118,0.15)", border: "rgba(0,230,118,0.5)",  text: "#00e676" },
  takeoff:   { bg: "rgba(0,200,255,0.12)",  border: "rgba(0,200,255,0.45)", text: "#00c8ff" },
  holding:   { bg: "rgba(255,170,0,0.12)",  border: "rgba(255,170,0,0.4)",  text: "#ffaa00" },
  cruise:    { bg: "rgba(168,85,247,0.10)", border: "rgba(168,85,247,0.4)", text: "#a855f7" },
  conflict:  { bg: "rgba(255,59,92,0.15)",  border: "rgba(255,59,92,0.5)",  text: "#ff3b5c" },
  optimized: { bg: "rgba(0,255,200,0.10)", border: "rgba(0,255,200,0.4)", text: "#00ffc8" },
};

const TOTAL_MINUTES = 120;
const NOW_MINUTE = 37; // ~14:37 UTC

export default function TimelinePanel() {
  const ticks = Array.from({ length: 25 }, (_, i) => i * 5);

  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 p-3 overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase">Flight Timeline</h3>
        <span className="text-[9px] font-mono text-atc-text-muted">13:00 — 15:00 UTC</span>
      </div>

      {/* Time axis */}
      <div className="relative ml-16">
        <div className="flex justify-between mb-1">
          {ticks.filter((_, i) => i % 3 === 0).map((t) => (
            <span key={t} className="text-[8px] font-mono text-atc-text-muted/50">
              {`${13 + Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`}
            </span>
          ))}
        </div>
      </div>

      {/* Rows */}
      <div className="space-y-1 relative">
        {/* NOW indicator */}
        <div
          className="absolute top-0 bottom-0 w-px bg-atc-danger/60 z-10"
          style={{ left: `calc(64px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)` }}
        />
        <div
          className="absolute -top-1 z-10 text-[7px] font-mono text-atc-danger"
          style={{ left: `calc(64px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)` }}
        >
          NOW
        </div>

        {timelineRows.map((row) => {
          const style = TYPE_STYLES[row.type] || TYPE_STYLES.cruise;
          const leftPct = (row.startMin / TOTAL_MINUTES) * 100;
          const widthPct = (row.durationMin / TOTAL_MINUTES) * 100;

          return (
            <div key={row.flight} className="flex items-center gap-0 h-6">
              <span className="w-16 text-[9px] font-mono font-bold text-atc-text-secondary shrink-0 text-right pr-2">
                {row.flight}
              </span>
              <div className="flex-1 relative h-5 rounded-sm bg-white/[0.02]">
                <div
                  className="absolute top-0 h-full rounded-sm flex items-center px-1.5 transition-all"
                  style={{
                    left: `${leftPct}%`,
                    width: `${widthPct}%`,
                    background: style.bg,
                    borderLeft: `2px solid ${style.border}`,
                  }}
                >
                  <span className="text-[8px] font-mono truncate" style={{ color: style.text }}>
                    {row.label}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
