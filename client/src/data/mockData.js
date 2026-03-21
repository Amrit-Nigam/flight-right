// ========== FLIGHTS ==========
export const flights = [
  { callsign: "AI6302", route: "BOM → DEL", status: "CONFLICT", statusType: "alert", altitude: "FL280", heading: 45, speed: 420, aircraft: "B737", phase: "enroute", etaMin: 34 },
  { callsign: "SG881", route: "HYD → BOM", status: "HOLDING", statusType: "hold", altitude: "FL270", heading: 320, speed: 210, aircraft: "A320", phase: "holding", etaMin: 22 },
  { callsign: "EK512", route: "DXB → BOM", status: "LANDING", statusType: "land", altitude: "4,800 ft", heading: 272, speed: 165, aircraft: "B777", phase: "approach", etaMin: 8 },
  { callsign: "9W445", route: "BOM → CCU", status: "TAKEOFF", statusType: "take", altitude: "1,200 ft", heading: 90, speed: 190, aircraft: "B737", phase: "climb", etaMin: 0 },
  { callsign: "UK965", route: "MAA → DEL", status: "CRUISE", statusType: "cruise", altitude: "FL350", heading: 15, speed: 470, aircraft: "A321", phase: "cruise", etaMin: 55 },
  { callsign: "6E741", route: "DEL → BOM", status: "APPROACH", statusType: "land", altitude: "6,200 ft", heading: 265, speed: 180, aircraft: "A320", phase: "approach", etaMin: 14 },
  { callsign: "QR552", route: "BOM → DOH", status: "DEPARTING", statusType: "dep", altitude: "GND", heading: 90, speed: 0, aircraft: "B787", phase: "taxi", etaMin: 0 },
  { callsign: "BA118", route: "LHR → BOM", status: "CRUISE", statusType: "cruise", altitude: "FL390", heading: 110, speed: 490, aircraft: "B777", phase: "cruise", etaMin: 88 },
  { callsign: "AA258", route: "ORD → BOM", status: "APPROACH", statusType: "land", altitude: "9,400 ft", heading: 268, speed: 200, aircraft: "B787", phase: "approach", etaMin: 18 },
  { callsign: "G8423", route: "COK → BOM", status: "HOLDING", statusType: "hold", altitude: "FL140", heading: 180, speed: 215, aircraft: "ATR72", phase: "holding", etaMin: 30 },
  { callsign: "SJ302", route: "BOM → SIN", status: "CRUISE", statusType: "cruise", altitude: "FL370", heading: 135, speed: 460, aircraft: "A330", phase: "cruise", etaMin: 210 },
  { callsign: "TK718", route: "IST → BOM", status: "CRUISE", statusType: "cruise", altitude: "FL360", heading: 120, speed: 480, aircraft: "B777", phase: "cruise", etaMin: 75 },
  { callsign: "IX304", route: "AMD → BOM", status: "LANDING", statusType: "land", altitude: "3,100 ft", heading: 270, speed: 155, aircraft: "A320", phase: "final", etaMin: 5 },
  { callsign: "LD501", route: "BOM → PNQ", status: "TAKEOFF", statusType: "take", altitude: "2,400 ft", heading: 95, speed: 210, aircraft: "ATR72", phase: "climb", etaMin: 0 },
];

// ========== RADAR FLIGHTS ==========
export const radarFlights = [
  { callsign: "AI6302", xPct: 62, yPct: 38, heading: 45, status: "conflict", altitude: "FL280", speed: 420 },
  { callsign: "SG881", xPct: 55, yPct: 42, heading: 320, status: "holding", altitude: "FL270", speed: 210 },
  { callsign: "EK512", xPct: 40, yPct: 60, heading: 272, status: "landing", altitude: "4800ft", speed: 165 },
  { callsign: "9W445", xPct: 48, yPct: 52, heading: 90, status: "takeoff", altitude: "1200ft", speed: 190 },
  { callsign: "UK965", xPct: 70, yPct: 30, heading: 15, status: "cruise", altitude: "FL350", speed: 470 },
  { callsign: "6E741", xPct: 35, yPct: 55, heading: 265, status: "landing", altitude: "6200ft", speed: 180 },
  { callsign: "QR552", xPct: 50, yPct: 50, heading: 90, status: "takeoff", altitude: "GND", speed: 0 },
  { callsign: "BA118", xPct: 25, yPct: 25, heading: 110, status: "cruise", altitude: "FL390", speed: 490 },
  { callsign: "AA258", xPct: 30, yPct: 65, heading: 268, status: "landing", altitude: "9400ft", speed: 200 },
  { callsign: "G8423", xPct: 58, yPct: 58, heading: 180, status: "holding", altitude: "FL140", speed: 215 },
  { callsign: "SJ302", xPct: 72, yPct: 65, heading: 135, status: "cruise", altitude: "FL370", speed: 460 },
  { callsign: "TK718", xPct: 20, yPct: 35, heading: 120, status: "cruise", altitude: "FL360", speed: 480 },
  { callsign: "IX304", xPct: 44, yPct: 62, heading: 270, status: "landing", altitude: "3100ft", speed: 155 },
  { callsign: "LD501", xPct: 52, yPct: 48, heading: 95, status: "takeoff", altitude: "2400ft", speed: 210 },
];

// ========== METRICS ==========
export const metrics = [
  { id: "active_flights", value: 28, label: "Active Flights", delta: "↑ 3 from 1hr ago", deltaType: "up", color: "cyan" },
  { id: "on_time_rate", value: "94.2%", label: "On-Time Rate", delta: "↑ 2.1% vs avg", deltaType: "up", color: "green" },
  { id: "conflicts", value: 2, label: "AI Conflicts", delta: "— Predicting now", deltaType: "neutral", color: "warning" },
  { id: "ai_score", value: "87%", label: "AI Opt. Score", delta: "↑ Best today", deltaType: "up", color: "accent_green" },
  { id: "runways", value: 6, label: "Runways Active", delta: "2L 2R 3L 3R 5A 5B", deltaType: "neutral", color: "text" },
  { id: "wind", value: "18 kt", label: "Wind Speed", delta: "DIR: 270° NW", deltaType: "neutral", color: "purple" },
  { id: "visibility", value: "7,200 m", label: "Visibility", delta: "CLR — No IMC", deltaType: "up", color: "cyan" },
  { id: "spacing", value: "1.4 min", label: "Avg Spacing", delta: "↑ AI Optimized", deltaType: "up", color: "green" },
];

// ========== CONFLICT ALERT ==========
export const conflictAlert = {
  visible: true,
  icon: "⚡",
  title: "POTENTIAL CONFLICT — AI PREDICTED IN 4 MIN 20 SEC",
  detail: "AI6302 (FL280, hdg 045°) vs SG881 (FL270, hdg 320°) — Estimated CPA: 2.1 NM — Below 3 NM minimum separation",
  actionButton: "RESOLVE NOW",
  countdownStartSeconds: 260,
};

// ========== TIMELINE ==========
export const timelineRows = [
  { flight: "EK512", type: "landing", startMin: 5, durationMin: 18, label: "ILS RWY 27L" },
  { flight: "9W445", type: "takeoff", startMin: 12, durationMin: 10, label: "DEP RWY 09R" },
  { flight: "AI6302", type: "conflict", startMin: 35, durationMin: 6, label: "⚡ CONFLICT ZONE" },
  { flight: "SG881", type: "holding", startMin: 30, durationMin: 20, label: "HOLD DEGAN" },
  { flight: "6E741", type: "landing", startMin: 45, durationMin: 15, label: "ILS RWY 27R" },
  { flight: "QR552", type: "takeoff", startMin: 50, durationMin: 12, label: "DEP RWY 09L" },
  { flight: "UK965", type: "cruise", startMin: 0, durationMin: 60, label: "FL350 ENROUTE" },
  { flight: "BA118", type: "cruise", startMin: 20, durationMin: 60, label: "FL390 ENROUTE" },
  { flight: "G8423", type: "optimized", startMin: 58, durationMin: 14, label: "✦ AI RESEQUENCED" },
  { flight: "AA258", type: "landing", startMin: 70, durationMin: 16, label: "VISUAL RWY 32L" },
];

// ========== WEATHER ==========
export const weather = {
  station: "VABB (Mumbai CSIA)",
  metar: "VABB 211200Z 27018KT 7200 FEW030 28/22 Q1012 NOSIG",
  atisLetter: "K",
  conditions: [
    { label: "Wind", value: "270° / 18 kt", sub: "Max gust: 24 kt" },
    { label: "Visibility", value: "7,200 m", sub: "No significant Wx" },
    { label: "Ceiling", value: "FEW030 (3,000 ft)", sub: "No CB observed" },
    { label: "Temperature", value: "28°C / 22°C", sub: "Dew point 22°C" },
    { label: "QNH", value: "1012 hPa", sub: "Q1012" },
    { label: "Active Rwy", value: "27L / 27R (Land)", sub: "09L / 09R (Dep)" },
  ],
  trend: "NOSIG",
  windShearAlert: false,
  turbulenceLevel: "NIL",
  icing: "NIL",
};

// ========== AI SUGGESTIONS ==========
export const aiSuggestions = [
  {
    id: "s1", type: "CONFLICT", typeColor: "danger", confidence: "97.4%",
    flightRefs: ["AI6302", "SG881"], priority: "CRITICAL", autoAppliable: false,
    text: "Descend AI6302 to FL260 immediately. Issue heading 020° to SG881 to increase lateral separation. Resolves in 2 min 40 sec.",
  },
  {
    id: "s2", type: "OPTIMIZE", typeColor: "accent_green", confidence: "91.2%",
    flightRefs: ["EK512", "IX304"], priority: "HIGH", autoAppliable: true,
    text: "Sequence EK512 before IX304 on RWY 27L. EK512 heavier (B777), IX304 lighter (A320). Saves 3.2 min total delay.",
  },
  {
    id: "s3", type: "WEATHER", typeColor: "warning", confidence: "84.0%",
    flightRefs: ["BA118"], priority: "MEDIUM", autoAppliable: false,
    text: "Wind shift expected in 22 min (250° → 300°). Recommend issuing updated QNH to BA118 on approach. Pre-brief crew.",
  },
  {
    id: "s4", type: "SEQUENCE", typeColor: "accent_cyan", confidence: "88.7%",
    flightRefs: ["G8423", "6E741", "AA258"], priority: "MEDIUM", autoAppliable: true,
    text: "AI resequenced landing queue: 6E741 → EK512 → AA258 → G8423. Reduces total holding fuel burn by 340 kg.",
  },
  {
    id: "s5", type: "OPTIMIZE", typeColor: "accent_green", confidence: "79.5%",
    flightRefs: ["QR552"], priority: "LOW", autoAppliable: true,
    text: "QR552 pushback approved. Estimated runway hold time: 4 min. Taxi via Alpha-7, Bravo-3, hold short RWY 09L.",
  },
];

// ========== RUNWAYS ==========
export const runways = [
  {
    id: "RWY 27L", type: "landing",
    slots: [
      { type: "land", flight: "EK512", startPct: 5, widthPct: 12 },
      { type: "clear", startPct: 17, widthPct: 15 },
      { type: "land", flight: "IX304", startPct: 32, widthPct: 10 },
      { type: "clear", startPct: 42, widthPct: 10 },
      { type: "land", flight: "AA258", startPct: 52, widthPct: 14 },
      { type: "clear", startPct: 66, widthPct: 34 },
    ],
  },
  {
    id: "RWY 27R", type: "landing",
    slots: [
      { type: "clear", startPct: 0, widthPct: 10 },
      { type: "land", flight: "6E741", startPct: 10, widthPct: 11 },
      { type: "clear", startPct: 21, widthPct: 20 },
      { type: "land", flight: "G8423", startPct: 41, widthPct: 10 },
      { type: "clear", startPct: 51, widthPct: 49 },
    ],
  },
  {
    id: "RWY 09L", type: "departure",
    slots: [
      { type: "clear", startPct: 0, widthPct: 18 },
      { type: "take", flight: "QR552", startPct: 18, widthPct: 8 },
      { type: "clear", startPct: 26, widthPct: 74 },
    ],
  },
  {
    id: "RWY 09R", type: "departure",
    slots: [
      { type: "take", flight: "9W445", startPct: 0, widthPct: 7 },
      { type: "clear", startPct: 7, widthPct: 18 },
      { type: "take", flight: "LD501", startPct: 25, widthPct: 6 },
      { type: "clear", startPct: 31, widthPct: 69 },
    ],
  },
  {
    id: "RWY 32L", type: "landing",
    slots: [
      { type: "maint", startPct: 0, widthPct: 30, label: "⚙ MAINTENANCE" },
      { type: "clear", startPct: 30, widthPct: 70 },
    ],
  },
  {
    id: "RWY 32R", type: "mixed",
    slots: [
      { type: "clear", startPct: 0, widthPct: 40 },
      { type: "land", flight: "BA118", startPct: 40, widthPct: 15 },
      { type: "clear", startPct: 55, widthPct: 45 },
    ],
  },
];

// ========== NLP COMMS ==========
export const nlpComms = [
  { time: "14:34:12", type: "atc", flight: "EK512", text: "Emirates five-one-two, descend and maintain four thousand feet, reduce speed one-six-zero knots, cleared ILS approach runway two-seven-left.", aiTranscribed: true },
  { time: "14:34:28", type: "pilot", flight: "EK512", text: "Descend maintain four thousand, reduce one-six-zero, cleared ILS two-seven-left, Emirates five-one-two.", aiTranscribed: true },
  { time: "14:35:01", type: "ai", flight: "AI SYSTEM", text: "⚡ Conflict detected. Suggested phraseology: 'Air India six-three-zero-two, turn left heading zero-two-zero, descend flight level two-six-zero immediately.'", aiTranscribed: false },
  { time: "14:35:44", type: "atc", flight: "SG881", text: "SpiceJet eight-eight-one, enter holding at DEGAN, maintain flight level two-seven-zero, expect further clearance at one-five-zero-zero.", aiTranscribed: true },
  { time: "14:36:10", type: "pilot", flight: "SG881", text: "Entering hold DEGAN, flight level two-seven-zero, EFC one-five-zero-zero, SpiceJet eight-eight-one.", aiTranscribed: true },
  { time: "14:36:55", type: "ai", flight: "AI SYSTEM", text: "✦ Optimized sequence applied: EK512 → IX304 → AA258 on RWY 27L. Estimated delay savings: 3.2 min. Fuel saved: 180 kg.", aiTranscribed: false },
  { time: "14:37:08", type: "atc", flight: "QR552", text: "Qatar five-five-two, pushback and startup approved, QNH one-zero-one-two, ATIS Kilo.", aiTranscribed: true },
];

// ========== OPTIMIZATION ==========
export const optimization = {
  overall: 87,
  label: "Overall AI Score",
  description: "Real-time AI efficiency rating",
  bars: [
    { label: "Landing Seq.", value: 92, color: "#00e676" },
    { label: "Dep. Spacing", value: 85, color: "#00c8ff" },
    { label: "Conflict Avoid.", value: 78, color: "#ff6b35" },
    { label: "Fuel Efficiency", value: 88, color: "#ffd700" },
    { label: "Runway Util.", value: 91, color: "#a855f7" },
    { label: "NLP Accuracy", value: 95, color: "#00ffc8" },
    { label: "Hold Reduction", value: 74, color: "#ffaa00" },
    { label: "On-Time Perf.", value: 94, color: "#00e676" },
  ],
  history: [72, 75, 78, 74, 80, 83, 81, 85, 84, 87, 86, 87],
};

// ========== STATUS COLOR MAP ==========
export const statusColors = {
  landing: "#00e676",
  takeoff: "#00c8ff",
  cruise: "#a855f7",
  holding: "#ffaa00",
  conflict: "#ff3b5c",
  optimized: "#00ffc8",
  land: "#00e676",
  take: "#00c8ff",
  alert: "#ff3b5c",
  hold: "#ffaa00",
  dep: "#00c8ff",
};
