import { optimization } from "@/data/mockData";
import { AreaChart, Area, ResponsiveContainer, Tooltip } from "recharts";
import { Cpu, TrendingUp } from "lucide-react";

const historyData = optimization.history.map((v, i) => ({
  time: `${-60 + i * 5}m`,
  score: v,
}));

export default function OptimizationPanel() {
  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 p-3">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase flex items-center gap-1.5">
          <Cpu className="w-3 h-3 text-atc-cyan" />
          System Optimization
        </h3>
      </div>

      {/* Overall score */}
      <div className="flex items-center gap-3 mb-4 p-3 rounded-md bg-atc-bg/60 border border-atc-cyan/10">
        <div className="relative w-14 h-14 shrink-0">
          <svg className="w-14 h-14 -rotate-90" viewBox="0 0 56 56">
            <circle cx="28" cy="28" r="24" fill="none" stroke="rgba(0,200,255,0.1)" strokeWidth="4" />
            <circle
              cx="28" cy="28" r="24" fill="none" stroke="#00c8ff" strokeWidth="4"
              strokeDasharray={`${(optimization.overall / 100) * 150.8} 150.8`}
              strokeLinecap="round"
              className="transition-all duration-1000"
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-sm font-mono font-bold text-atc-cyan">
            {optimization.overall}
          </span>
        </div>
        <div>
          <p className="text-xs font-semibold text-atc-text-primary">{optimization.label}</p>
          <p className="text-[9px] text-atc-text-muted">{optimization.description}</p>
          <p className="text-[9px] text-atc-success flex items-center gap-1 mt-0.5">
            <TrendingUp className="w-3 h-3" /> +15 pts in last hour
          </p>
        </div>
      </div>

      {/* Bars */}
      <div className="space-y-2 mb-4">
        {optimization.bars.map((bar) => (
          <div key={bar.label}>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[9px] text-atc-text-muted">{bar.label}</span>
              <span className="text-[9px] font-mono font-bold" style={{ color: bar.color }}>{bar.value}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full rounded-full animate-bar-fill"
                style={{ width: `${bar.value}%`, background: bar.color }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Sparkline */}
      <div className="rounded-md bg-atc-bg/60 border border-atc-cyan/5 p-2">
        <p className="text-[8px] text-atc-text-muted uppercase tracking-wider mb-1">Score — Last 60 min</p>
        <ResponsiveContainer width="100%" height={60}>
          <AreaChart data={historyData}>
            <defs>
              <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00c8ff" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#00c8ff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Tooltip
              contentStyle={{ background: "#0d1e33", border: "1px solid rgba(0,200,255,0.2)", fontSize: "10px", fontFamily: "Space Mono" }}
              labelStyle={{ color: "#7ba8c8" }}
              itemStyle={{ color: "#00c8ff" }}
            />
            <Area
              type="monotone"
              dataKey="score"
              stroke="#00c8ff"
              strokeWidth={1.5}
              fill="url(#scoreGrad)"
              dot={false}
              animationDuration={1500}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
