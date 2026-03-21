import { useState, useEffect } from "react";
import { Plane, Sun, Moon } from "lucide-react";

export default function TopBar({ alertCount, aiEnabled, onToggleAI, theme, onToggleTheme }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const utc = time.toISOString().slice(11, 19);
  const hasAlerts = alertCount > 0;

  return (
    <header className="sticky top-0 z-50 flex items-center justify-between h-[56px] px-5" style={{ background: 'var(--bg-base)', borderBottom: '2px solid var(--amber)' }}>
      {/* Left — Logo */}
      <div className="flex items-center gap-3">
        <Plane className="w-6 h-6" style={{ color: 'var(--amber)' }} />
        <div>
          <h1 className="font-display text-[18px] tracking-[3px]" style={{ color: 'var(--amber)' }}>AEROSYNC ATC</h1>
          <p className="text-[11px] font-body" style={{ color: 'var(--text-muted)' }}>Air Traffic Controller Assistant v2.4.1</p>
        </div>
      </div>

      {/* Center — Status + Clock */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2 px-3 py-1.5" style={{ border: `1px solid ${hasAlerts ? 'var(--red)' : 'var(--green)'}`, background: hasAlerts ? 'var(--red-glow)' : 'rgba(0,255,136,0.05)' }}>
          <span className={`w-2.5 h-2.5 rounded-full ${hasAlerts ? 'animate-blink' : 'animate-pulse-dot'}`} style={{ background: hasAlerts ? 'var(--red)' : 'var(--green)' }} />
          <span className="font-display text-[12px] tracking-wider" style={{ color: hasAlerts ? 'var(--red)' : 'var(--green)' }}>
            {hasAlerts ? 'ALERT — CONFLICT DETECTED' : 'SYSTEM ACTIVE — ALL SYSTEMS NOMINAL'}
          </span>
        </div>
        <div className="font-display text-[24px] tracking-widest glow-amber" style={{ color: 'var(--amber)' }}>
          {utc} <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>UTC</span>
        </div>
      </div>

      {/* Right — Theme + Alerts + AI + Controller */}
      <div className="flex items-center gap-3">
        {/* Theme Toggle */}
        <button
          onClick={onToggleTheme}
          className="p-2 transition-colors rounded"
          style={{ border: '1px solid var(--border-default)', color: 'var(--amber)' }}
          title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

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
          <p className="font-display text-[12px]" style={{ color: 'var(--text-secondary)' }}>A. SHARMA</p>
          <p className="font-display text-[10px]" style={{ color: 'var(--text-muted)' }}>SECTOR: 7B-ALPHA</p>
        </div>
      </div>
    </header>
  );
}
