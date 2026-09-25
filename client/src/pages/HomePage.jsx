import { useState, useCallback, useEffect, useMemo, useRef, lazy, Suspense } from "react";
import TopBar from "@/components/TopBar";
import MetricsRow from "@/components/MetricsRow";
import ConflictBanner from "@/components/ConflictBanner";
import ResolveModal from "@/components/ResolveModal";
import SuccessToast from "@/components/SuccessToast";
import RadarCanvas from "@/components/RadarCanvas";
import AIAuditTrail from "@/components/AIAuditTrail";
const FlightRadarMap = lazy(() => import("@/components/FlightRadarMap.tsx"));
import TimelinePanel from "@/components/TimelinePanel";
import FlightListPanel from "@/components/FlightListPanel";
import FlightDetailDrawer from "@/components/FlightDetailDrawer";
import AISuggestionsPanel from "@/components/AISuggestionsPanel";
import WatchListPanel from "@/components/WatchListPanel";
import DataSourceBar from "@/components/DataSourceBar";
import RunwayStatusPanel from "@/components/RunwayStatusPanel";
import NLPCommsPanel from "@/components/NLPCommsPanel";
import { BlurFade } from "@/components/ui/blur-fade";

import { useLiveData } from "@/hooks/useLiveData";
import {
  conflictFromAlerts, metricsFromState, resolveOptionsFromAlert,
  suggestionsFromAlerts, timelineFromAlerts, watchListFromAlerts, withConflictStatus,
} from "@/lib/adapters";
import { acceptSuggestion, dismissSuggestion } from "@/lib/api";
import { logActivity, logAudit } from "@/lib/siteLogger";

export default function HomePage() {
  // Everything on this page comes from the backend. There is no mock traffic, no mock
  // conflict and no mock resolution: if the backend is unreachable the dashboard says
  // so rather than showing aircraft that do not exist.
  const { flights: rawFlights, conflicts, feed, connection, lastError } = useLiveData();

  const active = conflicts.active || [];
  const flights = useMemo(() => withConflictStatus(rawFlights, active), [rawFlights, active]);
  const conflict = useMemo(() => conflictFromAlerts(active), [active]);
  const suggestions = useMemo(() => suggestionsFromAlerts(active), [active]);
  const watchList = useMemo(() => watchListFromAlerts(active), [active]);
  const metrics = useMemo(
    () => metricsFromState(flights, conflicts, feed), [flights, conflicts, feed]);
  const resolveOptions = useMemo(() => resolveOptionsFromAlert(conflict), [conflict]);
  const timelineRows = useMemo(() => timelineFromAlerts(active), [active]);

  const [resolveModalOpen, setResolveModalOpen] = useState(false);
  const [selectedOption, setSelectedOption] = useState("OPT_1");
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState("ALL");
  const [acceptedCount, setAcceptedCount] = useState(0);
  const [handledIds, setHandledIds] = useState(new Set());

  const [theme, setTheme] = useState("light");
  useEffect(() => {
    if (theme === "light") document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
  }, [theme]);
  const toggleTheme = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      logAudit("dashboard:theme", "Application color theme switched", { next });
      return next;
    });

  // Only confirmed tier 1 alarms are interruptions. Tier 2 is a watch list.
  const alertCount = (conflicts.counts?.tier_1 ?? 0);

  const showToast = useCallback((message) => {
    setToast({ message, type: "success" });
    setTimeout(() => setToast(null), 4000);
  }, []);

  useEffect(() => {
    const handleToastEvent = (e) => showToast(e.detail);
    window.addEventListener("show-toast", handleToastEvent);
    return () => window.removeEventListener("show-toast", handleToastEvent);
  }, [showToast]);

  // Keep the selected option valid as the engine's option set changes between updates.
  useEffect(() => {
    if (resolveOptions.length && !resolveOptions.some((o) => o.id === selectedOption)) {
      setSelectedOption(resolveOptions[0].id);
    }
  }, [resolveOptions, selectedOption]);

  const handleResolveClick = () => {
    if (!conflict) return;
    logAudit("conflict:flow", "Conflict resolution flow opened", { pair: [conflict.flight1, conflict.flight2] });
    setResolveModalOpen(true);
  };

  /**
   * The controller accepted a suggestion. This RECORDS the decision in the server-side
   * audit log. It does not transmit anything to an aircraft and it does not change the
   * traffic picture: the next surveillance update decides whether the conflict is gone,
   * exactly as it would in a real centre.
   */
  const handleAcceptResolution = async () => {
    if (!conflict) return;
    const option = resolveOptions.find((o) => o.id === selectedOption) || resolveOptions[0];
    try {
      await acceptSuggestion({
        conflictId: conflict.id,
        callsign: option?.manoeuvre?.aircraft,
        action: option ? `Accepted: ${option.action}` : "Accepted resolution",
        confidence: option ? Number(String(option.confidence).replace("%", "")) / 100 : null,
        modelVersion: conflict.sources,
        detail: { optionId: selectedOption, pair: [conflict.flight1, conflict.flight2],
                  manoeuvre: option?.manoeuvre, score: option?.score },
      });
      showToast(`Decision recorded — ${conflict.flight1} & ${conflict.flight2}`);
    } catch (error) {
      showToast(`Could not record the decision: ${error.message}`);
    }
    setResolveModalOpen(false);
  };

  const handleCancelResolution = async () => {
    if (conflict) {
      try {
        await dismissSuggestion({
          conflictId: conflict.id,
          action: "Dismissed resolution options — handling manually",
          detail: { optionId: selectedOption, pair: [conflict.flight1, conflict.flight2] },
        });
      } catch { /* the modal still closes; the failure is surfaced by the audit page */ }
    }
    setResolveModalOpen(false);
  };

  const handleAcceptSuggestion = async (suggestion) => {
    try {
      await acceptSuggestion({
        conflictId: suggestion.id,
        callsign: suggestion.flights[0],
        action: `Accepted suggestion: ${suggestion.text}`,
        confidence: Number(String(suggestion.confidence).replace("%", "")) / 100,
        detail: { pair: suggestion.flights, tier: suggestion.tier },
      });
      setAcceptedCount((c) => c + 1);
      setHandledIds((prev) => new Set([...prev, suggestion.episodeKey]));
      showToast(suggestion.actionToast);
    } catch (error) {
      showToast(`Could not record the decision: ${error.message}`);
    }
  };

  const handleDismissSuggestion = async (id) => {
    const suggestion = suggestions.find((s) => s.id === id);
    try {
      await dismissSuggestion({
        conflictId: id,
        action: "Dismissed AI suggestion",
        detail: { pair: suggestion?.flights },
      });
    } catch { /* recorded failures surface on the audit page */ }
    setHandledIds((prev) => new Set([...prev, suggestion?.episodeKey ?? id]));
  };

  const handleSelectFlight = (callsign, meta = {}) => {
    const next = callsign === selectedFlight ? null : callsign;
    logAudit("flights:select", next ? "Flight selection set" : "Flight selection cleared", {
      callsign: next, surface: meta.surface || "unknown",
    });
    setSelectedFlight(next);
  };

  const handleTabChange = (tab) => {
    logAudit("flights:tab", "Flight list filter changed", { tab });
    setActiveTab(tab);
  };

  const [timelineOpen, setTimelineOpen] = useState(false);
  const [auditTrailOpen, setAuditTrailOpen] = useState(false);
  const [mapView, setMapView] = useState("map");
  const [weatherOn, setWeatherOn] = useState(false);

  const bootLogged = useRef(false);
  useEffect(() => {
    if (bootLogged.current || connection === "connecting") return;
    bootLogged.current = true;
    logAudit("session:dashboard", "Controller dashboard connected to backend", {
      connection, source: feed.source, mode: feed.mode,
    });
    logActivity("dashboard", `Dashboard connected (${connection}, ${feed.source || "no source"})`);
  }, [connection, feed.source, feed.mode]);

  const visibleSuggestions = suggestions.filter((s) => !handledIds.has(s.episodeKey));

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}>
      <TopBar
        alertCount={alertCount}
        trackedCount={flights.length}
        aiEnabled={aiEnabled}
        onToggleAI={() => {
          setAiEnabled((v) => {
            const next = !v;
            logAudit("dashboard:ai", "AI assist master control toggled", { enabled: next });
            return next;
          });
        }}
        theme={theme}
        onToggleTheme={toggleTheme}
        conflict={conflict}
        weatherOn={weatherOn}
        onWeatherToggle={() => setWeatherOn((w) => !w)}
      />

      <DataSourceBar feed={feed} connection={connection} lastError={lastError}
                     conflicts={conflicts} theme={theme} />

      <div className="relative z-40 w-full">
        <ConflictBanner conflict={conflict} onResolveClick={handleResolveClick} theme={theme} />
      </div>

      <div className="relative flex flex-1 gap-4 overflow-hidden p-4">
        <BlurFade delay={0} direction="right" offset={10} className="flex h-full min-h-0 w-[280px] shrink-0 flex-col">
          <FlightListPanel
            flightsData={flights}
            selectedFlight={selectedFlight}
            onSelectFlight={handleSelectFlight}
            activeTab={activeTab}
            onTabChange={handleTabChange}
            theme={theme}
          />
        </BlurFade>

        <BlurFade delay={0.06} direction="down" offset={12} className="flex h-full w-[55vw] shrink-0 flex-col gap-2">
          <div className="relative flex shrink-0 items-center gap-0" style={{ height: 30, zIndex: 900 }}>
            {[{ key: "map", label: "MAP VIEW" }, { key: "radar", label: "RADAR SWEEP" }].map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setMapView(key)}
                className="font-display px-5 py-1.5 text-[11px] tracking-widest transition-all"
                style={{
                  background: mapView === key ? "var(--amber)" : "transparent",
                  color: mapView === key ? "#0a0b0e" : "var(--amber)",
                  border: "1px solid var(--amber)",
                  marginLeft: key === "radar" ? -1 : 0,
                }}
              >
                {label}
              </button>
            ))}

            <button
              type="button"
              onClick={() => setWeatherOn((w) => !w)}
              title="Weather overlay is illustrative only — no weather feed is connected."
              className="font-display ml-2 px-4 py-1.5 text-[11px] tracking-widest transition-all"
              style={{
                background: weatherOn ? "var(--teal)" : "transparent",
                color: weatherOn ? "#0a0b0e" : "var(--teal)",
                border: "1px solid var(--teal)",
              }}
            >
              ☁ WEATHER (DEMO)
            </button>

            <div className="relative ml-auto" style={{ zIndex: 950 }}>
              <AIAuditTrail isOpen={auditTrailOpen} onToggle={() => setAuditTrailOpen((o) => !o)} />
            </div>
          </div>

          <div className="relative min-h-0 flex-1 overflow-hidden">
            <div style={{ position: "absolute", inset: 0, display: mapView === "map" ? "block" : "none" }}>
              <Suspense fallback={<MapLoading />}>
                <FlightRadarMap
                  flights={flights}
                  conflict={conflict}
                  selectedFlight={selectedFlight}
                  onSelectFlight={handleSelectFlight}
                  theme={theme}
                />
              </Suspense>
            </div>
            <div style={{ position: "absolute", inset: 0, display: mapView === "radar" ? "block" : "none" }}>
              <RadarCanvas flights={flights} selectedFlight={selectedFlight} theme={theme}
                           weatherOn={weatherOn} weatherDevAccepted={false} />
            </div>
          </div>
        </BlurFade>

        <BlurFade delay={0.12} direction="left" offset={10} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
          <MetricsRow metricsData={metrics} />
          <AISuggestionsPanel
            suggestions={visibleSuggestions}
            onAccept={handleAcceptSuggestion}
            onDismiss={handleDismissSuggestion}
            aiEnabled={aiEnabled}
            acceptedCount={acceptedCount}
          />
          <WatchListPanel items={watchList} lowConfidence={conflicts.lowConfidence} theme={theme} />
          <RunwayStatusPanel />
          <NLPCommsPanel />
          <div className="h-4 shrink-0" />
        </BlurFade>
      </div>

      <TimelinePanel isOpen={timelineOpen} onToggle={() => setTimelineOpen((o) => !o)}
                     rows={timelineRows} />

      <ResolveModal
        open={resolveModalOpen}
        conflict={conflict}
        options={resolveOptions}
        countdown={conflict?.countdown || 0}
        selectedOption={selectedOption}
        onSelectOption={setSelectedOption}
        onApply={handleAcceptResolution}
        onCancel={handleCancelResolution}
      />
      <SuccessToast toast={toast} />

      <FlightDetailDrawer
        flight={flights.find((f) => f.callsign === selectedFlight) || null}
        onClose={() => handleSelectFlight(null, { surface: "drawer-close" })}
        theme={theme}
      />
    </div>
  );
}

function MapLoading() {
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center",
                  justifyContent: "center", background: "var(--bg-base)" }}>
      <span style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", fontSize: 12,
                     color: "var(--text-muted)", letterSpacing: "0.2em" }}>
        LOADING RADAR MAP…
      </span>
    </div>
  );
}
