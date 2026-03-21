import { runways } from "@/data/mockData";
import { PlaneTakeoff } from "lucide-react";

const SLOT_STYLES = {
  land: { bg: "rgba(0,230,118,0.5)", border: "#00e676", text: "#00e676" },
  take: { bg: "rgba(0,200,255,0.5)", border: "#00c8ff", text: "#00c8ff" },
  clear: { bg: "rgba(255,255,255,0.03)", border: "rgba(255,255,255,0.06)", text: "transparent" },
  hold: { bg: "rgba(255,170,0,0.5)", border: "#ffaa00", text: "#ffaa00" },
  maint: { bg: "rgba(255,59,92,0.25)", border: "#ff3b5c", text: "#ff3b5c" },
};

export default function RunwayStatusPanel() {
  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 p-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase flex items-center gap-1.5">
          <PlaneTakeoff className="w-3 h-3 text-atc-cyan" />
          Runway Status
        </h3>
        <span className="text-[8px] font-mono text-atc-text-muted/60">Next 30 min</span>
      </div>

      <div className="space-y-2">
        {runways.map((rwy) => (
          <div key={rwy.id} className="flex items-center gap-2">
            <span className="w-16 text-[9px] font-mono text-atc-text-secondary shrink-0 text-right">
              {rwy.id}
            </span>
            <div className="flex-1 h-5 relative rounded-sm bg-white/[0.02] overflow-hidden">
              {rwy.slots.map((slot, i) => {
                const style = SLOT_STYLES[slot.type] || SLOT_STYLES.clear;
                return (
                  <div
                    key={i}
                    className="absolute top-0 h-full flex items-center justify-center group"
                    style={{
                      left: `${slot.startPct}%`,
                      width: `${slot.widthPct}%`,
                      background: style.bg,
                      borderLeft: slot.type !== "clear" ? `1px solid ${style.border}` : "none",
                      borderRight: slot.type !== "clear" ? `1px solid ${style.border}` : "none",
                    }}
                    title={slot.flight || slot.label || ""}
                  >
                    {slot.type !== "clear" && (
                      <span className="text-[7px] font-mono font-bold truncate px-0.5" style={{ color: style.text }}>
                        {slot.flight || slot.label || ""}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 pt-2 border-t border-atc-cyan/5">
        {[
          { label: "Landing", color: "#00e676" },
          { label: "Takeoff", color: "#00c8ff" },
          { label: "Clear", color: "rgba(255,255,255,0.15)" },
          { label: "Maint.", color: "#ff3b5c" },
        ].map((l) => (
          <div key={l.label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ background: l.color }} />
            <span className="text-[7px] font-mono text-atc-text-muted uppercase">{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
