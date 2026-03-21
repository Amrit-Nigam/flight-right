import { useState, useEffect } from "react";
import { conflictAlert } from "@/data/mockData";
import { AlertTriangle, Zap } from "lucide-react";

export default function ConflictAlertBanner() {
  const [seconds, setSeconds] = useState(conflictAlert.countdownStartSeconds);
  const [visible, setVisible] = useState(conflictAlert.visible);

  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => {
      setSeconds((s) => {
        if (s <= 1) { clearInterval(id); return 0; }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [visible]);

  if (!visible) return null;

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;

  return (
    <div className="relative overflow-hidden rounded-lg border border-atc-danger/40 bg-atc-danger/5 p-3 box-glow-red">
      {/* Animated red pulse background */}
      <div className="absolute inset-0 bg-gradient-to-r from-atc-danger/10 via-transparent to-atc-danger/10 animate-pulse" />

      <div className="relative flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-1">
          <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-atc-danger/20 border border-atc-danger/30 animate-blink">
            <Zap className="w-5 h-5 text-atc-danger" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-bold text-atc-danger tracking-wider glow-red flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5" />
              {conflictAlert.title}
            </p>
            <p className="text-[10px] text-atc-text-secondary mt-0.5">{conflictAlert.detail}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-[9px] text-atc-danger/70 uppercase tracking-wider">Time to CPA</p>
            <p className="text-xl font-mono font-bold text-atc-danger glow-red tabular-nums">
              {String(mins).padStart(2, "0")}:{String(secs).padStart(2, "0")}
            </p>
          </div>
          <button className="px-4 py-2 text-[10px] font-bold tracking-widest uppercase bg-atc-danger text-white rounded-md hover:bg-atc-danger/80 transition-colors shadow-lg shadow-atc-danger/20">
            {conflictAlert.actionButton}
          </button>
        </div>
      </div>
    </div>
  );
}
