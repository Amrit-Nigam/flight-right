import { useState } from "react";
import { aiSuggestions } from "@/data/mockData";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Brain, Check, X, AlertTriangle, Sparkles, CloudRain, ArrowUpDown } from "lucide-react";

const TYPE_CONFIG = {
  CONFLICT: { icon: AlertTriangle, color: "#ff3b5c" },
  OPTIMIZE: { icon: Sparkles, color: "#00ffc8" },
  WEATHER: { icon: CloudRain, color: "#ffaa00" },
  SEQUENCE: { icon: ArrowUpDown, color: "#00c8ff" },
};

const PRIORITY_STYLES = {
  CRITICAL: "bg-atc-danger/10 text-atc-danger border-atc-danger/30",
  HIGH: "bg-atc-orange/10 text-atc-orange border-atc-orange/30",
  MEDIUM: "bg-atc-warning/10 text-atc-warning border-atc-warning/30",
  LOW: "bg-atc-text-muted/10 text-atc-text-muted border-atc-text-muted/30",
};

export default function AISuggestionsPanel() {
  const [items, setItems] = useState(aiSuggestions);
  const [accepted, setAccepted] = useState(new Set());

  const handleAccept = (id) => {
    setAccepted((prev) => new Set([...prev, id]));
  };

  const handleDismiss = (id) => {
    setItems((prev) => prev.filter((s) => s.id !== id));
  };

  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 flex flex-col">
      <div className="p-3 border-b border-atc-cyan/10">
        <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase flex items-center gap-1.5">
          <Brain className="w-3 h-3 text-atc-purple" />
          AI Recommendations
        </h3>
      </div>

      <ScrollArea className="flex-1 max-h-[400px]">
        <div className="p-2 space-y-2">
          {items.map((s) => {
            const cfg = TYPE_CONFIG[s.type] || TYPE_CONFIG.OPTIMIZE;
            const Icon = cfg.icon;
            const isAccepted = accepted.has(s.id);

            return (
              <div
                key={s.id}
                className={`rounded-md border p-3 transition-all ${
                  isAccepted
                    ? "border-atc-success/30 bg-atc-success/5"
                    : "border-white/5 bg-white/[0.02] hover:bg-white/[0.04]"
                }`}
                style={{ borderLeftColor: cfg.color, borderLeftWidth: "3px" }}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <Icon className="w-3.5 h-3.5" style={{ color: cfg.color }} />
                    <span className="text-[9px] font-mono font-bold tracking-wider" style={{ color: cfg.color }}>
                      {s.type}
                    </span>
                    <span className={`text-[8px] font-mono px-1 py-0.5 rounded border ${PRIORITY_STYLES[s.priority]}`}>
                      {s.priority}
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-atc-text-muted">{s.confidence}</span>
                </div>

                {/* Flight refs */}
                <div className="flex items-center gap-1 mb-1.5">
                  {s.flightRefs.map((f) => (
                    <span key={f} className="text-[8px] font-mono px-1.5 py-0.5 rounded bg-atc-cyan/10 text-atc-cyan border border-atc-cyan/15">
                      {f}
                    </span>
                  ))}
                </div>

                {/* Text */}
                <p className="text-[10px] text-atc-text-secondary leading-relaxed mb-2">{s.text}</p>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  {isAccepted ? (
                    <span className="text-[9px] font-mono text-atc-success flex items-center gap-1">
                      <Check className="w-3 h-3" /> APPLIED
                    </span>
                  ) : (
                    <>
                      <button
                        onClick={() => handleAccept(s.id)}
                        className="flex items-center gap-1 px-2 py-1 text-[9px] font-mono tracking-wider rounded bg-atc-success/10 text-atc-success border border-atc-success/20 hover:bg-atc-success/20 transition-colors"
                      >
                        <Check className="w-3 h-3" /> ACCEPT
                      </button>
                      <button
                        onClick={() => handleDismiss(s.id)}
                        className="flex items-center gap-1 px-2 py-1 text-[9px] font-mono tracking-wider rounded bg-white/5 text-atc-text-muted border border-white/5 hover:bg-white/10 transition-colors"
                      >
                        <X className="w-3 h-3" /> DISMISS
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
