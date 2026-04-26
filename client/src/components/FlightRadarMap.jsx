import { useEffect, useRef, useState, useMemo } from "react";
import { logActivity, logAudit } from "@/lib/siteLogger";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// ─── CONSTANTS ─────────────────────────────────────────────────────────────────
const VABB_LAT = 19.0896;
const VABB_LNG = 72.8656;

const INITIAL_FLIGHTS = [
  { callsign: "AI6302", lat: 19.80, lng: 73.85, heading: 45,  speed: 420, altitude: "FL280", status: "conflict" },
  { callsign: "SG881",  lat: 19.45, lng: 72.70, heading: 320, speed: 210, altitude: "FL270", status: "holding" },
  { callsign: "EK512",  lat: 19.25, lng: 72.40, heading: 272, speed: 165, altitude: "4800ft",status: "landing" },
  { callsign: "9W445",  lat: 19.10, lng: 73.00, heading: 90,  speed: 190, altitude: "1200ft",status: "takeoff" },
  { callsign: "UK965",  lat: 20.50, lng: 73.60, heading: 15,  speed: 470, altitude: "FL350", status: "cruise"  },
  { callsign: "6E741",  lat: 19.30, lng: 72.50, heading: 265, speed: 180, altitude: "6200ft",status: "approach"},
  { callsign: "QR552",  lat: 19.09, lng: 72.86, heading: 90,  speed: 0,   altitude: "GND",   status: "departing"},
  { callsign: "BA118",  lat: 21.20, lng: 71.50, heading: 110, speed: 490, altitude: "FL390", status: "cruise"  },
  { callsign: "AA258",  lat: 19.50, lng: 72.30, heading: 268, speed: 200, altitude: "9400ft",status: "approach"},
  { callsign: "G8423",  lat: 18.20, lng: 73.10, heading: 180, speed: 215, altitude: "FL140", status: "holding" },
  { callsign: "TK718",  lat: 22.10, lng: 72.00, heading: 120, speed: 480, altitude: "FL360", status: "cruise"  },
  { callsign: "IX304",  lat: 19.15, lng: 72.55, heading: 270, speed: 155, altitude: "3100ft",status: "landing" },
  { callsign: "LD501",  lat: 19.12, lng: 72.92, heading: 95,  speed: 210, altitude: "2400ft",status: "takeoff" },
  { callsign: "SJ302",  lat: 17.50, lng: 74.20, heading: 135, speed: 460, altitude: "FL370", status: "cruise"  },
];

const STATUS_COLORS_DARK = {
  landing: "#00e5cc", approach: "#00e5cc",
  takeoff: "#f5a623", cruise: "#f5a623", departing: "#f5a623",
  holding: "#ffdd00",
  conflict: "#ff2d2d",
};
const STATUS_COLORS_LIGHT = {
  landing: "#0f766e", approach: "#0f766e",
  takeoff: "#b45309", cruise: "#64748b", departing: "#b45309",
  holding: "#a16207",
  conflict: "#b91c1c",
};

const WAYPOINTS = [
  { name: "DEGAN", lat: 19.45, lng: 72.70 },
  { name: "ARSIN", lat: 18.60, lng: 73.20 },
  { name: "OKLOV", lat: 20.10, lng: 72.40 },
  { name: "DISHA", lat: 19.20, lng: 73.50 },
  { name: "LUCKY", lat: 18.20, lng: 72.90 },
];

const FIR_COORDS = [
  [23.5, 68.0], [23.5, 77.0], [18.0, 80.0], [13.0, 77.0], [13.0, 70.0], [18.0, 67.0], [23.5, 68.0],
];

const APPROACH_PATHS = [
  { name: "27L/27R", latlngs: [[19.09, 73.5], [19.09, 72.86]] },
  { name: "09L/09R", latlngs: [[19.09, 72.2], [19.09, 72.86]] },
];

const FILTER_OPTS = ["ALL", "LANDING", "DEPARTING", "CONFLICTS"];
const ALT_OPTS    = ["ALL ALT", "< FL100", "FL100-250", "> FL250"];

// ─── HELPERS ──────────────────────────────────────────────────────────────────
function flightAltBand(alt) {
  if (!alt || alt === "GND") return "< FL100";
  if (alt.startsWith("FL")) {
    const fl = parseInt(alt.slice(2), 10);
    if (fl < 100) return "< FL100";
    if (fl <= 250) return "FL100-250";
    return "> FL250";
  }
  const ft = parseInt(alt, 10);
  return ft < 10000 ? "< FL100" : "FL100-250";
}

function displaySpeed(speed) {
  if (typeof speed === "string") return speed;
  const kt = Number(speed);
  return `${Number.isFinite(kt) ? Math.round(kt) : 0} kt`;
}

function makeAircraftIcon(color, heading, size, pulse) {
  const pulseHtml = pulse
    ? `<div style="position:absolute;top:50%;left:50%;width:${size}px;height:${size}px;margin-left:-${size/2}px;margin-top:-${size/2}px;border-radius:50%;border:2px solid #ff2d2d;animation:frm-pulse 1s ease-out infinite;pointer-events:none;"></div>`
    : "";
  const html = `<div style="width:${size}px;height:${size}px;transform:rotate(${heading}deg);position:relative;display:flex;align-items:center;justify-content:center;filter:drop-shadow(0 0 5px ${color});">${pulseHtml}<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="${color}"><path d="M21,16v-2l-8-5V3.5c0-0.83-0.67-1.5-1.5-1.5S10,2.67,10,3.5V9l-8,5v2l8-2.5V19l-2,1.5V22l3.5-1l3.5,1v-1.5L13,19v-5.5L21,16z"/></svg></div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function makeWaypointIcon(name, isLight) {
  const fill = isLight ? "#0f766e" : "#00e5cc";
  const label = isLight ? "#115e59" : "#00e5cc";
  const shadow = isLight ? "none" : "0 0 6px #00e5cc";
  const html = `<div style="position:relative;display:flex;flex-direction:column;align-items:center;"><svg viewBox="0 0 10 10" width="10" height="10" fill="${fill}"><polygon points="5,0 10,5 5,10 0,5"/></svg><span style="position:absolute;top:14px;left:50%;transform:translateX(-50%);font-family:'Geist Variable',system-ui,sans-serif;font-size:10px;color:${label};white-space:nowrap;font-weight:600;text-shadow:${shadow};">${name}</span></div>`;
  return L.divIcon({ className: "", html, iconSize: [10, 10], iconAnchor: [5, 5] });
}

function makeAirportIcon(isLight) {
  const fill = isLight ? "#b45309" : "#f5a623";
  const label = isLight ? "#92400e" : "#f5a623";
  const shadow = isLight ? "none" : "0 0 8px #f5a623";
  const html = `<div style="position:relative;display:flex;align-items:center;justify-content:center;"><svg viewBox="0 0 24 24" width="24" height="24" fill="${fill}"><rect x="11" y="2" width="2" height="20" rx="1"/><rect x="2" y="11" width="20" height="2" rx="1"/></svg><span style="position:absolute;top:26px;left:50%;transform:translateX(-50%);font-family:'Geist Variable',system-ui,sans-serif;font-size:10px;color:${label};white-space:nowrap;font-weight:700;text-shadow:${shadow};">VABB</span></div>`;
  return L.divIcon({ className: "", html, iconSize: [24, 24], iconAnchor: [12, 12] });
}

// Pill button
function Pill({ label, active, color, onClick, isLight }) {
  const inactiveBg = isLight ? "rgba(255,255,255,0.96)" : "rgba(6,6,8,0.85)";
  const inactiveColor = isLight ? "#292524" : color;
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: "'Geist Variable', system-ui, sans-serif",
        fontSize: 11,
        padding: "4px 10px",
        background: active ? color : inactiveBg,
        color: active ? "#0a0b0e" : inactiveColor,
        border: `1px solid ${color}`,
        opacity: active ? 1 : 1,
        cursor: "pointer",
        letterSpacing: "0.06em",
        transition: "all 0.15s",
        marginLeft: -1,
        boxShadow: isLight && !active ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
      }}
    >
      {label}
    </button>
  );
}

// ─── MAIN COMPONENT ────────────────────────────────────────────────────────────
export default function FlightRadarMap({ flights: propFlights, selectedFlight, onSelectFlight, theme }) {
  const mapRef    = useRef(null);
  const markersRef = useRef({});
  const overlaysRef = useRef([]);

  const [liveFlights, setLiveFlights]   = useState(INITIAL_FLIGHTS);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [altFilter, setAltFilter]       = useState("ALL ALT");
  const containerRef = useRef(null);
  const hasPropPositions = useMemo(
    () => Array.isArray(propFlights) && propFlights.some((f) => Number.isFinite(Number(f.lat)) && Number.isFinite(Number(f.lng))),
    [propFlights]
  );

  // ── Sync backend/replay aircraft into map state when coordinates are available ──
  useEffect(() => {
    if (!propFlights?.length) return;
    setLiveFlights((prev) => {
      const previousByCallsign = new Map(prev.map((f) => [f.callsign, f]));
      return propFlights
        .map((pf) => {
          const old = previousByCallsign.get(pf.callsign) || {};
          const lat = Number(pf.lat ?? old.lat);
          const lng = Number(pf.lng ?? old.lng);
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
          const speedKt = Number((pf.speedKt ?? parseInt(pf.speed || old.speed || "0", 10)) || 0);
          return {
            ...old,
            callsign: pf.callsign,
            lat,
            lng,
            status: String(pf.status || old.status || "cruise").toLowerCase(),
            altitude: pf.altitude || old.altitude || "GND",
            speed: speedKt,
            heading: Number(pf.heading ?? old.heading ?? 0),
          };
        })
        .filter(Boolean);
    });
  }, [propFlights]);

  // ── Move local fallback aircraft every 2s; backend/replay coordinates are authoritative when present ──
  useEffect(() => {
    if (hasPropPositions) return undefined;
    const id = setInterval(() => {
      setLiveFlights(prev =>
        prev.map(f => {
          if (f.speed === 0) return f;
          const hdRad = (f.heading * Math.PI) / 180;
          const dist  = (f.speed * 0.000290 * 2) / 3600;
          return { ...f, lat: f.lat + dist * Math.cos(hdRad), lng: f.lng + dist * Math.sin(hdRad) };
        })
      );
    }, 2000);
    return () => clearInterval(id);
  }, [hasPropPositions]);

  const isLight = theme === "light";

  // ── Init Leaflet map (rebuild when theme changes so basemap matches) ──
  useEffect(() => {
    if (!containerRef.current) return;

    if (mapRef.current) {
      mapRef.current.remove();
      mapRef.current = null;
      markersRef.current = {};
    }

    const map = L.map(containerRef.current, {
      center: [VABB_LAT, VABB_LNG],
      zoom: 8,
      minZoom: 7,
      maxZoom: 11,
      zoomControl: false,
      attributionControl: false,
      maxBounds: L.latLngBounds([10.0, 66.0], [25.0, 82.0]),
      maxBoundsViscosity: 1.0,
    });

    const tileUrl = isLight
      ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
    L.tileLayer(tileUrl, { subdomains: "abcd" }).addTo(map);

    const strokeAmber = isLight ? "#b45309" : "#f5a623";
    const strokeTeal = isLight ? "#0f766e" : "#00e5cc";

    L.polygon(FIR_COORDS, {
      color: strokeAmber, weight: isLight ? 2 : 1.5, opacity: isLight ? 0.85 : 0.45, dashArray: "6 4", fillOpacity: 0,
    }).addTo(map);

    L.circle([VABB_LAT, VABB_LNG], {
      radius: 80000,
      color: strokeTeal, weight: isLight ? 1.25 : 1, opacity: isLight ? 0.55 : 0.35, dashArray: "4 4", fillColor: strokeTeal, fillOpacity: isLight ? 0.06 : 0.03,
    }).addTo(map);

    APPROACH_PATHS.forEach(ap => {
      L.polyline(ap.latlngs, { color: strokeAmber, weight: 1.5, opacity: isLight ? 0.55 : 0.3, dashArray: "3 6" }).addTo(map);
    });

    L.marker([VABB_LAT, VABB_LNG], { icon: makeAirportIcon(isLight) }).addTo(map);

    WAYPOINTS.forEach(wp => {
      L.marker([wp.lat, wp.lng], { icon: makeWaypointIcon(wp.name, isLight) }).addTo(map);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, [isLight]);

  // ── Compute visible set ──
  const visibleCallsigns = useMemo(() => {
    const set = new Set();
    liveFlights.forEach(f => {
      const statusOk =
        statusFilter === "ALL" ||
        (statusFilter === "LANDING"   && (f.status === "landing"  || f.status === "approach")) ||
        (statusFilter === "DEPARTING" && (f.status === "departing"|| f.status === "takeoff"))  ||
        (statusFilter === "CONFLICTS" && f.status === "conflict");
      const altOk = altFilter === "ALL ALT" || flightAltBand(f.altitude) === altFilter;
      if (statusOk && altOk) set.add(f.callsign);
    });
    return set;
  }, [liveFlights, statusFilter, altFilter]);

  const statusColors = useMemo(
    () => (isLight ? STATUS_COLORS_LIGHT : STATUS_COLORS_DARK),
    [isLight]
  );

  // ── Update markers imperatively as liveFlights change ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const selectedColor = isLight ? "#0c0a09" : "#ffffff";
    const liveCallsigns = new Set(liveFlights.map((f) => f.callsign));

    Object.entries(markersRef.current).forEach(([callsign, marker]) => {
      if (!liveCallsigns.has(callsign)) {
        marker.remove();
        delete markersRef.current[callsign];
      }
    });

    liveFlights.forEach(f => {
      const isSelected = selectedFlight === f.callsign;
      const isDimmed   = !visibleCallsigns.has(f.callsign);
      const color      = isSelected ? selectedColor : (statusColors[f.status] || (isLight ? "#b45309" : "#f5a623"));
      const size       = f.status === "conflict" ? 32 : 28;

      if (markersRef.current[f.callsign]) {
        // Update existing marker
        const marker = markersRef.current[f.callsign];
        marker.setLatLng([f.lat, f.lng]);
        marker.setIcon(makeAircraftIcon(color, f.heading, size, f.status === "conflict"));
        marker.setOpacity(isDimmed ? 0.15 : 1);

        // Show permanent tooltip for conflict or selected
        const showLabel = f.status === "conflict" || isSelected;
        if (showLabel && !marker.getTooltip()) {
          marker.bindTooltip(`${f.callsign} | ${f.altitude} · ${displaySpeed(f.speed)}`, {
            permanent: true, direction: "top", offset: [0, -size / 2 - 2], className: "frm-tooltip",
          });
        } else if (!showLabel && marker.getTooltip()?.options?.permanent) {
          marker.unbindTooltip();
        }
      } else {
        // Create new marker
        const marker = L.marker([f.lat, f.lng], {
          icon: makeAircraftIcon(color, f.heading, size, f.status === "conflict"),
          opacity: isDimmed ? 0.15 : 1,
        });

        if (f.status === "conflict" || isSelected) {
          marker.bindTooltip(`${f.callsign} | ${f.altitude} · ${displaySpeed(f.speed)}`, {
            permanent: true, direction: "top", offset: [0, -size / 2 - 2], className: "frm-tooltip",
          });
        }

        marker.on("click", () => {
          if (!onSelectFlight) return;
          logAudit("map:marker", "Aircraft marker clicked on Leaflet map", { callsign: f.callsign });
          onSelectFlight(f.callsign, { surface: "map-marker" });
        });
        marker.on("mouseover", () => {
          if (f.status !== "conflict" && !isSelected) {
            marker.bindTooltip(`${f.callsign} | ${f.altitude} · ${displaySpeed(f.speed)}`, {
              permanent: false, direction: "top", offset: [0, -size / 2 - 2], className: "frm-tooltip",
            }).openTooltip();
          }
        });
        marker.on("mouseout", () => {
          if (f.status !== "conflict" && !isSelected) marker.unbindTooltip();
        });

        marker.addTo(map);
        markersRef.current[f.callsign] = marker;
      }
    });
  }, [liveFlights, selectedFlight, visibleCallsigns, onSelectFlight, statusColors, isLight]);

  const bgColor = isLight ? "var(--bg-base)" : "#060608";
  
  return (
    <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: bgColor }}>
      {/* Leaflet CSS overrides */}
      <style>{`
        .leaflet-container { background: ${bgColor} !important; }
        .leaflet-pane { z-index: 10 !important; }
        .leaflet-top, .leaflet-bottom { z-index: 10 !important; }
        .leaflet-tile { filter: ${isLight ? 'none' : 'brightness(0.82) saturate(0.65)'}; }
        .leaflet-control-attribution, .leaflet-control-zoom { display: none !important; }
        @keyframes frm-pulse {
          0%   { transform: scale(1); opacity: 0.9; }
          100% { transform: scale(2.5); opacity: 0; }
        }
        .frm-tooltip {
          background: ${isLight ? "#ffffff" : "#0a0b0e"} !important;
          border: 1px solid ${isLight ? "#b45309" : "#f5a623"} !important;
          color: ${isLight ? "#0c0a09" : "#f5a623"} !important;
          font-family: 'Geist Variable', system-ui, sans-serif !important;
          font-size: 11px !important;
          padding: 5px 9px !important;
          border-radius: 2px !important;
          white-space: nowrap !important;
          box-shadow: ${isLight ? "0 2px 8px rgba(0,0,0,0.12)" : "0 0 10px rgba(245,166,35,0.25)"};
        }
        .frm-tooltip::before { display: none !important; }
      `}</style>

      {/* Map DOM node */}
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {/* Controls overlay */}
      <div style={{ position: "absolute", top: 12, left: 12, zIndex: 10, display: "flex", flexDirection: "column", gap: 8, pointerEvents: "none" }}>
        {/* Sector info bar */}
        <div style={{
          fontFamily: "'Geist Variable', system-ui, sans-serif",
          fontSize: 10,
          color: isLight ? "#44403c" : "rgba(245,166,35,0.85)",
          letterSpacing: "0.06em",
          padding: "5px 11px",
          background: isLight ? "var(--overlay-strong)" : "rgba(6,6,8,0.75)",
          border: isLight ? "1px solid var(--border-default)" : "1px solid transparent",
          borderRadius: 2,
        }}>
          MODE: APP/DEP &nbsp;|&nbsp; RANGE: TMA 80NM &nbsp;|&nbsp; SECTOR: 7B-ALPHA
        </div>

        {/* Status filter */}
        <div style={{ display: "flex", pointerEvents: "all" }}>
          {FILTER_OPTS.map(opt => (
            <Pill
              key={opt}
              label={opt}
              active={statusFilter === opt}
              color={isLight ? "#b45309" : "#f5a623"}
              isLight={isLight}
              onClick={() => {
                logAudit("map:filter", "Map status filter pill activated", { value: opt });
                logActivity("map:filter", `Mock map status filter → ${opt}`, { kind: "status", value: opt });
                setStatusFilter(opt);
              }}
            />
          ))}
        </div>

        {/* Altitude filter */}
        <div style={{ display: "flex", pointerEvents: "all" }}>
          {ALT_OPTS.map(opt => (
            <Pill
              key={opt}
              label={opt}
              active={altFilter === opt}
              color={isLight ? "#0f766e" : "#00e5cc"}
              isLight={isLight}
              onClick={() => {
                logAudit("map:filter", "Map altitude filter pill activated", { value: opt });
                logActivity("map:filter", `Mock map altitude band → ${opt}`, { kind: "altitude", value: opt });
                setAltFilter(opt);
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
