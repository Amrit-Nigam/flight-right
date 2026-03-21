import { useEffect, useState } from "react";
import { metrics } from "@/data/mockData";

const colorMap = {
  cyan: "text-atc-cyan border-atc-cyan/20 bg-atc-cyan/5",
  green: "text-atc-success border-atc-success/20 bg-atc-success/5",
  warning: "text-atc-warning border-atc-warning/20 bg-atc-warning/5",
  accent_green: "text-atc-green border-atc-green/20 bg-atc-green/5",
  text: "text-atc-text-primary border-atc-text-muted/20 bg-atc-text-muted/5",
  purple: "text-atc-purple border-atc-purple/20 bg-atc-purple/5",
};

function useCountUp(target, duration = 1200) {
  const [value, setValue] = useState(0);
  const numTarget = typeof target === "string" ? parseFloat(target) : target;
  const isNumber = !isNaN(numTarget);

  useEffect(() => {
    if (!isNumber) { setValue(target); return; }
    let start = 0;
    const startTime = performance.now();
    const step = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      start = Math.round(eased * numTarget * 10) / 10;
      setValue(start);
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [numTarget, duration, isNumber, target]);

  return value;
}

function MetricCard({ metric, index }) {
  const displayVal = useCountUp(metric.value);
  const classes = colorMap[metric.color] || colorMap.cyan;

  const formatValue = () => {
    const raw = typeof metric.value === "string" ? metric.value : "";
    if (raw.includes("%")) return `${displayVal}%`;
    if (raw.includes("kt")) return `${displayVal} kt`;
    if (raw.includes("m")) return `${typeof displayVal === "number" ? displayVal.toLocaleString() : displayVal} m`;
    if (raw.includes("min")) return `${displayVal} min`;
    return displayVal;
  };

  return (
    <div
      className={`rounded-lg border p-3 ${classes} animate-fade-in-up`}
      style={{ animationDelay: `${index * 80}ms` }}
    >
      <p className="text-[10px] uppercase tracking-wider opacity-70 mb-1 font-medium">{metric.label}</p>
      <p className="text-xl font-bold font-mono tracking-tight">{formatValue()}</p>
      <p className={`text-[10px] mt-1 ${metric.deltaType === "up" ? "text-atc-success" : "text-atc-text-muted"}`}>
        {metric.delta}
      </p>
    </div>
  );
}

export default function MetricsRow() {
  return (
    <div className="grid grid-cols-4 xl:grid-cols-8 gap-2">
      {metrics.map((m, i) => (
        <MetricCard key={m.id} metric={m} index={i} />
      ))}
    </div>
  );
}
