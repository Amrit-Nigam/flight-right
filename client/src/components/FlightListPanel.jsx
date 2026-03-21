import { useState } from "react";
import { flights, statusColors } from "@/data/mockData";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Plane, Navigation, Clock } from "lucide-react";

const TABS = ["ALL", "LANDING", "TAKEOFF", "ALERTS"];

const filterMap = {
  ALL: () => true,
  LANDING: (f) => f.statusType === "land",
  TAKEOFF: (f) => f.statusType === "take" || f.statusType === "dep",
  ALERTS: (f) => f.statusType === "alert" || f.statusType === "hold",
};

export default function FlightListPanel() {
  const [tab, setTab] = useState("ALL");
  const filtered = flights.filter(filterMap[tab] || filterMap.ALL);

  return (
    <div className="rounded-lg border border-atc-cyan/10 bg-atc-panel/50 flex flex-col h-full">
      <div className="p-3 border-b border-atc-cyan/10">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[10px] font-bold tracking-widest text-atc-text-muted uppercase flex items-center gap-1.5">
            <Plane className="w-3 h-3 text-atc-cyan" />
            Active Flights
          </h3>
          <span className="text-[9px] font-mono text-atc-cyan">{filtered.length}</span>
        </div>

        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <TabsList className="w-full bg-atc-bg/60 h-7 p-0.5">
            {TABS.map((t) => (
              <TabsTrigger
                key={t}
                value={t}
                className="flex-1 text-[9px] font-mono tracking-wider h-6 data-[state=active]:bg-atc-cyan/10 data-[state=active]:text-atc-cyan"
              >
                {t}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {filtered.map((flight) => {
            const color = statusColors[flight.statusType] || "#00c8ff";
            const isAlert = flight.statusType === "alert";

            return (
              <div
                key={flight.callsign}
                className={`group rounded-md border p-2.5 cursor-pointer transition-all hover:border-opacity-40 ${
                  isAlert
                    ? "border-atc-danger/30 bg-atc-danger/5 animate-conflict-pulse"
                    : "border-white/5 bg-white/[0.02] hover:bg-white/[0.04]"
                }`}
                style={{ borderLeftColor: color, borderLeftWidth: "3px" }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono font-bold" style={{ color }}>
                    {flight.callsign}
                  </span>
                  <span
                    className="text-[8px] font-mono tracking-wider px-1.5 py-0.5 rounded"
                    style={{ color, background: color + "15", border: `1px solid ${color}30` }}
                  >
                    {flight.status}
                  </span>
                </div>

                <p className="text-[10px] text-atc-text-secondary mb-1.5">{flight.route}</p>

                <div className="flex items-center gap-3 text-[9px] text-atc-text-muted font-mono">
                  <span className="flex items-center gap-1">
                    <Navigation className="w-2.5 h-2.5" />
                    {flight.altitude}
                  </span>
                  <span>{flight.speed} kt</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    {flight.etaMin > 0 ? `${flight.etaMin}m` : "NOW"}
                  </span>
                  <span className="text-[8px] opacity-50">{flight.aircraft}</span>
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
