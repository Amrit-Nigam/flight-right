import { runways } from "@/data/mockData";

const SLOT_STYLES = {
  land: { bg: "rgba(0,229,204,0.5)" },
  take: { bg: "rgba(245,166,35,0.5)" },
  clear: { bg: "transparent" },
  hold: { bg: "rgba(255,221,0,0.4)" },
  maint: { bg: "repeating-linear-gradient(45deg, rgba(255,45,45,0.3) 0px, rgba(255,45,45,0.3) 4px, transparent 4px, transparent 8px)", border: "1px solid #ff2d2d" },
};

export default function RunwayStatusPanel() {
  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <h3 className="font-display text-[11px] tracking-wider" style={{ color: 'var(--amber)' }}>⊞ RUNWAY STATUS</h3>
        <span className="font-display text-[8px]" style={{ color: 'var(--text-muted)' }}>Next 30 min</span>
      </div>

      <div className="p-3.5 space-y-2">
        {runways.map((rwy) => (
          <div key={rwy.id} className="flex items-center gap-2">
            <span className="w-16 font-display text-[9px] text-right shrink-0" style={{ color: 'var(--text-secondary)' }}>{rwy.id}</span>
            <div className="flex-1 h-5 relative overflow-hidden" style={{ background: 'var(--bg-raised)', border: '1px solid var(--border-default)' }}>
              {rwy.slots.map((slot, i) => {
                const s = SLOT_STYLES[slot.type] || SLOT_STYLES.clear;
                if (slot.type === "clear") return null;
                return (
                  <div
                    key={i}
                    className="absolute top-0 h-full flex items-center justify-center"
                    style={{
                      left: `${slot.pctStart}%`,
                      width: `${slot.pctW}%`,
                      background: slot.type === "maint" ? undefined : s.bg,
                      ...(slot.type === "maint" ? { backgroundImage: s.bg, border: s.border } : {}),
                    }}
                    title={slot.flight || slot.label || ""}
                  >
                    <span className="font-display text-[7px] truncate px-0.5" style={{
                      color: slot.type === "land" ? "#00e5cc" : slot.type === "take" ? "#f5a623" : slot.type === "maint" ? "#ff2d2d" : "var(--text-muted)"
                    }}>
                      {slot.flight || slot.label || ""}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {/* Legend */}
        <div className="flex items-center gap-3 mt-2 pt-2" style={{ borderTop: '1px solid var(--border-default)' }}>
          {[{ l: "Landing", c: "#00e5cc" }, { l: "Takeoff", c: "#f5a623" }, { l: "Clear", c: "rgba(255,255,255,0.1)" }, { l: "Maint.", c: "#ff2d2d" }].map((x) => (
            <div key={x.l} className="flex items-center gap-1">
              <span className="w-2 h-2" style={{ background: x.c }} />
              <span className="font-display text-[7px] uppercase" style={{ color: 'var(--text-muted)' }}>{x.l}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
