import { useEffect, useRef, useState, useMemo } from "react";
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

const STATUS_COLORS = {
  landing: "#00e5cc", approach: "#00e5cc",
  takeoff: "#f5a623", cruise: "#f5a623", departing: "#f5a623",
  holding: "#ffdd00",
  conflict: "#ff2d2d",
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

function makeAircraftIcon(color, heading, size, pulse) {
  const pulseHtml = pulse
    ? `<div style="position:absolute;top:50%;left:50%;width:${size}px;height:${size}px;margin-left:-${size/2}px;margin-top:-${size/2}px;border-radius:50%;border:2px solid #ff2d2d;animation:frm-pulse 1s ease-out infinite;pointer-events:none;"></div>`
    : "";
  const html = `<div style="width:${size}px;height:${size}px;transform:rotate(${heading}deg);position:relative;display:flex;align-items:center;justify-content:center;filter:drop-shadow(0 0 5px ${color});">${pulseHtml}<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="${color}"><path d="M12 2L4 14h5v7l3-1 3 1v-7h5L12 2z"/></svg></div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

function makeWaypointIcon(name) {
  const html = `<div style="position:relative;display:flex;flex-direction:column;align-items:center;"><svg viewBox="0 0 10 10" width="10" height="10" fill="#00e5cc"><polygon points="5,0 10,5 5,10 0,5"/></svg><span style="position:absolute;top:14px;left:50%;transform:translateX(-50%);font-family:'Share Tech Mono',monospace;font-size:9px;color:#00e5cc;white-space:nowrap;opacity:0.75;text-shadow:0 0 6px #00e5cc;">${name}</span></div>`;
  return L.divIcon({ className: "", html, iconSize: [10, 10], iconAnchor: [5, 5] });
}

function makeAirportIcon() {
  const html = `<div style="position:relative;display:flex;align-items:center;justify-content:center;"><svg viewBox="0 0 24 24" width="24" height="24" fill="#f5a623"><rect x="11" y="2" width="2" height="20" rx="1"/><rect x="2" y="11" width="20" height="2" rx="1"/></svg><span style="position:absolute;top:26px;left:50%;transform:translateX(-50%);font-family:'Share Tech Mono',monospace;font-size:9px;color:#f5a623;white-space:nowrap;font-weight:700;text-shadow:0 0 8px #f5a623;">VABB</span></div>`;
  return L.divIcon({ className: "", html, iconSize: [24, 24], iconAnchor: [12, 12] });
}

// Pill button
function Pill({ label, active, color, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: "'Share Tech Mono', monospace",
        fontSize: 10,
        padding: "3px 10px",
        background: active ? color : "rgba(6,6,8,0.85)",
        color: active ? "#0a0b0e" : color,
        border: `1px solid ${color}`,
        opacity: active ? 1 : 0.75,
        cursor: "pointer",
        letterSpacing: "0.08em",
        transition: "all 0.15s",
        marginLeft: -1,
      }}
    >
      {label}
    </button>
  );
}

// ─── MAIN COMPONENT ────────────────────────────────────────────────────────────
export default function FlightRadarMap({ flights: propFlights, selectedFlight, onSelectFlight }) {
  const mapRef    = useRef(null);
  const markersRef = useRef({});
  const overlaysRef = useRef([]);

  const [liveFlights, setLiveFlights]   = useState(INITIAL_FLIGHTS);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [altFilter, setAltFilter]       = useState("ALL ALT");
  const containerRef = useRef(null);

  // ── Sync propFlights status into liveFlights ──
  useEffect(() => {
    if (!propFlights?.length) return;
    setLiveFlights(prev =>
      prev.map(lf => {
        const pf = propFlights.find(p => p.callsign === lf.callsign);
        if (!pf) return lf;
        return { ...lf, status: (pf.status || lf.status).toLowerCase(), altitude: pf.altitude || lf.altitude, speed: parseInt(pf.speed, 10) || lf.speed, heading: pf.heading ?? lf.heading };
      })
    );
  }, [propFlights]);

  // ── Move aircraft every 2s ──
  useEffect(() => {
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
  }, []);

  // ── Init Leaflet map imperatively (avoids react-leaflet dependency chain) ──
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

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

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd",
    }).addTo(map);

    // FIR boundary polygon
    L.polygon(FIR_COORDS, {
      color: "#f5a623", weight: 1.5, opacity: 0.45, dashArray: "6 4", fillOpacity: 0,
    }).addTo(map);

    // TMA circle (80 km)
    L.circle([VABB_LAT, VABB_LNG], {
      radius: 80000,
      color: "#00e5cc", weight: 1, opacity: 0.35, dashArray: "4 4", fillColor: "#00e5cc", fillOpacity: 0.03,
    }).addTo(map);

    // ILS approach corridors
    APPROACH_PATHS.forEach(ap => {
      L.polyline(ap.latlngs, { color: "#f5a623", weight: 1.5, opacity: 0.3, dashArray: "3 6" }).addTo(map);
    });

    // Airport marker
    L.marker([VABB_LAT, VABB_LNG], { icon: makeAirportIcon() }).addTo(map);

    // Waypoints
    WAYPOINTS.forEach(wp => {
      L.marker([wp.lat, wp.lng], { icon: makeWaypointIcon(wp.name) }).addTo(map);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, []);

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

  // ── Update markers imperatively as liveFlights change ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    liveFlights.forEach(f => {
      const isSelected = selectedFlight === f.callsign;
      const isDimmed   = !visibleCallsigns.has(f.callsign);
      const color      = isSelected ? "#ffffff" : (STATUS_COLORS[f.status] || "#f5a623");
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
          marker.bindTooltip(`${f.callsign} | ${f.altitude} · ${f.speed}kt`, {
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
          marker.bindTooltip(`${f.callsign} | ${f.altitude} · ${f.speed}kt`, {
            permanent: true, direction: "top", offset: [0, -size / 2 - 2], className: "frm-tooltip",
          });
        }

        marker.on("click", () => onSelectFlight && onSelectFlight(f.callsign));
        marker.on("mouseover", () => {
          if (f.status !== "conflict" && !isSelected) {
            marker.bindTooltip(`${f.callsign} | ${f.altitude} · ${f.speed}kt`, {
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
  }, [liveFlights, selectedFlight, visibleCallsigns, onSelectFlight]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: "#060608" }}>
      {/* Leaflet CSS overrides */}
      <style>{`
        .leaflet-container { background: #060608 !important; }
        .leaflet-tile { filter: brightness(0.82) saturate(0.65); }
        .leaflet-control-attribution, .leaflet-control-zoom { display: none !important; }
        @keyframes frm-pulse {
          0%   { transform: scale(1); opacity: 0.9; }
          100% { transform: scale(2.5); opacity: 0; }
        }
        .frm-tooltip {
          background: #0a0b0e !important;
          border: 1px solid #f5a623 !important;
          color: #f5a623 !important;
          font-family: 'Share Tech Mono', monospace !important;
          font-size: 10px !important;
          padding: 4px 8px !important;
          border-radius: 0 !important;
          white-space: nowrap !important;
          box-shadow: 0 0 10px rgba(245,166,35,0.25);
        }
        .frm-tooltip::before { display: none !important; }
      `}</style>

      {/* Map DOM node */}
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {/* Controls overlay */}
      <div style={{ position: "absolute", top: 12, left: 12, zIndex: 1000, display: "flex", flexDirection: "column", gap: 8, pointerEvents: "none" }}>
        {/* Sector info bar */}
        <div style={{ fontFamily: "'Share Tech Mono', monospace", fontSize: 9, color: "rgba(245,166,35,0.55)", letterSpacing: "0.1em", padding: "4px 10px", background: "rgba(6,6,8,0.75)" }}>
          MODE: APP/DEP &nbsp;|&nbsp; RANGE: TMA 80NM &nbsp;|&nbsp; SECTOR: 7B-ALPHA
        </div>

        {/* Status filter */}
        <div style={{ display: "flex", pointerEvents: "all" }}>
          {FILTER_OPTS.map(opt => (
            <Pill key={opt} label={opt} active={statusFilter === opt} color="#f5a623" onClick={() => setStatusFilter(opt)} />
          ))}
        </div>

        {/* Altitude filter */}
        <div style={{ display: "flex", pointerEvents: "all" }}>
          {ALT_OPTS.map(opt => (
            <Pill key={opt} label={opt} active={altFilter === opt} color="#00e5cc" onClick={() => setAltFilter(opt)} />
          ))}
        </div>
      </div>
    </div>
  );
}
