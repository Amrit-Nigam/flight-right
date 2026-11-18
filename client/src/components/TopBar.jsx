import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Bell, Sun, Moon, Radio, ScrollText } from "lucide-react";
import { logAudit } from "@/lib/siteLogger";

// Everything in this bar comes from the backend (27 Sep 2026). It used to show an invented
// "ATIS M · RWY 27R / 27L" (Mumbai has 09/27 and 14/32, and no ATIS feed is readable), a made-up
// controller name, today's wall clock while replaying a recording, a microphone that only
// showed "coming soon", and a bell that always said "No new system notifications".

function useDataClock(feed, connection) {
  // The time the picture on screen describes, advancing between updates.
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const data = Date.parse(feed.dataTimeUtc);
  const age = Math.max(0, now - Date.parse(feed.updatedAt));
  // This is a display freshness indicator, not an alert/model threshold.
  const stale = !Number.isFinite(age) || age > 45000;
  const advancing = connection !== 'offline' && !feed.error && !stale;
  const elapsed = advancing ? age * (feed.replay?.speed ?? 1) : 0;
  return { clock: Number.isFinite(data) ? new Date(data + elapsed) : null, stale, elapsed };
}

export default function TopBar({ alertCount, aiEnabled, onToggleAI, theme, onToggleTheme, conflict, trackedCount = 0,
                                 feed = {}, airport = null, health = null, notifications = [], connection = 'connecting' }) {
  const [bellOpen, setBellOpen] = useState(false);
  const {clock, stale, elapsed} = useDataClock(feed, connection);
  const cpaSeconds = conflict ? Math.max(0, Math.round(conflict.countdown - elapsed / 1000)) : 0;
  const feedStatus = connection === 'offline' ? 'DISCONNECTED' : !feed.source ? 'CONNECTING' : feed.error ? 'FEED ERROR' : stale ? 'STALE DATA' : null;

  const hasAlerts = alertCount > 0;
  const statusColor = feedStatus || hasAlerts ? 'var(--red)' : 'var(--green)';
  const cpaStr = `${String(Math.floor(cpaSeconds / 60)).padStart(2, "0")}:${String(cpaSeconds % 60).padStart(2, "0")}`;
  const cpaColor = cpaSeconds < 180 ? "var(--red)" : cpaSeconds < 480 ? "var(--amber)" : "var(--green)";
  const isReplay = feed.source === "replay";
  const inUse = airport?.inUse;
  const metar = airport?.metar;
  const wind = metar
    ? (metar.windVariable ? `VRB/${metar.windKt} kt` : metar.windDirDeg != null ? `${String(metar.windDirDeg).padStart(3, "0")}°/${metar.windKt} kt${metar.gustKt ? ` G${metar.gustKt}` : ""}` : null)
    : null;

  return (
    <header
      className={`atc-header sticky top-0 z-50 flex shrink-0 items-stretch justify-between h-[80px] ${hasAlerts ? "animate-header-pulse" : ""}`}
      style={{
        background: "var(--bg-panel-alt)",
        borderBottom: hasAlerts ? "2px solid var(--red)" : "2px solid var(--amber)",
        boxShadow: hasAlerts
          ? (theme === "light" ? "0 3px 16px rgba(185,28,28,0.22)" : "0 4px 24px rgba(255,45,45,0.5)")
          : (theme === "light" ? "0 1px 0 rgba(180,83,9,0.2)" : "0 4px 20px rgba(245,166,35,0.15)"),
        transition: "all 0.3s ease-in-out",
      }}
    >
      {/* LEFT: the airport, from real data only */}
      <div className="flex-1 flex items-center px-6 min-w-0" style={{ borderRight: "1px solid var(--border-default)" }}>
        <div className="min-w-0">
          <p className="font-body text-[11px] uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
            Mumbai · VABB
          </p>
          <div className="flex items-baseline gap-4">
            <h1 className="font-display text-[26px] tracking-[2px] whitespace-nowrap" style={{ color: "var(--amber)" }}
                title={inUse ? `Runway in use derived from ${inUse.derived}: ${inUse.basis}` : "No runway movement observed and no wind report yet"}>
              {inUse ? `RWY ${inUse.end}` : "RWY —"}
            </h1>
            <span className="font-display text-[13px] truncate" style={{ color: "var(--text-secondary)" }}
                  title={metar ? `METAR ${metar.raw} (${metar.source})` : "No METAR available"}>
              {metar ? `${wind ?? "wind —"} · Q${metar.qnhHpa ?? "—"}${metar.stale ? " · METAR STALE" : ""}` : "METAR unavailable"}
            </span>
          </div>
          <p className="font-body text-[9px] tracking-wide mt-0.5 truncate" style={{ color: "var(--text-muted)" }}>
            {inUse ? `in use: ${inUse.derived === "surface wind" ? "from surface wind" : "from observed movements"}` : ""}
          </p>
        </div>
      </div>

      {/* CENTER: the time the picture describes */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 gap-1" style={{ borderRight: "1px solid var(--border-default)" }}>
        <div className="flex items-baseline gap-2">
          <div className="data-clock font-display tabular-nums text-[36px] tracking-widest leading-none"
               style={{ color: "var(--amber)", textShadow: "0 0 10px rgba(245,166,35,0.22)", fontVariantNumeric: "tabular-nums" }}
               title={isReplay ? "The recording's own time (UTC), not today's" : "UTC"}>
            {clock ? clock.toISOString().slice(11, 19) : "--:--:--"}
          </div>
          <span className="font-display text-[10px] tracking-widest" style={{ color: "var(--text-muted)" }}>
            UTC{isReplay && clock ? ` · ${clock.toISOString().slice(0, 10)} REC` : ""}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div role="status" className="flex items-center gap-1.5 px-2 py-0.5 rounded-sm" style={{ border: `1px solid ${statusColor}`, background: feedStatus || hasAlerts ? "var(--status-alert-bg)" : "var(--status-nominal-bg)" }}>
            <span className={`w-1.5 h-1.5 rounded-full ${hasAlerts ? "animate-blink" : "animate-pulse-dot"}`} style={{ background: statusColor }} />
            <span className="font-display text-[9px] tracking-widest uppercase" style={{ color: statusColor }}>
              {feedStatus || (hasAlerts ? "ATC ALERT" : "NO ACTIVE ALERTS")}
            </span>
          </div>
          {conflict && cpaSeconds > 0 && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-sm animate-pulse"
                 style={{ border: `1px solid ${cpaColor}`, background: `${cpaColor}18`, cursor: "default" }}
                 title={`CPA: ${conflict.flight1} × ${conflict.flight2}`}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: cpaColor }} />
              <span className="font-display text-[9px] tracking-widest tabular-nums" style={{ color: cpaColor }}>
                {conflict.flight1} × {conflict.flight2} · {cpaStr}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* RIGHT */}
      <div className="flex-1 flex items-center justify-end px-3 lg:px-5 gap-2 lg:gap-4 min-w-0">
        <button
          title="Show or hide the suggestions panel. Monitoring and planning continue."
          aria-pressed={aiEnabled}
          onClick={() => { logAudit("topbar:ai", "AI assist control clicked", { priorEnabled: aiEnabled }); onToggleAI(); }}
          className="flex flex-col items-end text-right transition-colors shrink min-w-0"
        >
          <span className="font-body text-[9px] sm:text-[10px] uppercase tracking-wider mb-0.5 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>Suggestions</span>
          <div className="flex items-center gap-1.5">
            {aiEnabled && <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "var(--teal)", boxShadow: "0 0 6px rgba(0,229,204,0.6)" }} />}
            <span className="font-display text-[12px] sm:text-[13px] whitespace-nowrap" style={{ color: aiEnabled ? "var(--teal)" : "var(--text-secondary)" }}>
              {aiEnabled ? "SHOWN" : "HIDDEN"}
            </span>
          </div>
          {aiEnabled && (
            <span className="hidden 2xl:block font-body text-[9px] tracking-wide mt-0.5 whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
              {trackedCount} tracked · {alertCount} alarm{alertCount === 1 ? "" : "s"}
            </span>
          )}
        </button>

        <div className="w-[1px] h-8 shrink-0" style={{ background: "var(--border-default)" }} />

        {/* Passive monitoring of the existing pilot/ATCO radio channel. */}
        <button
          onClick={() => document.getElementById("live-radio-monitor")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          className="p-1.5 rounded transition-colors hover:bg-white/5 active:scale-95 disabled:opacity-40"
          style={{ color: "var(--text-muted)" }}
          title="Open the live pilot/ATCO radio monitor"
          aria-label="Open live radio monitor"
        >
          <Radio className="w-4 h-4" />
        </button>

        <div className="hidden xl:block text-right shrink-0" title="The identity every audit row is recorded under (no login in this prototype)">
          <span className="block font-body text-[10px] uppercase tracking-wider mb-1" style={{ color: "var(--text-muted)" }}>Controller</span>
          <span className="block font-display text-[15px]" style={{ color: "var(--text-primary)" }}>
            {health?.controller ?? "—"}
          </span>
        </div>

        <div className="hidden xl:block w-[1px] h-8 shrink-0" style={{ background: "var(--border-default)" }} />

        <Link
          to="/logs"
          onClick={() => logAudit("topbar:nav", "User opened Session logs from header", { to: "/logs" })}
          className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[9px] font-semibold uppercase tracking-wider transition-colors hover:bg-white/5 sm:gap-1.5 sm:px-2.5 sm:py-1.5 sm:text-[10px] sm:tracking-widest shrink-0"
          style={{ color: "var(--text-muted)" }}
          title="Audit log"
        >
          <ScrollText className="h-3 w-3 shrink-0 sm:h-3.5 sm:w-3.5" />
          <span className="hidden lg:inline">Logs</span>
        </Link>

        <div className="w-px h-8 shrink-0" style={{ background: "var(--border-default)" }} />

        <div className="flex items-center gap-1.5 sm:gap-2.5 shrink-0">
          <button
            onClick={() => { logAudit("topbar:theme", "Theme toggle control clicked", { priorTheme: theme }); onToggleTheme(); }}
            className="p-1 transition-colors rounded hover:bg-white/5 active:scale-95"
            style={{ color: "var(--text-muted)" }}
            title="Toggle Theme"
          >
            {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>

          <div className="relative">
            <button
              className="relative flex items-center justify-center p-1 hover:bg-white/5 rounded transition-colors active:scale-95"
              onClick={() => { logAudit("topbar:notifications", "Notifications opened", { count: notifications.length }); setBellOpen((o) => !o); }}
              title="Recent alert notifications from the alert feed"
            >
              <Bell className="w-5 h-5" style={{ color: hasAlerts ? "var(--red)" : "var(--amber)" }} />
              {hasAlerts && (
                <span className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center rounded-full font-display text-[10px] animate-blink pointer-events-none" style={{ background: "var(--red)", color: "white" }}>
                  {alertCount}
                </span>
              )}
            </button>
            {bellOpen && (
              <div className="absolute right-0 top-9 w-[380px] max-h-[360px] overflow-y-auto p-3 z-[1000]"
                   style={{ background: "var(--bg-panel)", border: "1px solid var(--border-default)", boxShadow: "0 8px 24px rgba(0,0,0,0.25)" }}>
                <p className="font-display text-[10px] tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
                  RECENT NOTIFICATIONS · alert feed
                </p>
                {notifications.length === 0 && (
                  <p className="font-body text-[11px]" style={{ color: "var(--text-muted)" }}>No notifications since this page opened.</p>
                )}
                {notifications.map((n) => (
                  <div key={n.key} className="py-1.5" style={{ borderTop: "1px solid var(--border-default)" }}>
                    <p className="font-display text-[11px]" style={{ color: n.tier === 1 ? "var(--red)" : "var(--amber)" }}>
                      {n.pair.join(" × ")} · tier {n.tier}
                      <span className="font-body text-[9px] ml-2" style={{ color: "var(--text-muted)" }}>{n.at}</span>
                    </p>
                    <p className="font-body text-[10px]" style={{ color: "var(--text-secondary)" }}>{n.reason}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
