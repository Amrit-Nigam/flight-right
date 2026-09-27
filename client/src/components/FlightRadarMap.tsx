import { useEffect, useMemo, useState } from "react";
import type { GeoJSON } from "geojson";
import type { GeoJSONSourceRaw } from "maplibre-gl";
import { logActivity, logAudit } from "@/lib/siteLogger";
import {
  Map,
  MapMarker,
  MarkerContent,
  MarkerLabel,
  MarkerTooltip,
  MapRoute,
  useMap,
} from "@/components/ui/map";

// ─── CONSTANTS ─────────────────────────────────────────────────────────────────
const VABB_LAT = 19.0896;
const VABB_LNG = 72.8656;

// Shape only. The map draws whatever the backend sends; there is no seeded traffic,
// because a map that invents aircraft when the feed is quiet is worse than a blank one.
const INITIAL_FLIGHTS: {
  callsign: string; lat: number; lng: number; heading: number; speed: number;
  altitude: string; status: string; cpaPair?: string | null;
}[] = [];


const STATUS_COLORS_DARK: Record<string, string> = {
  landing: "#00e5cc",
  approach: "#00e5cc",
  takeoff: "#f5a623",
  cruise: "#f5a623",
  departing: "#f5a623",
  holding: "#ffdd00",
  conflict: "#ff2d2d",
};
const STATUS_COLORS_LIGHT: Record<string, string> = {
  landing: "#0f766e",
  approach: "#0f766e",
  takeoff: "#b45309",
  cruise: "#64748b",
  departing: "#b45309",
  holding: "#a16207",
  conflict: "#b91c1c",
};

// Removed 27 Sep 2026: five named "waypoints" (DEGAN, ARSIN, OKLOV, DISHA, LUCKY) we could not
// verify against any published source, an invented FIR outline, and approach lines labelled
// 27L/27R and 09L/09R (Mumbai has 09/27 and 14/32). In their place: the OpenSky query box our
// data is actually collected from (server/app/config.py BOUNDS), a 50 NM range ring, and the real
// runways from OurAirports (via /api/airport) with a 10 NM extended centreline on the runway in use.
const DATA_BOX_LNGLAT: [number, number][] = [
  [68.0, 16.0], [77.5, 16.0], [77.5, 23.5], [68.0, 23.5], [68.0, 16.0],
];
const RANGE_RING_M = 50 * 1852;

/** A point `nm` nautical miles from (lat, lng) along `bearingDeg`, as [lng, lat] (flat-earth, fine at these ranges). */
function offsetNm(lat: number, lng: number, bearingDeg: number, nm: number): [number, number] {
  const h = (bearingDeg * Math.PI) / 180;
  return [lng + (nm * Math.sin(h)) / (60 * Math.cos((lat * Math.PI) / 180)), lat + (nm * Math.cos(h)) / 60];
}

type Runway = { end: string; runway: string; headingDeg: number; threshold: [number, number]; far: [number, number] };

// Built from the live conflict prop. Nothing here is hardcoded to a callsign any more.
const EMPTY_PLAN = {
  primary: null as string | null,
  secondary: null as string | null,
  cpa: null as [number, number] | null,
  cpaLabel: "",
  minimum: "",
  actions: [] as string[],
};

const FILTER_OPTS = ["ALL", "LANDING", "DEPARTING", "CONFLICTS"];
const ALT_OPTS = ["ALL ALT", "< FL100", "FL100-250", "> FL250"];

function flightAltBand(alt: string | undefined) {
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

/** Approximate geodesic circle as a polygon ring [lng, lat][] */
function circleRingLngLat(lng: number, lat: number, radiusM: number, steps = 72): [number, number][] {
  const ring: [number, number][] = [];
  const cosLat = Math.cos((lat * Math.PI) / 180);
  const metersPerDegLng = 111320 * Math.max(0.2, Math.abs(cosLat));
  const metersPerDegLat = 110540;
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    ring.push([lng + (radiusM / metersPerDegLng) * Math.cos(a), lat + (radiusM / metersPerDegLat) * Math.sin(a)]);
  }
  return ring;
}

function Pill({
  label,
  active,
  color,
  onClick,
  isLight,
}: {
  label: string;
  active: boolean;
  color: string;
  onClick: () => void;
  isLight: boolean;
}) {
  const inactiveBg = isLight ? "rgba(255,255,255,0.96)" : "rgba(6,6,8,0.85)";
  const inactiveColor = isLight ? "#292524" : color;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontFamily: "'Geist Variable', system-ui, sans-serif",
        fontSize: 11,
        padding: "4px 10px",
        background: active ? color : inactiveBg,
        color: active ? "#0a0b0e" : inactiveColor,
        border: `1px solid ${color}`,
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

function AircraftIcon({
  color,
  heading,
  size,
  pulse,
}: {
  color: string;
  heading: number;
  size: number;
  pulse: boolean;
}) {
  return (
    <div
      className="relative flex items-center justify-center"
      style={{
        width: size,
        height: size,
        transform: `rotate(${heading}deg)`,
        filter: `drop-shadow(0 0 5px ${color})`,
      }}
    >
      {pulse ? (
        <div
          className="pointer-events-none absolute rounded-full border-2 border-[#ff2d2d]"
          style={{
            width: size,
            height: size,
            left: "50%",
            top: "50%",
            marginLeft: -size / 2,
            marginTop: -size / 2,
            animation: "frm-pulse 1s ease-out infinite",
          }}
        />
      ) : null}
      <svg viewBox="0 0 24 24" width={size} height={size} fill={color}>
        <path d="M21,16v-2l-8-5V3.5c0-0.83-0.67-1.5-1.5-1.5S10,2.67,10,3.5V9l-8,5v2l8-2.5V19l-2,1.5V22l3.5-1l3.5,1v-1.5L13,19v-5.5L21,16z" />
      </svg>
    </div>
  );
}

/** GeoJSON overlays: FIR line, TMA fill, approaches, optional CPA rings */
function FlightRadarGeoLayers({ isLight, hasActiveConflict, runways, inUseEnd, cpa, ringNm }:
  { isLight: boolean; hasActiveConflict: boolean; runways: Runway[]; inUseEnd: string | null;
    cpa: [number, number] | null; ringNm: number }) {
  const { map, isLoaded } = useMap();

  const strokeAmber = isLight ? "#b45309" : "#f5a623";
  const strokeTeal = isLight ? "#0f766e" : "#00e5cc";
  const red = isLight ? "#b91c1c" : "#ff2d2d";

  useEffect(() => {
    if (!map || !isLoaded) return;

    const layers = [
      "frm-fir-line",
      "frm-tma-fill",
      "frm-tma-line",
      "frm-approach-0",
      "frm-approach-1",
      "frm-cpa-outer-fill",
      "frm-cpa-inner-line",
    ];

    const sources = ["frm-fir", "frm-tma", "frm-approach-0", "frm-approach-1", "frm-cpa-outer", "frm-cpa-inner"];

    const firFc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: DATA_BOX_LNGLAT },
        },
      ],
    };

    const tmaRing = circleRingLngLat(VABB_LNG, VABB_LAT, RANGE_RING_M);
    const tmaFc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: { type: "Polygon", coordinates: [tmaRing] },
        },
      ],
    };

    const addSrc = (id: string, data: GeoJSON) => {
      map.addSource(id, { type: "geojson", data } as GeoJSONSourceRaw);
    };

    try {
      addSrc("frm-fir", firFc);
      addSrc("frm-tma", tmaFc);

      // Real runways, plus a 10 NM extended centreline for the runway end in use.
      const runwayLines: [number, number][][] = [];
      const seen = new Set<string>();
      for (const r of runways) {
        if (!seen.has(r.runway)) {
          seen.add(r.runway);
          runwayLines.push([[r.threshold[1], r.threshold[0]], [r.far[1], r.far[0]]]);
        }
      }
      const inUse = runways.find((r) => r.end === inUseEnd);
      const approachLines: [number, number][][] = inUse
        ? [[offsetNm(inUse.threshold[0], inUse.threshold[1], (inUse.headingDeg + 180) % 360, 10), [inUse.threshold[1], inUse.threshold[0]]]]
        : [];
      [runwayLines, approachLines].forEach((lines, i) => {
        addSrc(`frm-approach-${i}`, {
          type: "FeatureCollection",
          features: lines.map((coordinates) => ({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates } })),
        } as GeoJSON.FeatureCollection);
      });

      map.addLayer({
        id: "frm-fir-line",
        type: "line",
        source: "frm-fir",
        paint: {
          "line-color": strokeAmber,
          "line-width": isLight ? 2 : 1.5,
          "line-opacity": isLight ? 0.85 : 0.45,
          "line-dasharray": [2, 2],
        },
      });

      map.addLayer({
        id: "frm-tma-fill",
        type: "fill",
        source: "frm-tma",
        paint: {
          "fill-color": strokeTeal,
          "fill-opacity": isLight ? 0.06 : 0.03,
        },
      });
      map.addLayer({
        id: "frm-tma-line",
        type: "line",
        source: "frm-tma",
        paint: {
          "line-color": strokeTeal,
          "line-width": isLight ? 1.25 : 1,
          "line-opacity": isLight ? 0.55 : 0.35,
          "line-dasharray": [2, 2],
        },
      });

      [0, 1].forEach((i) => {
        map.addLayer({
          id: `frm-approach-${i}`,
          type: "line",
          source: `frm-approach-${i}`,
          paint: i === 0
            ? { "line-color": isLight ? "#44403c" : "#e7e5e4", "line-width": 4, "line-opacity": 0.85 }
            : { "line-color": strokeAmber, "line-width": 1.5, "line-opacity": isLight ? 0.7 : 0.5, "line-dasharray": [1, 2] },
        });
      });

      if (hasActiveConflict) {
        if (!cpa) return;
        const [cpaLat, cpaLng] = cpa;
        // The separation standard drawn to scale around the predicted closest approach.
        const outerRing = circleRingLngLat(cpaLng, cpaLat, ringNm * 1852);
        const innerRing = circleRingLngLat(cpaLng, cpaLat, (ringNm * 1852) / 2);
        addSrc("frm-cpa-outer", {
          type: "FeatureCollection",
          features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [outerRing] } }],
        });
        addSrc("frm-cpa-inner", {
          type: "FeatureCollection",
          features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: innerRing } }],
        });
        map.addLayer({
          id: "frm-cpa-outer-fill",
          type: "fill",
          source: "frm-cpa-outer",
          paint: {
            "fill-color": red,
            "fill-opacity": isLight ? 0.05 : 0.08,
          },
        });
        map.addLayer({
          id: "frm-cpa-inner-line",
          type: "line",
          source: "frm-cpa-inner",
          paint: {
            "line-color": strokeTeal,
            "line-width": 1,
            "line-opacity": 0.5,
            "line-dasharray": [2, 2],
          },
        });
      }
    } catch {
      // style swap race — cleaned up on rerun
    }

    return () => {
      for (const lid of layers) {
        try {
          if (map.getLayer(lid)) map.removeLayer(lid);
        } catch {
          /* ignore */
        }
      }
      for (const sid of sources) {
        try {
          if (map.getSource(sid)) map.removeSource(sid);
        } catch {
          /* ignore */
        }
      }
    };
  }, [map, isLoaded, isLight, hasActiveConflict, strokeAmber, strokeTeal, red, runways, inUseEnd, cpa, ringNm]);

  return null;
}

/** Pan once to frame an alarm's two aircraft and their predicted closest approach. Alarms are
 * en-route and often far outside the default view over VABB. Runs when the alarm pair changes,
 * not on every update, so the controller can still pan freely. */
function FitConflict({ id, points }: { id: string | null; points: [number, number][] }) {
  const { map, isLoaded } = useMap();
  useEffect(() => {
    if (!map || !isLoaded || !id || points.length < 2) return;
    const lngs = points.map((p) => p[0]), lats = points.map((p) => p[1]);
    try {
      map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
                    { padding: 110, maxZoom: 9, duration: 1200 });
    } catch { /* style swap race */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, isLoaded, id]);
  return null;
}

type LiveFlight = (typeof INITIAL_FLIGHTS)[number];

type PropFlight = {
  callsign: string;
  status?: string;
  altitude?: string;
  speed?: string | number;
  heading?: number;
  cpaPair?: string | null;
};

export default function FlightRadarMap({
  flights: propFlights,
  conflict,
  selectedFlight,
  onSelectFlight,
  theme,
  airport = null,
  constants = null,
  source = null,
}: {
  flights?: PropFlight[];
  conflict?: any;
  selectedFlight: string | null;
  onSelectFlight?: (callsign: string, meta?: { surface?: string }) => void;
  theme: string;
  airport?: any;
  constants?: any;
  source?: string | null;
}) {
  const [liveFlights, setLiveFlights] = useState<LiveFlight[]>(INITIAL_FLIGHTS);

  // The conflict overlay comes from the detection chain, not from a fixed scenario.
  const CONFLICT_PLAN = useMemo(() => {
    if (!conflict) return EMPTY_PLAN;
    const primary = propFlights?.find((f) => f.callsign === conflict.flight1) as any;
    const secondary = propFlights?.find((f) => f.callsign === conflict.flight2) as any;
    // Each aircraft's straight-line position at the predicted time of closest approach -- the
    // prediction the alarm is computed from. The CPA mark sits between those two positions.
    // (It used to be the midpoint of where the aircraft are NOW, with each line then bent to a
    // fixed map point.)
    const t = Math.max(0, Number(conflict.countdown) || 0);
    const at = (f: any): [number, number] | null => {
      if (f?.lat == null) return null;
      const nm = ((Number(f.speedKt) || 0) * t) / 3600;
      return offsetNm(f.lat, f.lng, Number(f.heading) || 0, nm);
    };
    const endA = at(primary), endB = at(secondary);
    const cpa: [number, number] | null = endA && endB ? [(endA[1] + endB[1]) / 2, (endA[0] + endB[0]) / 2] : null;
    return {
      primary: conflict.flight1,
      secondary: conflict.flight2,
      cpa,
      endA,
      endB,
      cpaLabel: `CPA ${Number(conflict.cpaNM).toFixed(2)} NM / ${Math.round(conflict.cpaVerticalFt)} ft · T-${Math.round(conflict.countdown)}s`,
      minimum: constants ? `MIN SEP ${constants.separationLateralNm} NM / ${constants.separationVerticalFt} FT (en-route)` : "",
      actions: (conflict.resolution?.options || []).map((o: any) => o.explanation).slice(0, 3),
    };
  }, [conflict, propFlights, constants]);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [altFilter, setAltFilter] = useState("ALL ALT");

  // The backend is the source of truth. The old version matched incoming flights
  // against a fixed list by callsign and silently dropped everything that did not
  // match, which meant real traffic never appeared on the map at all.
  useEffect(() => {
    if (!propFlights) return;
    setLiveFlights(
      propFlights
        .filter((p: any) => Number.isFinite(p.lat) && Number.isFinite(p.lng))
        .map((p: any) => ({
          callsign: p.callsign,
          lat: p.lat,
          lng: p.lng,
          heading: p.heading ?? 0,
          speed: Number(p.speedKt ?? parseInt(String(p.speed), 10)) || 0,
          altitude: p.altitude || "GND",
          status: String(p.status || "cruise").toLowerCase(),
          cpaPair: p.cpaPair ?? null,
        })),
    );
  }, [propFlights]);

  // No dead-reckoning between updates: positions come from the feed, and moving them
  // ourselves would put the icon somewhere the aircraft is not.

  const isLight = theme === "light";

  const conflictCallsigns = useMemo(() => {
    const set = new Set<string>();
    liveFlights.forEach((f) => {
      if (f.status === "conflict" || f.cpaPair) {
        set.add(f.callsign);
        if (f.cpaPair) set.add(f.cpaPair);
      }
    });
    return set;
  }, [liveFlights]);

  const hasActiveConflict = conflictCallsigns.size >= 2;

  const visibleCallsigns = useMemo(() => {
    const set = new Set<string>();
    liveFlights.forEach((f) => {
      const statusOk =
        statusFilter === "ALL" ||
        (statusFilter === "LANDING" && (f.status === "landing" || f.status === "approach")) ||
        (statusFilter === "DEPARTING" && (f.status === "departing" || f.status === "takeoff")) ||
        (statusFilter === "CONFLICTS" && conflictCallsigns.has(f.callsign));
      const altOk = altFilter === "ALL ALT" || flightAltBand(f.altitude) === altFilter;
      if (statusOk && altOk) set.add(f.callsign);
    });
    return set;
  }, [liveFlights, statusFilter, altFilter, conflictCallsigns]);

  const statusColors = useMemo(() => (isLight ? STATUS_COLORS_LIGHT : STATUS_COLORS_DARK), [isLight]);

  const mapTheme = isLight ? "light" : "dark";
  const tealAccent = isLight ? "#0f766e" : "#00e5cc";
  const bgColor = isLight ? "var(--bg-base)" : "#060608";

  const [cpaLng, cpaLat] = CONFLICT_PLAN.cpa ? [CONFLICT_PLAN.cpa[1], CONFLICT_PLAN.cpa[0]] : [0, 0];
  const red = isLight ? "#b91c1c" : "#ff2d2d";

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: bgColor }}>
      <style>{`
        @keyframes frm-pulse {
          0% { transform: scale(1); opacity: 0.9; }
          100% { transform: scale(2.5); opacity: 0; }
        }
        @keyframes frm-cpa-pulse {
          0% { transform: scale(0.8); opacity: 1; }
          100% { transform: scale(2.6); opacity: 0; }
        }
        .frm-tooltip-mapcn {
          font-family: 'Geist Variable', system-ui, sans-serif !important;
          font-size: 11px !important;
          padding: 5px 9px !important;
          border-radius: 2px !important;
          white-space: nowrap !important;
        }
      `}</style>

      <Map
        theme={mapTheme}
        className="absolute inset-0"
        center={[VABB_LNG, VABB_LAT]}
        zoom={8}
        minZoom={7}
        maxZoom={11}
        maxBounds={[
          [66, 10],
          [82, 25],
        ]}
        attributionControl={false}
        dragRotate={false}
        pitchWithRotate={false}
        touchPitch={false}
        styles={{
          light: "https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json",
          dark: "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
        }}
      >
        <FitConflict id={conflict ? `${conflict.flight1}|${conflict.flight2}` : null}
                     points={[
                       ...[CONFLICT_PLAN.primary, CONFLICT_PLAN.secondary]
                         .map((c) => liveFlights.find((f) => f.callsign === c))
                         .filter(Boolean)
                         .map((f: any) => [f.lng, f.lat] as [number, number]),
                       ...(((CONFLICT_PLAN as any).endA && (CONFLICT_PLAN as any).endB) ? [(CONFLICT_PLAN as any).endA, (CONFLICT_PLAN as any).endB] : []),
                     ]} />
        <FlightRadarGeoLayers isLight={isLight} hasActiveConflict={hasActiveConflict}
                              runways={airport?.runways || []} inUseEnd={airport?.inUse?.end || null}
                              cpa={CONFLICT_PLAN.cpa} ringNm={constants?.separationLateralNm ?? 5} />

        {hasActiveConflict
          ? (() => {
              const conflictFlights = [CONFLICT_PLAN.primary, CONFLICT_PLAN.secondary]
                .map((c) => liveFlights.find((f) => f.callsign === c))
                .filter(Boolean) as LiveFlight[];
              if (conflictFlights.length < 2) return null;
              const [f1, f2] = conflictFlights;
              const [cpaLat2, cpaLng2] = CONFLICT_PLAN.cpa || [0, 0];
              const cpaPt: [number, number] = [cpaLng2, cpaLat2];
              return (
                <>
                  <MapRoute
                    id="frm-conflict-a"
                    coordinates={[[f1.lng, f1.lat], (CONFLICT_PLAN as any).endA || cpaPt]}
                    color={red}
                    width={3}
                    opacity={0.72}
                    dashArray={[4, 3]}
                    interactive={false}
                  />
                  <MapRoute
                    id="frm-conflict-b"
                    coordinates={[[f2.lng, f2.lat], (CONFLICT_PLAN as any).endB || cpaPt]}
                    color={isLight ? "#b45309" : "#f5a623"}
                    width={3}
                    opacity={0.72}
                    dashArray={[4, 3]}
                    interactive={false}
                  />
                  <MapRoute
                    id="frm-conflict-pair"
                    coordinates={[
                      [f1.lng, f1.lat],
                      [f2.lng, f2.lat],
                    ]}
                    color={red}
                    width={1.5}
                    opacity={0.55}
                    dashArray={[2, 4]}
                    interactive={false}
                  />
                </>
              );
            })()
          : null}

        <MapMarker longitude={VABB_LNG} latitude={VABB_LAT} anchor="center">
          <MarkerContent>
            <div className="relative flex flex-col items-center justify-center">
              <svg viewBox="0 0 24 24" width={24} height={24} fill={isLight ? "#b45309" : "#f5a623"}>
                <rect x="11" y="2" width="2" height="20" rx="1" />
                <rect x="2" y="11" width="20" height="2" rx="1" />
              </svg>
              <span
                className="absolute whitespace-nowrap font-semibold"
                style={{
                  top: 26,
                  left: "50%",
                  transform: "translateX(-50%)",
                  fontFamily: "'Geist Variable', system-ui, sans-serif",
                  fontSize: 10,
                  color: isLight ? "#92400e" : "#f5a623",
                  textShadow: isLight ? "none" : "0 0 8px #f5a623",
                }}
              >
                VABB
              </span>
            </div>
          </MarkerContent>
        </MapMarker>


        {hasActiveConflict ? (
          <MapMarker longitude={cpaLng} latitude={cpaLat} anchor="center">
            <MarkerContent>
              <div
                className="pointer-events-none relative flex flex-col items-center justify-center"
                style={{ width: 116, height: 44, transform: "translate(-58px, -22px)" }}
              >
                <div
                  className="absolute rounded-full border-2"
                  style={{
                    width: 18,
                    height: 18,
                    left: "50%",
                    top: "50%",
                    marginLeft: -9,
                    marginTop: -9,
                    borderColor: red,
                    background: `${red}22`,
                    boxShadow: `0 0 18px ${red}`,
                    animation: "frm-cpa-pulse 1s ease-out infinite",
                  }}
                />
                <div
                  className="absolute whitespace-nowrap font-extrabold tracking-widest"
                  style={{
                    left: 28,
                    top: -18,
                    background: isLight ? "#ffffff" : "#120807",
                    border: `1px solid ${red}`,
                    color: red,
                    fontSize: 10,
                    padding: "4px 7px",
                    boxShadow: "0 2px 10px rgba(0,0,0,.18)",
                  }}
                >
                  {conflict ? `CPA ${Number(conflict.cpaNM).toFixed(2)} NM / ${Math.round(conflict.cpaVerticalFt)} ft` : ""}
                </div>
              </div>
            </MarkerContent>
          </MapMarker>
        ) : null}

        {liveFlights.map((f) => {
          const isSelected = selectedFlight === f.callsign;
          const isDimmed = !visibleCallsigns.has(f.callsign);
          const isConflictTrack = hasActiveConflict && conflictCallsigns.has(f.callsign);
          const selectedColor = isLight ? "#0c0a09" : "#ffffff";
          const amber = isLight ? "#b45309" : "#f5a623";
          const color =
            isSelected
              ? selectedColor
              : f.callsign === CONFLICT_PLAN.primary
                ? red
                : isConflictTrack
                  ? amber
                  : statusColors[f.status] || amber;
          const size = isConflictTrack ? 36 : 28;

          return (
            <MapMarker
              key={f.callsign}
              longitude={f.lng}
              latitude={f.lat}
              anchor="center"
              onClick={() => {
                if (!onSelectFlight) return;
                logAudit("map:marker", "Aircraft marker clicked on map", { callsign: f.callsign });
                onSelectFlight(f.callsign, { surface: "map-marker" });
              }}
            >
              <MarkerContent>
                <div style={{ opacity: isDimmed ? 0.15 : 1, cursor: "pointer" }}>
                  <AircraftIcon color={color} heading={f.heading} size={size} pulse={isConflictTrack} />
                </div>
                {isSelected ? (
                  <MarkerLabel position="top" className="frm-tooltip-mapcn border border-[var(--amber)] bg-[var(--bg-panel)] text-[var(--text-primary)] shadow-md">
                    {f.callsign} | {f.altitude} · {f.speed}kt
                  </MarkerLabel>
                ) : (
                  <MarkerTooltip
                    offset={12}
                    className="frm-tooltip-mapcn border border-[var(--amber)] !bg-[var(--bg-panel)] !text-[var(--text-primary)] shadow-md"
                  >
                    {f.callsign} | {f.altitude} · {f.speed}kt
                  </MarkerTooltip>
                )}
              </MarkerContent>
            </MapMarker>
          );
        })}
      </Map>

      <div
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            fontFamily: "'Geist Variable', system-ui, sans-serif",
            fontSize: 10,
            color: isLight ? "#44403c" : "rgba(245,166,35,0.85)",
            letterSpacing: "0.06em",
            padding: "5px 11px",
            background: isLight ? "var(--overlay-strong)" : "rgba(6,6,8,0.75)",
            border: isLight ? "1px solid var(--border-default)" : "1px solid transparent",
            borderRadius: 2,
          }}
        >
          {source === "live" ? "LIVE OpenSky" : source === "replay" ? "RECORDED SESSION" : "NO SOURCE"}
          &nbsp;|&nbsp; RING: 50 NM FROM VABB &nbsp;|&nbsp; BOX: OPENSKY QUERY AREA
          {airport?.inUse ? <>&nbsp;|&nbsp; RWY IN USE {airport.inUse.end}</> : null}
        </div>

        <div style={{ display: "flex", pointerEvents: "all" }}>
          {FILTER_OPTS.map((opt) => (
            <Pill
              key={opt}
              label={opt}
              active={statusFilter === opt}
              color={isLight ? "#b45309" : "#f5a623"}
              isLight={isLight}
              onClick={() => {
                logAudit("map:filter", "Map status filter pill activated", { value: opt });
                logActivity("map:filter", `Map status filter → ${opt}`, { kind: "status", value: opt });
                setStatusFilter(opt);
              }}
            />
          ))}
        </div>

        <div style={{ display: "flex", pointerEvents: "all" }}>
          {ALT_OPTS.map((opt) => (
            <Pill
              key={opt}
              label={opt}
              active={altFilter === opt}
              color={isLight ? "#0f766e" : "#00e5cc"}
              isLight={isLight}
              onClick={() => {
                logAudit("map:filter", "Map altitude filter pill activated", { value: opt });
                logActivity("map:filter", `Map altitude band → ${opt}`, { kind: "altitude", value: opt });
                setAltFilter(opt);
              }}
            />
          ))}
        </div>
      </div>

      {hasActiveConflict ? (
        <div
          style={{
            position: "absolute",
            right: 12,
            bottom: 12,
            zIndex: 11,
            width: 300,
            background: isLight ? "rgba(255,255,255,0.95)" : "rgba(10,11,14,0.9)",
            border: `1px solid ${isLight ? "#b91c1c" : "#ff2d2d"}`,
            boxShadow: isLight ? "0 8px 20px rgba(0,0,0,0.12)" : "0 10px 24px rgba(0,0,0,0.35)",
            padding: "10px 12px",
            pointerEvents: "none",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span
              style={{
                fontFamily: "'Geist Variable', system-ui, sans-serif",
                fontSize: 11,
                letterSpacing: "0.15em",
                fontWeight: 700,
                color: isLight ? "#b91c1c" : "#ff2d2d",
              }}
            >
              CONFLICT PAIR
            </span>
            <span style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", fontSize: 10, color: isLight ? "#57534e" : "#9c978f" }}>
              {CONFLICT_PLAN.minimum}
            </span>
          </div>
          <div
            style={{
              marginTop: 4,
              fontFamily: "'Geist Variable', system-ui, sans-serif",
              fontSize: 14,
              fontWeight: 700,
              color: isLight ? "#111827" : "#f8fafc",
              letterSpacing: "0.04em",
            }}
          >
            {CONFLICT_PLAN.primary} ↔ {CONFLICT_PLAN.secondary}
          </div>
          <div style={{ marginTop: 3, fontFamily: "'Geist Variable', system-ui, sans-serif", fontSize: 11, color: isLight ? "#57534e" : "#9c978f" }}>
            {CONFLICT_PLAN.cpaLabel}
          </div>
          <div style={{ marginTop: 7, display: "grid", gap: 4 }}>
            {CONFLICT_PLAN.actions.map((action, index) => (
              <div key={action} style={{ display: "flex", gap: 7, alignItems: "flex-start" }}>
                <span
                  style={{
                    width: 5,
                    height: 5,
                    borderRadius: 99,
                    marginTop: 6,
                    background: index === 2 ? tealAccent : isLight ? "#b91c1c" : "#ff2d2d",
                  }}
                />
                <span style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", fontSize: 11, lineHeight: 1.3, color: isLight ? "#111827" : "#e5e7eb" }}>
                  {action}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
