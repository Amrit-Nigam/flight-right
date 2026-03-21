import { useState, useEffect } from "react";
import { Bell, Sun, Moon } from "lucide-react";

export default function TopBar({ alertCount, aiEnabled, onToggleAI, theme, onToggleTheme }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const utc = time.toISOString().slice(11, 19);
  const hasAlerts = alertCount > 0;

  return (
    <header
      className={`sticky top-0 z-50 flex items-stretch justify-between h-[80px] ${hasAlerts ? 'animate-header-pulse' : ''}`}
      style={{
        background: 'var(--bg-panel-alt)',
        borderBottom: hasAlerts ? '2px solid var(--red)' : '2px solid var(--amber)',
        boxShadow: hasAlerts ? '0 4px 24px rgba(255,45,45,0.5)' : '0 4px 20px rgba(245,166,35,0.15)',
        transition: 'all 0.3s ease-in-out',
      }}
    >
      {/* LEFT ZONE: ATIS & Runway */}
      <div className="flex-1 flex items-center px-6" style={{ borderRight: '1px solid var(--border-default)' }}>
        <div>
          <p className="font-body text-[11px] uppercase tracking-widest mb-1" style={{ color: 'var(--text-muted)' }}>
            Airport Status
          </p>
          <div className="flex items-baseline gap-4">
            <h1 className="font-display text-[28px] tracking-[2px]" style={{ color: 'var(--amber)' }}>
              ATIS M
            </h1>
            <span className="font-display text-[16px]" style={{ color: 'var(--text-secondary)' }}>
              RWY 27R / 27L
            </span>
          </div>
        </div>
      </div>

      {/* CENTER ZONE: Live Clock & System Status */}
      <div className="flex-1 flex flex-col items-center justify-center px-6" style={{ borderRight: '1px solid var(--border-default)' }}>
        <div className="font-display tabular-nums text-[48px] tracking-widest leading-none drop-shadow-md pb-1" style={{ color: 'var(--amber)', textShadow: '0 0 16px rgba(245,166,35,0.4)', fontVariantNumeric: 'tabular-nums' }}>
          {utc}
        </div>
        <div className="flex items-center gap-2 px-3 py-1 rounded-sm" style={{ border: `1px solid ${hasAlerts ? 'var(--red)' : 'var(--green)'}`, background: hasAlerts ? 'var(--red-glow)' : 'rgba(0,255,136,0.05)' }}>
          <span className={`w-2 h-2 rounded-full ${hasAlerts ? 'animate-blink' : 'animate-pulse-dot'}`} style={{ background: hasAlerts ? 'var(--red)' : 'var(--green)' }} />
          <span className="font-display text-[10px] tracking-widest uppercase" style={{ color: hasAlerts ? 'var(--red)' : 'var(--green)' }}>
            {hasAlerts ? 'ATC ALERT — CONFLICT DETECTED' : 'SYSTEM ACTIVE — NOMINAL'}
          </span>
        </div>
      </div>

      {/* RIGHT ZONE: AI Status, Controller, Notifications, Theme */}
      <div className="flex-1 flex items-center justify-end px-6 gap-6">
        {/* AI Engine Status */}
        <button
          onClick={onToggleAI}
          className="flex flex-col items-end text-right transition-colors"
        >
          <span className="font-body text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>
            AI Engine
          </span>
          <span className="font-display text-[14px]" style={{ color: aiEnabled ? 'var(--teal)' : 'var(--text-secondary)', textShadow: aiEnabled ? '0 0 8px rgba(0,229,204,0.4)' : 'none' }}>
            {aiEnabled ? 'ASSIST ACTIVE' : 'ASSIST OFF'}
          </span>
        </button>

        <div className="w-[1px] h-8" style={{ background: 'var(--border-default)' }} />

        {/* Controller Name */}
        <div className="text-right">
          <span className="block font-body text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--text-muted)' }}>
            Controller
          </span>
          <span className="block font-display text-[15px]" style={{ color: 'var(--text-primary)' }}>
            A. SHARMA
          </span>
        </div>

        <div className="w-[1px] h-8" style={{ background: 'var(--border-default)' }} />

        {/* Action icons (Notifications & Theme) */}
        <div className="flex items-center gap-4">
          <button
            onClick={onToggleTheme}
            className="p-1 transition-colors rounded"
            style={{ color: 'var(--text-muted)' }}
            title="Toggle Theme"
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>

          <div className="relative flex items-center justify-center p-1">
            <Bell className="w-5 h-5" style={{ color: hasAlerts ? 'var(--red)' : 'var(--amber)' }} />
            {hasAlerts && (
              <span className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center rounded-full font-display text-[10px] animate-blink" style={{ background: 'var(--red)', color: 'white' }}>
                {alertCount}
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
