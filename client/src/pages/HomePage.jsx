import { useState, useCallback, useEffect, useRef, lazy, Suspense } from "react";
import TopBar from "@/components/TopBar";
import MetricsRow from "@/components/MetricsRow";
import ConflictBanner from "@/components/ConflictBanner";
import ResolveModal from "@/components/ResolveModal";
import SuccessToast from "@/components/SuccessToast";
import RadarCanvas from "@/components/RadarCanvas";
import AIAuditTrail from "@/components/AIAuditTrail";
const FlightRadarMap = lazy(() => import("@/components/FlightRadarMap"));
import TimelinePanel from "@/components/TimelinePanel";
import FlightListPanel from "@/components/FlightListPanel";
import FlightDetailDrawer from "@/components/FlightDetailDrawer";
import AISuggestionsPanel from "@/components/AISuggestionsPanel";
import RunwayStatusPanel from "@/components/RunwayStatusPanel";
import NLPCommsPanel from "@/components/NLPCommsPanel";
import { BlurFade } from "@/components/ui/blur-fade";

import { initialFlights, metrics, initialConflict, initialSuggestions } from "@/data/mockData";
import { logActivity, logAudit } from "@/lib/siteLogger";

export default function HomePage() {
  const [flights, setFlights] = useState(initialFlights);
  const [conflict, setConflict] = useState(initialConflict);
  const [suggestions, setSuggestions] = useState(initialSuggestions);
  const [resolveModalOpen, setResolveModalOpen] = useState(false);
  const [selectedOption, setSelectedOption] = useState("OPT_1");
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState("ALL");
  const [acceptedCount, setAcceptedCount] = useState(0);
  const [acceptedIds, setAcceptedIds] = useState(new Set());

  const [theme, setTheme] = useState("light");
  useEffect(() => {
    if (theme === "light") document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
  }, [theme]);
  const toggleTheme = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      logAudit("dashboard:theme", "Application color theme switched", { next });
      logActivity("ui:theme", `Theme → ${next}`);
      return next;
    });

  const alertCount = conflict
    ? flights.filter((f) => f.status === "CONFLICT" || f.status === "HOLDING").length > 0
      ? 1
      : 0
    : 0;

  const showToast = useCallback((message) => {
    setToast({ message, type: "success" });
    setTimeout(() => setToast(null), 4000);
  }, []);

  useEffect(() => {
    const handleToastEvent = (e) => showToast(e.detail);
    window.addEventListener("show-toast", handleToastEvent);
    return () => window.removeEventListener("show-toast", handleToastEvent);
  }, [showToast]);

  const handleResolveClick = () => {
    logAudit("conflict:flow", "Conflict resolution flow opened from workspace", {
      pair: conflict ? [conflict.flight1, conflict.flight2] : [],
    });
    logActivity("conflict:action", "User opened resolution flow from banner", {
      pair: conflict ? [conflict.flight1, conflict.flight2] : [],
    });
    setResolveModalOpen(true);
  };

  const handleApplyResolution = () => {
    logAudit("conflict:resolve", "Mock resolution committed to workspace state", {
      optionId: selectedOption,
      callsigns: ["AI6302", "SG881"],
    });
    logActivity("conflict:resolve", "Applied mock resolution to traffic state", {
      optionId: selectedOption,
      updatedCallsigns: ["AI6302", "SG881"],
      newStatus: "ENROUTE",
    });
    setResolveModalOpen(false);
    setConflict(null);
    setFlights((prev) =>
      prev.map((f) =>
        f.callsign === "AI6302" || f.callsign === "SG881"
          ? { ...f, status: "ENROUTE", cpaPair: undefined, cpaSeconds: undefined }
          : f
      )
    );
    showToast("Resolution Applied — AI6302 & SG881 Separation Secured");
  };

  const handleCancelResolution = () => {
    logAudit("conflict:resolve", "Resolution modal dismissed without applying automated option", {
      optionId: selectedOption,
    });
    logActivity("conflict:resolve", "Cancelled resolution modal (manual handling)", { optionId: selectedOption });
    setResolveModalOpen(false);
  };

  const handleAcceptSuggestion = (suggestion) => {
    logAudit("ai:suggestion", "Operator accepted AI suggestion card", {
      id: suggestion.id,
      type: suggestion.type,
      flights: suggestion.flights,
    });
    logActivity("ai:suggestion", `Accepted mock AI suggestion: ${suggestion.type}`, {
      id: suggestion.id,
      priority: suggestion.priority,
      flights: suggestion.flights,
      confidence: suggestion.confidence,
    });
    setSuggestions((prev) => prev.filter((s) => s.id !== suggestion.id));
    setAcceptedCount((c) => c + 1);
    setAcceptedIds((prev) => new Set([...prev, suggestion.id]));
    showToast(suggestion.actionToast || `Applied: ${suggestion.type} — ${suggestion.flights.join(", ")}`);
  };
  const handleDismissSuggestion = (id) => {
    const s = suggestions.find((x) => x.id === id);
    logAudit("ai:suggestion", "Operator dismissed AI suggestion card", s ? { id, type: s.type, flights: s.flights } : { id });
    logActivity("ai:suggestion", "Dismissed mock AI suggestion", s ? { id, type: s.type, flights: s.flights } : { id });
    setSuggestions((prev) => prev.filter((x) => x.id !== id));
  };

  const handleSelectFlight = (callsign, meta = {}) => {
    const next = callsign === selectedFlight ? null : callsign;
    logAudit("flights:select", next ? "Flight selection set" : "Flight selection cleared", {
      callsign: next,
      surface: meta.surface || "unknown",
    });
    logActivity("flights:select", next ? `Selected ${next} in mock list` : "Cleared flight selection", {
      callsign: next,
      surface: meta.surface || "unknown",
    });
    setSelectedFlight(next);
  };

  const handleTabChange = (tab) => {
    logAudit("flights:tab", "Flight list filter changed (workspace)", { tab });
    logActivity("flights:tab", `Flight list filter → ${tab}`);
    setActiveTab(tab);
  };

  const [timelineOpen, setTimelineOpen] = useState(false);
  const [auditTrailOpen, setAuditTrailOpen] = useState(false);
  const [mapView, setMapView] = useState("map");
  const [weatherOn, setWeatherOn] = useState(false);

  const bootLogged = useRef(false);
  useEffect(() => {
    if (bootLogged.current) return;
    bootLogged.current = true;
    logAudit("session:dashboard", "Operator loaded mock ATC dashboard surface", {
      flights: initialFlights.length,
      conflictScenario: !!(initialConflict && initialConflict.visible),
      suggestionsQueued: initialSuggestions.length,
    });
    logActivity("dashboard", "Mock ATC dashboard loaded", {
      flights: initialFlights.length,
      conflictScenario: !!(initialConflict && initialConflict.visible),
      suggestionsQueued: initialSuggestions.length,
    });
  }, []);

  const prevResolveOpen = useRef(false);
  useEffect(() => {
    if (resolveModalOpen && conflict && !prevResolveOpen.current) {
      logAudit("conflict:modal", "Resolution modal surface displayed", {
        flights: [conflict.flight1, conflict.flight2],
        selectedOption,
      });
      logActivity("conflict:modal", "Resolution modal opened (mock CPA scenario)", {
        flights: [conflict.flight1, conflict.flight2],
        selectedOption,
      });
    }
    prevResolveOpen.current = resolveModalOpen;
  }, [resolveModalOpen, conflict, selectedOption]);

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ background: "var(--bg-base)", color: "var(--text-primary)" }}>
      <TopBar
        alertCount={alertCount}
        aiEnabled={aiEnabled}
        onToggleAI={() => {
          setAiEnabled((v) => {
            const next = !v;
            logAudit("dashboard:ai", "AI assist master control toggled", { enabled: next });
            logActivity("ai:engine", `AI assist ${next ? "ENABLED" : "DISABLED"} (mock)`);
            return next;
          });
        }}
        theme={theme}
        onToggleTheme={toggleTheme}
        conflict={conflict}
        weatherOn={weatherOn}
        onWeatherToggle={() =>
          setWeatherOn((w) => {
            const next = !w;
            logAudit("dashboard:weather", "TopBar weather overlay control toggled", { on: next });
            logActivity("map:weather", `Radar/map weather overlay ${next ? "ON" : "OFF"} (mock)`);
            return next;
          })
        }
      />

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
            {[
              { key: "map", label: "MAP VIEW" },
              { key: "radar", label: "RADAR SWEEP" },
            ].map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  logAudit("dashboard:map-mode", "Center panel map/radar mode control", { view: key });
                  logActivity("map:view", `Center workspace view → ${key}`, { view: key });
                  setMapView(key);
                }}
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
              onClick={() =>
                setWeatherOn((w) => {
                  const next = !w;
                  logAudit("dashboard:weather", "Map toolbar weather control toggled", { on: next });
                  logActivity("map:weather", `Weather toggle from map bar → ${next ? "ON" : "OFF"}`);
                  return next;
                })
              }
              className="font-display ml-2 px-4 py-1.5 text-[11px] tracking-widest transition-all"
              style={{
                background: weatherOn ? "var(--teal)" : "transparent",
                color: weatherOn ? "#0a0b0e" : "var(--teal)",
                border: "1px solid var(--teal)",
              }}
            >
              ☁ WEATHER
            </button>

            <div className="relative ml-auto" style={{ zIndex: 950 }}>
              <AIAuditTrail isOpen={auditTrailOpen} onToggle={() => setAuditTrailOpen((o) => !o)} />
            </div>
          </div>

          <div className="relative min-h-0 flex-1 overflow-hidden">
            <div style={{ position: "absolute", inset: 0, display: mapView === "map" ? "block" : "none" }}>
              <Suspense
                fallback={
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: "var(--bg-base)",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "'Geist Variable', system-ui, sans-serif",
                        fontSize: 12,
                        color: "var(--text-muted)",
                        letterSpacing: "0.2em",
                      }}
                    >
                      LOADING RADAR MAP…
                    </span>
                  </div>
                }
              >
                <FlightRadarMap
                  flights={flights}
                  selectedFlight={selectedFlight}
                  onSelectFlight={handleSelectFlight}
                  theme={theme}
                />
              </Suspense>
            </div>
            <div style={{ position: "absolute", inset: 0, display: mapView === "radar" ? "block" : "none" }}>
              <RadarCanvas
                flights={flights}
                selectedFlight={selectedFlight}
                theme={theme}
                weatherOn={weatherOn}
                weatherDevAccepted={acceptedIds.has("s3")}
              />
            </div>
          </div>
        </BlurFade>

        <BlurFade delay={0.12} direction="left" offset={10} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
          <MetricsRow metricsData={metrics} />
          <AISuggestionsPanel
            suggestions={suggestions}
            onAccept={handleAcceptSuggestion}
            onDismiss={handleDismissSuggestion}
            aiEnabled={aiEnabled}
            acceptedCount={acceptedCount}
          />
          <RunwayStatusPanel />
          <NLPCommsPanel />
          <div className="h-4 shrink-0" />
        </BlurFade>
      </div>

      <TimelinePanel isOpen={timelineOpen} onToggle={() => setTimelineOpen((o) => !o)} />

      <ResolveModal
        open={resolveModalOpen}
        conflict={conflict}
        countdown={conflict?.countdown || 0}
        selectedOption={selectedOption}
        onSelectOption={setSelectedOption}
        onApply={handleApplyResolution}
        onCancel={handleCancelResolution}
      />
      <SuccessToast toast={toast} />

      {/* Flight detail drawer — rendered outside column panels so fixed positioning is viewport-level */}
      <FlightDetailDrawer
        flight={flights.find((f) => f.callsign === selectedFlight) || null}
        onClose={() => handleSelectFlight(null, { surface: "drawer-close" })}
        theme={theme}
      />
    </div>
  );
}
