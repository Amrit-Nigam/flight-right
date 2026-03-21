import { weather } from "@/data/mockData";
import { Cloud, Wind, Eye, Thermometer, Gauge, PlaneLanding } from "lucide-react";

const ICONS = {
  Wind: Wind,
  Visibility: Eye,
  Ceiling: Cloud,
  Temperature: Thermometer,
  QNH: Gauge,
  "Active Rwy": PlaneLanding,
};

export default function WeatherPanel() {
  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 p-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase flex items-center gap-1.5">
          <Cloud className="w-3 h-3 text-atc-cyan" />
          Weather / ATIS
        </h3>
        <span className="text-[9px] font-mono text-atc-gold px-1.5 py-0.5 rounded bg-atc-gold/10 border border-atc-gold/20">
          ATIS {weather.atisLetter}
        </span>
      </div>

      {/* METAR */}
      <div className="rounded-md bg-atc-bg/60 border border-atc-cyan/5 p-2 mb-3">
        <p className="text-[8px] text-atc-text-muted uppercase tracking-wider mb-0.5">METAR</p>
        <p className="text-[9px] font-mono text-atc-cyan/70 leading-relaxed break-all">{weather.metar}</p>
      </div>

      {/* Conditions */}
      <div className="space-y-1.5">
        {weather.conditions.map((c) => {
          const Icon = ICONS[c.label] || Cloud;
          return (
            <div key={c.label} className="flex items-start gap-2 p-1.5 rounded-md hover:bg-white/[0.02] transition-colors">
              <Icon className="w-3 h-3 text-atc-cyan/50 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] text-atc-text-muted uppercase tracking-wider">{c.label}</span>
                  <span className="text-[10px] font-mono text-atc-text-primary font-medium">{c.value}</span>
                </div>
                <p className="text-[8px] text-atc-text-muted/60 mt-0.5">{c.sub}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Trend + Safety */}
      <div className="mt-3 pt-2 border-t border-atc-cyan/5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[8px] text-atc-text-muted uppercase">Trend:</span>
          <span className="text-[9px] font-mono text-atc-success">{weather.trend}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[8px] font-mono text-atc-text-muted">
            WS: <span className={weather.windShearAlert ? "text-atc-danger" : "text-atc-success"}>{weather.windShearAlert ? "ALERT" : "NIL"}</span>
          </span>
          <span className="text-[8px] font-mono text-atc-text-muted">
            TURB: <span className="text-atc-success">{weather.turbulenceLevel}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
