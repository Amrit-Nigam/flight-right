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
    const raw = metric.value;
    if (raw.includes("%")) return `${displayVal}%`;
    if (raw.includes("kt")) return `${displayVal} kt`;
    if (raw.includes("km")) return `${displayVal} km`;
    if (raw.includes("m")) return `${displayVal}m`;
    return displayVal;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.3 }}
      className={`p-3 ${metric.pulse ? 'animate-blink' : ''}`}
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        clipPath: 'polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 0 100%)',
      }}
    >
      <p className="font-body text-[11px] uppercase tracking-[2px] mb-1" style={{ color: 'var(--text-muted)' }}>{metric.label}</p>
      <p className="font-display text-[26px] glow-amber" style={{ color, textShadow: `0 0 12px ${color}60` }}>{formatValue()}</p>
      <p className="font-body text-[12px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>{metric.delta}</p>
    </motion.div>
  );
}

export default function MetricsRow({ metricsData }) {
  return (
    <div className="grid grid-cols-4 xl:grid-cols-8 gap-2">
      {metricsData.map((m, i) => (
        <MetricCard key={m.id} metric={m} index={i} />
      ))}
    </div>
  );
}
