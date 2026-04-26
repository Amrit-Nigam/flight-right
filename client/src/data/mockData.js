// ========== FLIGHTS ==========
export const initialFlights = [
  { callsign: "AI6302", route: "BOM→DEL", status: "CONFLICT", altitude: "FL280", speed: "420 kt", eta: "34m", aircraft: "B737", heading: 45, squawk: "7700", fuel: "4.2h", waypoint: "DEGAN", cpaPair: "SG881", cpaSeconds: 260 },
  { callsign: "SG881",  route: "HYD→BOM", status: "HOLDING",  altitude: "FL270", speed: "210 kt", eta: "22m", aircraft: "A320", heading: 320, squawk: "5502", fuel: "3.1h", waypoint: "DEGAN", cpaPair: "AI6302", cpaSeconds: 260 },
  { callsign: "EK512",  route: "DXB→BOM", status: "LANDING",  altitude: "4800ft", speed: "165 kt", eta: "8m",  aircraft: "B777", heading: 272, squawk: "2341", fuel: "1.2h", waypoint: "27L ILS" },
  { callsign: "9W445",  route: "BOM→CCU", status: "TAKEOFF",  altitude: "1200ft", speed: "190 kt", eta: "NOW", aircraft: "B737", heading: 90,  squawk: "4412", fuel: "5.8h", waypoint: "DISHA" },
  { callsign: "UK965",  route: "MAA→DEL", status: "CRUISE",   altitude: "FL350",  speed: "470 kt", eta: "55m", aircraft: "A321", heading: 15,  squawk: "3301", fuel: "6.4h", waypoint: "ARSIN" },
  { callsign: "6E741",  route: "DEL→BOM", status: "APPROACH", altitude: "6200ft", speed: "180 kt", eta: "14m", aircraft: "A320", heading: 265, squawk: "2201", fuel: "0.8h", waypoint: "27R ILS" },
  { callsign: "QR552",  route: "BOM→DOH", status: "DEPARTING",altitude: "GND",    speed: "0 kt",   eta: "NOW", aircraft: "B787", heading: 90,  squawk: "5561", fuel: "9.2h", waypoint: "RWY 09L" },
  { callsign: "BA118",  route: "LHR→BOM", status: "CRUISE",   altitude: "FL390",  speed: "490 kt", eta: "88m", aircraft: "B777", heading: 110, squawk: "1145", fuel: "7.1h", waypoint: "OKLOV" },
  { callsign: "AA258",  route: "ORD→BOM", status: "APPROACH", altitude: "9400ft", speed: "200 kt", eta: "18m", aircraft: "B787", heading: 268, squawk: "3312", fuel: "1.5h", waypoint: "32L VISU" },
  { callsign: "G8423",  route: "COK→BOM", status: "HOLDING",  altitude: "FL140",  speed: "215 kt", eta: "30m", aircraft: "ATR72",heading: 180, squawk: "4401", fuel: "2.2h", waypoint: "DEGAN" },
  { callsign: "IX304",  route: "AMD→BOM", status: "LANDING",  altitude: "3100ft", speed: "155 kt", eta: "5m",  aircraft: "A320", heading: 270, squawk: "2442", fuel: "0.6h", waypoint: "27L FINAL" },
  { callsign: "LD501",  route: "BOM→PNQ", status: "TAKEOFF",  altitude: "2400ft", speed: "210 kt", eta: "NOW", aircraft: "ATR72",heading: 95,  squawk: "4413", fuel: "3.1h", waypoint: "RWY 09R" },
];

// ========== RADAR FLIGHTS & ENVIRONMENT ==========
export const radarFlights = [
  { callsign: "AI6302", xPct: 62, yPct: 38, heading: 45,  status: "conflict", altitude: "FL280", speed: 420 },
  { callsign: "SG881",  xPct: 55, yPct: 42, heading: 320, status: "holding",  altitude: "FL270", speed: 210 },
  { callsign: "EK512",  xPct: 40, yPct: 60, heading: 272, status: "landing",  altitude: "4800ft", speed: 165 },
  { callsign: "9W445",  xPct: 48, yPct: 52, heading: 90,  status: "takeoff",  altitude: "1200ft", speed: 190 },
  { callsign: "UK965",  xPct: 70, yPct: 30, heading: 15,  status: "cruise",   altitude: "FL350", speed: 470 },
  { callsign: "6E741",  xPct: 35, yPct: 55, heading: 265, status: "landing",  altitude: "6200ft", speed: 180 },
  { callsign: "QR552",  xPct: 50, yPct: 50, heading: 90,  status: "takeoff",  altitude: "GND",   speed: 0 },
  { callsign: "BA118",  xPct: 25, yPct: 25, heading: 110, status: "cruise",   altitude: "FL390", speed: 490 },
  { callsign: "AA258",  xPct: 30, yPct: 65, heading: 268, status: "landing",  altitude: "9400ft", speed: 200 },
  { callsign: "G8423",  xPct: 58, yPct: 58, heading: 180, status: "holding",  altitude: "FL140", speed: 215 },
  { callsign: "IX304",  xPct: 44, yPct: 62, heading: 270, status: "landing",  altitude: "3100ft", speed: 155 },
  { callsign: "LD501",  xPct: 52, yPct: 48, heading: 95,  status: "takeoff",  altitude: "2400ft", speed: 210 },
];

export const weatherCell = [
  { xPct: 20, yPct: 20 },
  { xPct: 32, yPct: 22 },
  { xPct: 35, yPct: 30 },
  { xPct: 25, yPct: 38 },
  { xPct: 15, yPct: 32 },
];

export const deviationRoutes = {
  "BA118": [
    { xPct: 25, yPct: 25 },
    { xPct: 38, yPct: 18 },
    { xPct: 45, yPct: 30 },
  ]
};

// ========== METRICS ==========
export const metrics = [
  { id: "active",    value: "28",    label: "ACTIVE FLIGHTS", delta: "↑3 from 1h",     valueColor: "amber" },
  { id: "ontime",    value: "94.2%", label: "ON-TIME RATE",   delta: "↑2.1% vs avg",   valueColor: "green" },
  { id: "conflicts", value: "2",     label: "AI CONFLICTS",   delta: "Predicting now",  valueColor: "red", pulse: true },
  { id: "aiscore",   value: "87%",   label: "AI OPT SCORE",   delta: "Best today ↑",   valueColor: "teal" },
  { id: "runways",   value: "6",     label: "RWYS ACTIVE",    delta: "2L 2R 3L 3R 5A 5B", valueColor: "amber" },
  { id: "wind",      value: "18 kt", label: "WIND SPEED",     delta: "270° NW",         valueColor: "text_primary" },
  { id: "vis",       value: "7 km",  label: "VISIBILITY",     delta: "CLR — No IMC",    valueColor: "green" },
  { id: "spacing",   value: "1.4m",  label: "AVG SPACING",    delta: "↑ AI Optimized",  valueColor: "teal" },
];

// ========== INITIAL CONFLICT ==========
export const initialConflict = {
  visible: true,
  countdown: 260,
  flight1: "AI6302",
  flight2: "SG881",
  detail: "AI6302 (FL280, hdg 045°) vs SG881 (FL270, hdg 320°) — Estimated CPA: 2.1 NM — Below 3 NM minimum separation",
  // Geometry for mini trajectory diagram
  f1: { x: 0.72, y: 0.30, heading: 45,  label: "AI6302", altitude: "FL280", speed: 420 },
  f2: { x: 0.28, y: 0.68, heading: 320, label: "SG881",  altitude: "FL270", speed: 210 },
  cpaNM: 2.1,
};

// ========== RESOLVE OPTIONS ==========
export const resolveOptions = [
  {
    id: "OPT_1", recommended: true,
    label: "OPTION 1 — ALTITUDE SEPARATION",
    action: "Descend AI6302 → FL260. Issue heading 020° to SG881.",
    result: "Separation increases to 4.2 NM. Resolves in 2 min 40 sec.",
    confidence: "97.4%",
    atcoMatch: "94%",
    atcoCases: 847,
    fuelImpact: "+140 kg",
    delayImpact: "+2 min AI6302",
    xaiReason: "Altitude separation matches ATCO strategy for head-on conflicts at FL270–FL280 (based on 847 similar resolved cases). Least fuel penalty. Historically accepted 94% of the time by controllers in this sector.",
  },
  {
    id: "OPT_2", recommended: false,
    label: "OPTION 2 — LATERAL SEPARATION",
    action: "Turn AI6302 left heading 010°. No altitude change.",
    result: "Separation increases to 3.6 NM. Resolves in 3 min 10 sec.",
    confidence: "84.1%",
    atcoMatch: "78%",
    atcoCases: 312,
    fuelImpact: "+80 kg",
    delayImpact: "+1 min AI6302",
    xaiReason: "Lateral turn preferred when altitude bands are congested. Lower ATCO match rate due to higher separation margins needed at these speeds.",
  },
  {
    id: "OPT_3", recommended: false,
    label: "OPTION 3 — SPEED REDUCTION",
    action: "Reduce SG881 speed to 180 kt. Hold pattern at DEGAN.",
    result: "Separation increases to 3.4 NM. Resolves in 4 min 00 sec.",
    confidence: "71.8%",
    atcoMatch: "61%",
    atcoCases: 128,
    fuelImpact: "+220 kg",
    delayImpact: "+6 min SG881",
    xaiReason: "Speed reduction used as last resort when other aircraft are restricted. Higher fuel cost and delay. Least preferred by controllers in historical data.",
  },
];

// ========== TIMELINE ==========
export const timelineRows = [
  { flight: "EK512", aiManaged: false, bars: [{ type: "landing",  startMin: 5,  dur: 18, label: "ILS RWY 27L" }] },
  { flight: "9W445", aiManaged: false, bars: [{ type: "takeoff",  startMin: 12, dur: 10, label: "DEP RWY 09R" }] },
  { flight: "AI6302", aiManaged: false, bars: [{ type: "conflict", startMin: 35, dur: 6,  label: "⚡ CONFLICT · SG881 · 04:20" }] },
  { flight: "SG881", aiManaged: false, bars: [{ type: "holding",  startMin: 30, dur: 20, label: "HOLD DEGAN [exit ~14:02]", holdExit: "14:02" }] },
  { flight: "6E741", aiManaged: false, bars: [{ type: "landing",  startMin: 45, dur: 15, label: "ILS RWY 27R" }] },
  { flight: "QR552", aiManaged: false, bars: [{ type: "takeoff",  startMin: 50, dur: 12, label: "DEP RWY 09L" }] },
  { flight: "UK965", aiManaged: true,  bars: [{ type: "cruise",   startMin: 0,  dur: 60, label: "FL350" }] },
  { flight: "BA118", aiManaged: true,  bars: [{ type: "cruise",   startMin: 20, dur: 60, label: "FL390" }] },
  {
    flight: "G8423", aiManaged: true,
    bars: [{
      type: "optimized", startMin: 58, dur: 14, label: "✦ AI RESEQ",
      xaiDetail: "AI moved G8423 from 14:08 → 14:14 to avoid runway conflict with 6E741 at RWY 27R. Confidence: 91%. Fuel saved: 180 kg.",
    }],
  },
];

// ========== AI SUGGESTIONS ==========
export const initialSuggestions = [
  { id: "s1", type: "CONFLICT",  typeColor: "#ff2d2d", priority: "CRITICAL", confidence: "97.4%", flights: ["AI6302", "SG881"], text: "Descend AI6302 to FL260 immediately. Issue heading 020° to SG881. Separation increases to 4.2 NM. Resolves in 2 min 40 sec.", autoApplicable: false, actionToast: "Separation maneuver executed for AI6302 & SG881" },
  { id: "s2", type: "MEDICAL",   typeColor: "#ff2d2d", priority: "CRITICAL", confidence: "99.1%", flights: ["IX304"],           text: "MEDICAL EMERGENCY declared. Recommend clearing RWY 27L of all departures. Vector IX304 directly to final approach fix. Priority auto-granted.", autoApplicable: true, actionToast: "Medical Priority granted to IX304. RWY 27L cleared." },
  { id: "s3", type: "WEATHER",   typeColor: "#ffdd00", priority: "HIGH",     confidence: "92.0%", flights: ["BA118"],           text: "Severe thunderstorm cell developing at 25NM NW. Recommend 20-degree right deviation for BA118.", autoApplicable: true, actionToast: "Weather deviation approved for BA118 via datalink." },
  { id: "s4", type: "SEQUENCE",  typeColor: "#f5a623", priority: "MEDIUM",   confidence: "88.7%", flights: ["G8423", "6E741", "AA258"], text: "AI resequenced landing queue: 6E741 → EK512 → AA258 → G8423. Reduces total holding fuel burn by 340 kg.", autoApplicable: true, actionToast: "Resequencing applied to arrival flow." },
];

// ========== AI AUDIT LOG ==========
export const aiAuditLog = [
  { time: "14:38", action: "Resequenced G8423 14:08 → 14:14 (avoid RWY 27R conflict with 6E741)", flight: "G8423", outcome: "accepted", by: "A. Sharma", confidence: "91%" },
  { time: "14:37", action: "Flagged AI6302 × SG881 conflict — CPA 2.1 NM in 04:20 at time of detection", flight: "AI6302, SG881", outcome: "pending", by: null, confidence: "97.4%" },
  { time: "14:35", action: "Suggested hold for SG881 at DEGAN — accepted with modification (FL270 instead of FL260)", flight: "SG881", outcome: "modified", by: "A. Sharma", confidence: "88%" },
  { time: "14:33", action: "Optimized landing sequence: EK512 → IX304 → AA258 on RWY 27L", flight: "EK512, IX304", outcome: "accepted", by: "A. Sharma", confidence: "91.2%" },
  { time: "14:30", action: "Issued QNH update advisory for BA118 (wind shift forecast 250°→300°)", flight: "BA118", outcome: "rejected", by: "A. Sharma", confidence: "84%" },
];

// ========== RUNWAYS ==========
export const runways = [
  { 
    id: "RWY 27L", type: "LAND", 
    slots: [{type:"land",pctStart:5,pctW:12,flight:"EK512"},{type:"clear",pctStart:17,pctW:14},{type:"land",pctStart:31,pctW:10,flight:"IX304"},{type:"clear",pctStart:41,pctW:11},{type:"land",pctStart:52,pctW:14,flight:"AA258"},{type:"clear",pctStart:66,pctW:34}],
    balancedSlots: [{type:"land",pctStart:5,pctW:12,flight:"EK512"},{type:"clear",pctStart:17,pctW:35},{type:"land",pctStart:52,pctW:14,flight:"AA258"},{type:"clear",pctStart:66,pctW:34}]
  },
  { 
    id: "RWY 27R", type: "LAND", 
    slots: [{type:"clear",pctStart:0,pctW:10},{type:"land",pctStart:10,pctW:11,flight:"6E741"},{type:"clear",pctStart:21,pctW:20},{type:"land",pctStart:41,pctW:10,flight:"G8423"},{type:"clear",pctStart:51,pctW:49}],
    balancedSlots: [{type:"clear",pctStart:0,pctW:10},{type:"land",pctStart:10,pctW:11,flight:"6E741"},{type:"clear",pctStart:21,pctW:10}, {type:"land",pctStart:31,pctW:10,flight:"IX304"}, {type:"clear",pctStart:41,pctW:15}, {type:"land",pctStart:56,pctW:10,flight:"G8423"}]
  },
  { 
    id: "RWY 09L", type: "DEP",  
    slots: [{type:"clear",pctStart:0,pctW:18},{type:"take",pctStart:18,pctW:8,flight:"QR552"},{type:"clear",pctStart:26,pctW:74}],
    balancedSlots: [{type:"clear",pctStart:0,pctW:18},{type:"take",pctStart:18,pctW:8,flight:"QR552"},{type:"clear",pctStart:26,pctW:10},{type:"take",pctStart:36,pctW:7,flight:"9W445"},{type:"clear",pctStart:43,pctW:57}]
  },
  { 
    id: "RWY 09R", type: "DEP",  
    slots: [{type:"take",pctStart:0,pctW:7,flight:"9W445"},{type:"clear",pctStart:7,pctW:18},{type:"take",pctStart:25,pctW:6,flight:"LD501"},{type:"clear",pctStart:31,pctW:69}],
    balancedSlots: [{type:"clear",pctStart:0,pctW:25},{type:"take",pctStart:25,pctW:6,flight:"LD501"},{type:"clear",pctStart:31,pctW:69}]
  },
  { id: "RWY 32L", type: "MAINT", slots: [{type:"maint",pctStart:0,pctW:30,label:"MAINTENANCE"},{type:"clear",pctStart:30,pctW:70}], balancedSlots: [{type:"maint",pctStart:0,pctW:30,label:"MAINTENANCE"},{type:"clear",pctStart:30,pctW:70}] },
  { id: "RWY 32R", type: "LAND", slots: [{type:"clear",pctStart:0,pctW:40},{type:"land",pctStart:40,pctW:15,flight:"BA118"},{type:"clear",pctStart:55,pctW:45}], balancedSlots: [{type:"clear",pctStart:0,pctW:40},{type:"land",pctStart:40,pctW:15,flight:"BA118"},{type:"clear",pctStart:55,pctW:45}] },
];

// ========== NLP COMMS ==========
export const nlpComms = [
  { time: "14:34:12", type: "ATC",   flight: "EK512",  text: "Emirates five-one-two, descend and maintain four thousand feet, reduce speed one-six-zero knots, cleared ILS approach runway two-seven-left." },
  { time: "14:34:28", type: "PILOT", flight: "EK512",  text: "Descend maintain four thousand, reduce one-six-zero, cleared ILS two-seven-left, Emirates five-one-two." },
  { time: "14:35:01", type: "AI",    flight: "SYSTEM", text: "⚡ Conflict detected. Suggested: 'Air India six-three-zero-two, turn left heading zero-two-zero, descend flight level two-six-zero immediately.'" },
  { time: "14:35:44", type: "ATC",   flight: "SG881",  text: "SpiceJet eight-eight-one, enter holding at DEGAN, maintain flight level two-seven-zero, expect further clearance at one-five-zero-zero." },
  { time: "14:36:20", type: "PILOT", flight: "UK965",  text: "AeroSync, Vistara nine-six-five requesting clearance direct to ARSIN." },
  { 
    time: "14:36:22", type: "AI DRAFT", flight: "UK965", 
    text: "DIRECT TO ARSIN APPROVED. MAINTAIN FL350.", 
    interactive: true, datalink: true 
  },
  { time: "14:37:08", type: "ATC",   flight: "QR552",  text: "Qatar five-five-two, pushback and startup approved, QNH one-zero-one-two, ATIS Kilo." },
];

// ========== WEATHER ==========
export const weather = {
  metar: "VABB 211200Z 27018KT 7200 FEW030 28/22 Q1012 NOSIG",
  atis: "ATIS KILO",
  wind: "270° / 18 kt (G24)",
  visibility: "7,200 m",
  ceiling: "FEW030",
  tempDp: "28° / 22°",
  qnh: "Q1012",
  activeRwys: "LAND: 27L/27R | DEP: 09L/09R",
};

// ========== STATUS COLORS MAP ==========
export const statusColors = {
  CONFLICT:  "#ff2d2d",
  HOLDING:   "#ffdd00",
  LANDING:   "#00e5cc",
  TAKEOFF:   "#f5a623",
  CRUISE:    "#8a7d65",
  APPROACH:  "#00e5cc",
  DEPARTING: "#f5a623",
  ENROUTE:   "#8a7d65",
};

/** Darker / WCAG-friendlier on light panels */
export const statusColorsLight = {
  CONFLICT:  "#b91c1c",
  HOLDING:   "#a16207",
  LANDING:   "#0f766e",
  TAKEOFF:   "#b45309",
  CRUISE:    "#57534e",
  APPROACH:  "#0f766e",
  DEPARTING: "#b45309",
  ENROUTE:   "#57534e",
};

export const statusIcons = {
  LANDING:   "↘",
  TAKEOFF:   "↗",
  CRUISE:    "→",
  HOLDING:   "⏸",
  CONFLICT:  "⚡",
  DEPARTING: "◈",
  APPROACH:  "↘",
  ENROUTE:   "→",
};

// ========== ALTITUDE URGENCY SORT ==========
const STATUS_PRIORITY = {
  CONFLICT: 0, HOLDING: 1, APPROACH: 2, LANDING: 2,
  TAKEOFF: 3, DEPARTING: 3, CRUISE: 4, ENROUTE: 5,
};
export function sortByUrgency(flights) {
  return [...flights].sort((a, b) => {
    const pa = STATUS_PRIORITY[a.status] ?? 9;
    const pb = STATUS_PRIORITY[b.status] ?? 9;
    if (pa !== pb) return pa - pb;
    // Within same priority, sort by CPA seconds if available
    const ca = a.cpaSeconds ?? Infinity;
    const cb = b.cpaSeconds ?? Infinity;
    return ca - cb;
  });
}

// ========== ALTITUDE BAND COUNTS ==========
function parseFL(alt) {
  if (!alt || alt === "GND") return 0;
  if (alt.startsWith("FL")) return parseInt(alt.slice(2), 10);
  const ft = parseInt(alt.replace(/[^0-9]/g, ""), 10);
  return Math.round(ft / 100);
}
export function getAltBandCounts(flights) {
  const under100  = flights.filter(f => parseFL(f.altitude) < 100).length;
  const band100250 = flights.filter(f => { const fl = parseFL(f.altitude); return fl >= 100 && fl <= 250; }).length;
  const over250   = flights.filter(f => parseFL(f.altitude) > 250).length;
  return { under100, band100250, over250 };
}
