import { useState, useEffect, useRef } from "react";
import { Bell, Sun, Moon, Mic } from "lucide-react";

export default function TopBar({ alertCount, aiEnabled, onToggleAI, theme, onToggleTheme, conflict, onWeatherToggle, weatherOn }) {
  const [time, setTime] = useState(new Date());
  const [cpaSeconds, setCpaSeconds] = useState(conflict?.countdown ?? 0);
  const timerRef = useRef(null);

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // Sync & tick the CPA countdown independently in the TopBar
  useEffect(() => {
    if (!conflict) { setCpaSeconds(0); return; }
    setCpaSeconds(conflict.countdown);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCpaSeconds(s => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [conflict]);

  const utc = time.toISOString().slice(11, 19);
  const hasAlerts = alertCount > 0;

  const cpaMin = Math.floor(cpaSeconds / 60);
  const cpaSec = cpaSeconds % 60;
  const cpaStr = `${String(cpaMin).padStart(2, "0")}:${String(cpaSec).padStart(2, "0")}`;
  // red below 3min, amber 3–8 min
  const cpaColor = cpaSeconds < 180 ? "var(--red)" : cpaSeconds < 480 ? "#f5a623" : "var(--green)";

  // Simulated AI workload
  const aiManagedCount = 4;
  const aiPending = 1;

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

      {/* CENTER ZONE: Live Clock, Status & CPA Chip */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 gap-1" style={{ borderRight: '1px solid var(--border-default)' }}>
        <div className="font-display tabular-nums text-[40px] tracking-widest leading-none" style={{ color: 'var(--amber)', textShadow: '0 0 16px rgba(245,166,35,0.4)', fontVariantNumeric: 'tabular-nums' }}>
          {utc}
        </div>
        <div className="flex items-center gap-2">
          {/* System status */}
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-sm" style={{ border: `1px solid ${hasAlerts ? 'var(--red)' : 'var(--green)'}`, background: hasAlerts ? 'var(--red-glow)' : 'rgba(0,255,136,0.05)' }}>
            <span className={`w-1.5 h-1.5 rounded-full ${hasAlerts ? 'animate-blink' : 'animate-pulse-dot'}`} style={{ background: hasAlerts ? 'var(--red)' : 'var(--green)' }} />
            <span className="font-display text-[9px] tracking-widest uppercase" style={{ color: hasAlerts ? 'var(--red)' : 'var(--green)' }}>
              {hasAlerts ? 'ATC ALERT' : 'NOMINAL'}
            </span>
          </div>

          {/* CPA conflict chip */}
          {conflict && cpaSeconds > 0 && (
            <div
              className="flex items-center gap-1 px-2 py-0.5 rounded-sm animate-pulse"
              style={{ border: `1px solid ${cpaColor}`, background: `${cpaColor}18`, cursor: 'default' }}
              title={`CPA: ${conflict.flight1} × ${conflict.flight2}`}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: cpaColor }} />
              <span className="font-display text-[9px] tracking-widest tabular-nums" style={{ color: cpaColor }}>
                {conflict.flight1} × {conflict.flight2} · {cpaStr}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT ZONE: AI Status, Mic, Controller, Notifications, Theme */}
      <div className="flex-1 flex items-center justify-end px-6 gap-5">
        {/* AI Engine Status with workload */}
        <button onClick={onToggleAI} className="flex flex-col items-end text-right transition-colors">
          <span className="font-body text-[10px] uppercase tracking-wider mb-0.5" style={{ color: 'var(--text-muted)' }}>
            AI Engine
          </span>
          <div className="flex items-center gap-1.5">
            {aiEnabled && (
              <span
                className="w-2 h-2 rounded-full animate-pulse"
                style={{ background: 'var(--teal)', boxShadow: '0 0 6px rgba(0,229,204,0.6)' }}
              />
            )}
            <span className="font-display text-[13px]" style={{ color: aiEnabled ? 'var(--teal)' : 'var(--text-secondary)', textShadow: aiEnabled ? '0 0 8px rgba(0,229,204,0.4)' : 'none' }}>
              {aiEnabled ? 'ASSIST ACTIVE' : 'ASSIST OFF'}
            </span>
          </div>
          {aiEnabled && (
            <span className="font-body text-[9px] tracking-wide mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Managing {aiManagedCount} flights · {aiPending} pending
            </span>
          )}
        </button>

        <div className="w-[1px] h-8" style={{ background: 'var(--border-default)' }} />

        {/* Mic stub — voice commands coming soon */}
        <button
          onClick={() => {
            const ce = new CustomEvent("show-toast", { detail: "Mic initialization pending — voice NLP module offline" });
            window.dispatchEvent(ce);
          }}
          className="p-1.5 rounded transition-colors hover:bg-white/5 active:scale-95"
          style={{ color: 'var(--text-muted)' }}
          title="Voice commands — coming soon"
          aria-label="Voice commands"
        >
          <Mic className="w-4 h-4" />
        </button>

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

        {/* Action icons */}
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleTheme}
            className="p-1 transition-colors rounded hover:bg-white/5 active:scale-95"
            style={{ color: 'var(--text-muted)' }}
            title="Toggle Theme"
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>

          <button 
            className="relative flex items-center justify-center p-1 hover:bg-white/5 rounded transition-colors active:scale-95"
            onClick={() => {
              const ce = new CustomEvent("show-toast", { detail: "No new system notifications." });
              window.dispatchEvent(ce);
            }}
          >
            <Bell className="w-5 h-5" style={{ color: hasAlerts ? 'var(--red)' : 'var(--amber)' }} />
            {hasAlerts && (
              <span className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center rounded-full font-display text-[10px] animate-blink pointer-events-none" style={{ background: 'var(--red)', color: 'white' }}>
                {alertCount}
              </span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
