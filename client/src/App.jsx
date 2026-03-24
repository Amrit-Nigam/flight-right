import { useState, useCallback, useEffect, lazy, Suspense } from "react";
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
import AISuggestionsPanel from "@/components/AISuggestionsPanel";
import RunwayStatusPanel from "@/components/RunwayStatusPanel";
import NLPCommsPanel from "@/components/NLPCommsPanel";

import { initialFlights, metrics, initialConflict, initialSuggestions } from "@/data/mockData";

function App() {
  // ===== STATE =====
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

  // ===== THEME =====
  const [theme, setTheme] = useState("dark");
  useEffect(() => {
    if (theme === "light") document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
  }, [theme]);
  const toggleTheme = () => setTheme(t => t === "dark" ? "light" : "dark");

  // ===== COMPUTED =====
  const alertCount = conflict
    ? (flights.filter(f => f.status === "CONFLICT" || f.status === "HOLDING").length > 0 ? 1 : 0)
    : 0;

  // ===== TOAST =====
  const showToast = useCallback((message) => {
    setToast({ message, type: "success" });
    setTimeout(() => setToast(null), 4000);
  }, []);

  useEffect(() => {
    const handleToastEvent = (e) => showToast(e.detail);
    window.addEventListener("show-toast", handleToastEvent);
    return () => window.removeEventListener("show-toast", handleToastEvent);
  }, [showToast]);

  // ===== CONFLICT RESOLUTION =====
  const handleResolveClick = () => setResolveModalOpen(true);

  const handleApplyResolution = () => {
    setResolveModalOpen(false);
    setConflict(null);
    setFlights(prev =>
      prev.map(f =>
        f.callsign === "AI6302" || f.callsign === "SG881"
          ? { ...f, status: "ENROUTE", cpaPair: undefined, cpaSeconds: undefined }
          : f
      )
    );
    showToast("Resolution Applied — AI6302 & SG881 Separation Secured");
  };

  const handleCancelResolution = () => setResolveModalOpen(false);

  // ===== SUGGESTIONS =====
  const handleAcceptSuggestion = (suggestion) => {
    setSuggestions(prev => prev.filter(s => s.id !== suggestion.id));
    setAcceptedCount(c => c + 1);
    showToast(`Applied: ${suggestion.type} — ${suggestion.flights.join(", ")}`);
  };
  const handleDismissSuggestion = (id) => setSuggestions(prev => prev.filter(s => s.id !== id));

  // ===== FLIGHT SELECT =====
  const handleSelectFlight = (callsign) =>
    setSelectedFlight(callsign === selectedFlight ? null : callsign);

  // ===== PANEL TOGGLES =====
  const [timelineOpen, setTimelineOpen]   = useState(false);
  const [auditTrailOpen, setAuditTrailOpen] = useState(false);
  const [mapView, setMapView]             = useState("map"); // "map" | "radar"
  const [weatherOn, setWeatherOn]         = useState(false);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      <TopBar
        alertCount={alertCount}
        aiEnabled={aiEnabled}
        onToggleAI={() => setAiEnabled(!aiEnabled)}
        theme={theme}
        onToggleTheme={toggleTheme}
        conflict={conflict}
        weatherOn={weatherOn}
        onWeatherToggle={() => setWeatherOn(w => !w)}
      />

      {/* Conflict Banner */}
      <div className="z-40 w-full relative">
        <ConflictBanner conflict={conflict} onResolveClick={handleResolveClick} />
      </div>

      {/* Main Content */}
      <div className="flex-1 flex gap-4 p-4 overflow-hidden relative">
        {/* LEFT — Flight List */}
        <div className="w-[280px] shrink-0 h-full">
          <FlightListPanel
            flightsData={flights}
            selectedFlight={selectedFlight}
            onSelectFlight={handleSelectFlight}
            activeTab={activeTab}
            onTabChange={setActiveTab}
          />
        </div>

        {/* CENTER — Radar Hero */}
        <div className="w-[55vw] shrink-0 h-full flex flex-col gap-2">
          {/* View toggle row */}
          <div className="flex items-center gap-0 shrink-0" style={{ height: 30 }}>
            {[{ key: "map", label: "MAP VIEW" }, { key: "radar", label: "RADAR SWEEP" }].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setMapView(key)}
                className="font-display text-[11px] tracking-widest px-5 py-1.5 transition-all"
                style={{
                  background: mapView === key ? "var(--amber)" : "transparent",
                  color:      mapView === key ? "#0a0b0e"     : "var(--amber)",
                  border:     "1px solid var(--amber)",
                  marginLeft: key === "radar" ? -1 : 0,
                }}
              >
                {label}
              </button>
            ))}

            {/* WEATHER first-class toggle */}
            <button
              onClick={() => setWeatherOn(w => !w)}
              className="font-display text-[11px] tracking-widest px-4 py-1.5 transition-all ml-2"
              style={{
                background: weatherOn ? "var(--teal)" : "transparent",
                color:      weatherOn ? "#0a0b0e"     : "var(--teal)",
                border:     "1px solid var(--teal)",
              }}
            >
              ☁ WEATHER
            </button>

            {/* AI Audit Trail toggle */}
            <div className="ml-auto relative" style={{ zIndex: 40 }}>
              <AIAuditTrail isOpen={auditTrailOpen} onToggle={() => setAuditTrailOpen(o => !o)} />
            </div>
          </div>

          {/* Map / Radar panels */}
          <div className="flex-1 relative overflow-hidden" style={{ minHeight: 0 }}>
            <div style={{ position: "absolute", inset: 0, display: mapView === "map" ? "block" : "none" }}>
              <Suspense fallback={
                <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#060608" }}>
                  <span style={{ fontFamily: "'Share Tech Mono',monospace", fontSize: 12, color: "var(--text-muted)", letterSpacing: "0.2em" }}>LOADING RADAR MAP…</span>
                </div>
              }>
                <FlightRadarMap
                  flights={flights}
                  selectedFlight={selectedFlight}
                  onSelectFlight={handleSelectFlight}
                  theme={theme}
                />
              </Suspense>
            </div>
            <div style={{ position: "absolute", inset: 0, display: mapView === "radar" ? "block" : "none" }}>
              <RadarCanvas flights={flights} selectedFlight={selectedFlight} theme={theme} />
            </div>
          </div>
        </div>

        {/* RIGHT — Panels */}
        <div className="flex-1 h-full overflow-y-auto flex flex-col gap-4 pr-1">
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
        </div>
      </div>

      {/* BOTTOM — Timeline Drawer */}
      <TimelinePanel isOpen={timelineOpen} onToggle={() => setTimelineOpen(!timelineOpen)} />

      {/* Modals */}
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
    </div>
  );
}

export default App;