import { useState, useEffect } from "react";
import { Plane } from "lucide-react";

export default function TopBar({ alertCount, aiEnabled, onToggleAI }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const utc = time.toISOString().slice(11, 19);
  const hasAlerts = alertCount > 0;

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between h-[56px] px-4" style={{ background: 'var(--bg-base)', borderBottom: '2px solid var(--amber)' }}>
      {/* Left — Logo */}
      <div className="flex items-center gap-3">
        <Plane className="w-5 h-5" style={{ color: 'var(--amber)' }} />
        <div>
          <h1 className="font-display text-[16px] tracking-[3px]" style={{ color: 'var(--amber)' }}>AEROSYNC ATC</h1>
          <p className="text-[9px] font-body" style={{ color: 'var(--text-muted)' }}>Air Traffic Controller Assistant v2.4.1</p>
        </div>
      </div>

      {/* Center — Status + Clock */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2 px-3 py-1" style={{ border: `1px solid ${hasAlerts ? 'var(--red)' : 'var(--green)'}`, background: hasAlerts ? 'var(--red-glow)' : 'rgba(0,255,136,0.05)' }}>
          <span className={`w-2 h-2 rounded-full ${hasAlerts ? 'animate-blink' : 'animate-pulse-dot'}`} style={{ background: hasAlerts ? 'var(--red)' : 'var(--green)' }} />
          <span className="font-display text-[11px] tracking-wider" style={{ color: hasAlerts ? 'var(--red)' : 'var(--green)' }}>
            {hasAlerts ? 'ALERT — CONFLICT DETECTED' : 'SYSTEM ACTIVE — ALL SYSTEMS NOMINAL'}
          </span>
        </div>
        <div className="font-display text-[22px] tracking-widest glow-amber" style={{ color: 'var(--amber)' }}>
          {utc} <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>UTC</span>
        </div>
      </div>

      {/* Right — Alerts + AI + Controller */}
      <div className="flex items-center gap-3">
        <button
          className={`status-badge ${hasAlerts ? 'animate-blink' : ''}`}
          style={{
            borderColor: hasAlerts ? 'var(--red)' : 'var(--text-muted)',
            color: hasAlerts ? 'var(--red)' : 'var(--text-muted)',
            background: hasAlerts ? 'var(--red-glow)' : 'transparent',
          }}
        >
          ⚠ {alertCount} ALERTS
        </button>

        <button
          onClick={onToggleAI}
          className="status-badge transition-colors"
          style={{
            borderColor: aiEnabled ? 'var(--teal)' : 'var(--text-muted)',
            color: aiEnabled ? 'var(--teal)' : 'var(--text-muted)',
            background: aiEnabled ? 'var(--teal-glow)' : 'transparent',
          }}
        >
          {aiEnabled ? '✦ AI ASSIST ON' : '✦ AI ASSIST OFF'}
        </button>

        <div className="text-right ml-2">
          <p className="font-display text-[11px]" style={{ color: 'var(--text-secondary)' }}>A. SHARMA</p>
          <p className="font-display text-[9px]" style={{ color: 'var(--text-muted)' }}>SECTOR: 7B-ALPHA</p>
        </div>
      </div>
    </header>
  );
}
