import { timelineRows } from "@/data/mockData";

const TYPE_STYLES = {
  landing:   { bg: "rgba(0,229,204,0.25)", border: "#00e5cc", text: "#00e5cc" },
  takeoff:   { bg: "rgba(245,166,35,0.2)", border: "#f5a623", text: "#f5a623" },
  holding:   { bg: "rgba(255,221,0,0.15)", border: "#ffdd00", text: "#ffdd00" },
  cruise:    { bg: "rgba(138,125,101,0.12)", border: "rgba(138,125,101,0.4)", text: "#8a7d65" },
  conflict:  { bg: "rgba(255,45,45,0.2)", border: "#ff2d2d", text: "#ff2d2d" },
  optimized: { bg: "rgba(0,255,136,0.12)", border: "#00ff88", text: "#00ff88" },
};

const TOTAL_MINUTES = 120;
const NOW_MINUTE = 37;

export default function TimelinePanel() {
  const ticks = Array.from({ length: 25 }, (_, i) => i * 5);

  return (
    <div className="panel p-4 overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display text-[12px] tracking-wider" style={{ color: 'var(--text-muted)' }}>FLIGHT TIMELINE</h3>
        <span className="font-display text-[11px]" style={{ color: 'var(--text-muted)' }}>13:00 — 15:00 UTC</span>
      </div>

      {/* Time ticks */}
      <div className="ml-20">
        <div className="flex justify-between mb-1">
          {ticks.filter((_, i) => i % 3 === 0).map((t) => (
            <span key={t} className="font-display text-[10px]" style={{ color: 'var(--text-muted)' }}>
              {`${13 + Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`}
            </span>
          ))}
        </div>
      </div>

      {/* Rows */}
      <div className="space-y-0.5 relative">
        <div className="absolute top-0 bottom-0 z-10" style={{ left: `calc(80px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)`, width: '2px', background: 'var(--red)', opacity: 0.9 }} />
        <div className="absolute -top-3 z-10 font-display text-[9px]" style={{ left: `calc(80px + ${(NOW_MINUTE / TOTAL_MINUTES) * 100}%)`, color: 'var(--red)' }}>NOW</div>

        {timelineRows.map((row) => (
          <div key={row.flight} className="flex items-center h-[28px]">
            <span className="w-20 font-display text-[11px] text-right pr-3 shrink-0" style={{ color: 'var(--amber)' }}>{row.flight}</span>
            <div className="flex-1 relative h-[18px] rounded-sm" style={{ background: 'var(--bg-raised)' }}>
              {row.bars.map((bar, bi) => {
                const style = TYPE_STYLES[bar.type] || TYPE_STYLES.cruise;
                const leftPct = (bar.startMin / TOTAL_MINUTES) * 100;
                const widthPct = (bar.dur / TOTAL_MINUTES) * 100;
                return (
                  <div
                    key={bi}
                    className={`absolute top-0 h-full flex items-center px-1.5 rounded-sm ${bar.type === 'conflict' ? 'animate-blink' : ''}`}
                    style={{ left: `${leftPct}%`, width: `${widthPct}%`, background: style.bg, borderLeft: `2px solid ${style.border}` }}
                  >
                    <span className="font-display text-[10px] truncate" style={{ color: style.text }}>{bar.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
