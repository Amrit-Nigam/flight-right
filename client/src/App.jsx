import TopBar from "@/components/TopBar";
import MetricsRow from "@/components/MetricsRow";
import ConflictAlertBanner from "@/components/ConflictAlertBanner";
import RadarCanvas from "@/components/RadarCanvas";
import TimelinePanel from "@/components/TimelinePanel";
import FlightListPanel from "@/components/FlightListPanel";
import WeatherPanel from "@/components/WeatherPanel";
import AISuggestionsPanel from "@/components/AISuggestionsPanel";
import RunwayStatusPanel from "@/components/RunwayStatusPanel";
import NLPCommsPanel from "@/components/NLPCommsPanel";
import OptimizationPanel from "@/components/OptimizationPanel";

function App() {
  return (
    <div className="min-h-screen bg-atc-bg text-atc-text-primary">
      <TopBar />

      <div className="grid grid-cols-[280px_1fr_320px] gap-3 p-3 h-[calc(100vh-57px)]">
        {/* LEFT COLUMN */}
        <div className="flex flex-col gap-3 overflow-hidden">
          <FlightListPanel />
          <WeatherPanel />
        </div>

        {/* CENTER COLUMN */}
        <div className="flex flex-col gap-3 overflow-auto pr-1">
          <MetricsRow />
          <ConflictAlertBanner />
          <RadarCanvas />
          <TimelinePanel />
        </div>

        {/* RIGHT COLUMN */}
        <div className="flex flex-col gap-3 overflow-auto">
          <AISuggestionsPanel />
          <RunwayStatusPanel />
          <NLPCommsPanel />
          <OptimizationPanel />
        </div>
      </div>

      {/* Footer */}
      <div className="text-center py-2 border-t border-atc-cyan/5">
        <p className="text-[8px] text-atc-text-muted/40 font-mono tracking-wider">
          All data is simulated for demonstration. AeroSync AI does not replace human controllers — it assists them.
        </p>
      </div>
    </div>
  );
}

export default App;