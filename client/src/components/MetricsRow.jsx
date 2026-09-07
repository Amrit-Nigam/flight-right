import { useEffect, useState } from "react";
import { motion } from "framer-motion";

const COLOR_MAP = {
  amber: "var(--amber)", green: "var(--green)", red: "var(--red)",
  teal: "var(--teal)", text_primary: "var(--text-primary)", yellow: "var(--yellow)",
};

function useCountUp(target, duration = 1200) {
  const [value, setValue] = useState(0);
  const numTarget = parseFloat(target);
  const isNum = !isNaN(numTarget);
  useEffect(() => {
    if (!isNum) { setValue(target); return; }
    const startTime = performance.now();
    const step = (now) => {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(eased * numTarget * 10) / 10);
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [numTarget, duration, isNum, target]);
  return value;
}

function MetricCard({ metric, index }) {
  const displayVal = useCountUp(metric.value);
  const color = COLOR_MAP[metric.valueColor] || "var(--amber)";
  const formatValue = () => {
    const raw = metric.value.toString();
    if (raw.includes("%")) return `${displayVal}%`;
    if (raw.includes("kt")) return `${displayVal} kt`;
    if (raw.includes("km")) return `${displayVal} km`;
    if (raw.includes("m")) return `${displayVal}m`;
    return displayVal;
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: index * 0.1, duration: 0.4, type: "spring" }}
      className={`p-6 flex flex-col items-center justify-center text-center relative overflow-hidden group ${metric.pulse ? 'animate-blink' : ''}`}
      style={{
        background: 'var(--bg-panel-alt)',
        border: '1px solid var(--border-default)',
        borderRadius: '6px',
      }}
    >
      {/* Background Glow */}
      <div 
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-2xl"
        style={{ background: `radial-gradient(circle at center, ${color}30 0%, transparent 70%)` }}
      />
      
      <p 
        className="font-display text-[36px] tracking-tight leading-none mb-2 relative z-10" 
        style={{ color, textShadow: `0 0 12px ${color}28` }}
      >
        {formatValue()}
      </p>
      <p 
        className="font-body text-[10px] uppercase tracking-widest relative z-10" 
        style={{ color: 'var(--text-muted)' }}
      >
        {metric.label}
      </p>
    </motion.div>
  );
}

export default function MetricsRow({ metricsData }) {
  // Take only the top 4 for the 2x2 mission-critical readout
  const top4 = metricsData.slice(0, 4);
  
  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4 px-1">
        <div>
          <h3 className="font-display text-[13px] tracking-widest" style={{ color: 'var(--text-primary)' }}>
            Sector metrics
          </h3>
          <p className="font-body text-[10px] text-[var(--text-muted)] mt-0.5">Live from the detection chain · recomputed every update</p>
        </div>
        <span className="w-2 h-2 rounded-full animate-pulse-dot" style={{ background: 'var(--green)', boxShadow: '0 0 8px var(--green)' }} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        {top4.map((m, i) => (
          <MetricCard key={m.id} metric={m} index={i} />
        ))}
      </div>
    </div>
  );
}
