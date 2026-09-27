// Display helpers for flight status: colours, icons, urgency order and altitude bands.
// Moved out of data/mockData.js on 27 Sep 2026 when the mock data itself was deleted: these
// are presentation rules, not data. HOLDING is kept for the colour map only; nothing derives it.

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
