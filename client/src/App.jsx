import { useState, useCallback } from "react";
import TopBar from "@/components/TopBar";
import MetricsRow from "@/components/MetricsRow";
import ConflictBanner from "@/components/ConflictBanner";
import ResolveModal from "@/components/ResolveModal";
import SuccessToast from "@/components/SuccessToast";
import RadarCanvas from "@/components/RadarCanvas";
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

  const alertCount = conflict ? (flights.filter((f) => f.status === "CONFLICT" || f.status === "HOLDING").length > 0 ? 1 : 0) : 0;

  // ===== TOAST HELPER =====
  const showToast = useCallback((message) => {
    setToast({ message, type: "success" });
    setTimeout(() => setToast(null), 4000);
  }, []);

  // ===== CONFLICT RESOLUTION FLOW =====
  const handleResolveClick = () => setResolveModalOpen(true);

  const handleApplyResolution = () => {
    setResolveModalOpen(false);
    setConflict(null);
    setFlights((prev) =>
      prev.map((f) =>
        f.callsign === "AI6302" || f.callsign === "SG881"
          ? { ...f, status: "ENROUTE" }
          : f
      )
    );
    showToast("Resolution Applied — AI6302 & SG881 Separation Secured");
  };

  const handleCancelResolution = () => setResolveModalOpen(false);

  // ===== SUGGESTION FLOW =====
  const handleAcceptSuggestion = (suggestion) => {
    setSuggestions((prev) => prev.filter((s) => s.id !== suggestion.id));
    setAcceptedCount((c) => c + 1);
    showToast(`Applied: ${suggestion.type} — ${suggestion.flights.join(", ")}`);
  };

  const handleDismissSuggestion = (id) => {
    setSuggestions((prev) => prev.filter((s) => s.id !== id));
  };

  // ===== FLIGHT SELECT =====
  const handleSelectFlight = (callsign) => {
    setSelectedFlight(callsign === selectedFlight ? null : callsign);
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      <TopBar alertCount={alertCount} aiEnabled={aiEnabled} onToggleAI={() => setAiEnabled(!aiEnabled)} />

      <div className="flex-1 grid gap-3 p-3 overflow-hidden" style={{ gridTemplateColumns: '260px 1fr 300px', height: 'calc(100vh - 56px)' }}>
        {/* LEFT — Flight List */}
        <FlightListPanel
          flightsData={flights}
          selectedFlight={selectedFlight}
          onSelectFlight={handleSelectFlight}
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />

        {/* CENTER — Main panels */}
        <div className="flex flex-col gap-3 overflow-auto">
          <ConflictBanner conflict={conflict} onResolveClick={handleResolveClick} />
          <MetricsRow metricsData={metrics} />
          <RadarCanvas flights={flights} selectedFlight={selectedFlight} />
          <TimelinePanel />
        </div>

        {/* RIGHT — AI + Runways + Comms */}
        <div className="flex flex-col gap-3 overflow-auto">
          <AISuggestionsPanel
            suggestions={suggestions}
            onAccept={handleAcceptSuggestion}
            onDismiss={handleDismissSuggestion}
            aiEnabled={aiEnabled}
            acceptedCount={acceptedCount}
          />
          <RunwayStatusPanel />
          <NLPCommsPanel />
        </div>
      </div>

      {/* Footer */}
      <div className="text-center py-1.5" style={{ borderTop: '1px solid var(--border-default)' }}>
        <p className="font-display text-[7px] tracking-wider" style={{ color: 'var(--text-muted)' }}>
          All data is simulated for demonstration. AeroSync AI does not replace human controllers — it assists them.
        </p>
      </div>

      {/* Modals / Overlays */}
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