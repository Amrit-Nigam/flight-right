// Backend payloads -> the shapes the existing React components already render.
//
// The components were written against mockData.js. Rather than rewrite them, this maps
// real model output into the same shapes. Two rules are applied throughout:
//
//   1. A field the models cannot produce is REMOVED, not filled with a plausible
//      number. The resolve modal used to show "ATCO match: 94% (847 cases)" for every
//      option; that is the ML ranker trained on controller decisions, which was
//      deferred and never built. There is no such model and no such dataset, so the
//      field is gone and the real score breakdown takes its place.
//   2. Anything shown carries its reason. Section 12 forbids surfacing a prediction
//      without a rationale, so every option keeps the engine's own explanation string.

export const SEPARATION_LATERAL_NM = 5;
export const SEPARATION_VERTICAL_FT = 1000;

const round = (value, places = 1) =>
  Number.isFinite(value) ? Number(value).toFixed(places) : "--";

/** The most urgent confirmed alarm, in the shape ConflictBanner expects. */
export function conflictFromAlerts(active = []) {
  const alarm = active.find((a) => a.tier === 1) || null;
  if (!alarm) return null;

  const [one, two] = alarm.pair;
  return {
    visible: true,
    id: alarm.id,
    countdown: Math.max(0, Math.round(alarm.timeToCpaSeconds)),
    flight1: one,
    flight2: two,
    detail:
      `${one} vs ${two} — predicted closest approach ` +
      `${round(alarm.cpaLateralNm, 2)} NM / ${Math.round(alarm.cpaVerticalFt)} ft ` +
      `in ${Math.round(alarm.timeToCpaSeconds)} s. ` +
      `Separation standard is ${SEPARATION_LATERAL_NM} NM laterally or ` +
      `${SEPARATION_VERTICAL_FT} ft vertically.`,
    cpaNM: alarm.cpaLateralNm,
    cpaVerticalFt: alarm.cpaVerticalFt,
    severity: alarm.severity,
    reason: alarm.reason,
    probability: alarm.classifierProbability,
    sources: alarm.sources,
    explanation: alarm.explanation,
    resolution: alarm.resolution,
  };
}

/** Model 3's ranked options, in the shape ResolveModal expects. */
export function resolveOptionsFromAlert(alert) {
  const options = alert?.resolution?.options || [];
  return options.map((option, index) => {
    const kind = String(option.manoeuvre_type || "").toUpperCase();
    const magnitude = option.magnitude;
    const unit = option.unit || "";
    const sign = magnitude > 0 ? "+" : "";
    return {
      id: `OPT_${index + 1}`,
      recommended: index === 0,
      label: `OPTION ${index + 1} — ${kind || "MANOEUVRE"}`,
      action: option.explanation,
      result:
        `Resulting separation ${round(option.resulting_lateral_separation_nm, 1)} NM / ` +
        `${Math.round(option.resulting_vertical_separation_ft)} ft. ` +
        `Established about ${Math.round(option.seconds_to_establish)} s from now.`,
      confidence: `${Math.round((option.confidence ?? 0) * 100)}%`,
      // Coarse proxies. The engine says so itself and so does the tooltip.
      fuelImpact: `${sign}${Math.round(option.fuel_equivalent_seconds ?? 0)} s equivalent burn`,
      delayImpact: `${sign}${Math.round((option.delay_seconds ?? 0) / 60)} min ${option.aircraft}`,
      // The real ranking, replacing the invented "ATCO match".
      score: option.score,
      scoreComponents: option.score_components,
      residualRisk: option.residual_risk,
      newConflictRisk: option.new_conflict_risk,
      manoeuvre: { aircraft: option.aircraft, kind, magnitude, unit },
      xaiReason:
        `Ranked by the project's fixed weights: safety 0.60, delay 0.15, fuel 0.10, ` +
        `workload 0.10, confidence 0.05 — total score ${round(option.score, 3)}. ` +
        `Simulated through a ${38} s response delay before the aircraft moves, then at ` +
        `real turn and climb rates. Delay and fuel are approximate track-mile proxies.`,
    };
  });
}

/** The AI suggestions queue, built from confirmed alarms only. */
export function suggestionsFromAlerts(active = []) {
  return active
    .filter((alert) => alert.resolution?.offered && alert.resolution.options.length)
    .map((alert) => {
      const best = alert.resolution.options[0];
      return {
        id: alert.id,
        type: "CONFLICT",
        typeColor: "#ff2d2d",
        priority: alert.severity ? alert.severity.toUpperCase() : "MEDIUM",
        confidence: `${Math.round((best.confidence ?? 0) * 100)}%`,
        flights: alert.pair,
        text: best.explanation,
        // Nothing is auto-applicable. The system offers; the controller decides.
        autoApplicable: false,
        actionToast: `Decision recorded for ${alert.pair.join(" & ")}`,
        tier: alert.tier,
        timeToCpaSeconds: alert.timeToCpaSeconds,
        // ISSUES.md H3 (fixed 25 Sep 2026): what a dismissal is remembered against. The
        // pair id alone hid the pair for the rest of the session -- after it escalated, and
        // after it separated and re-converged. A new encounter (firstSeen), a new tier or a
        // different best manoeuvre is a new situation and is shown again.
        episodeKey: [alert.id, alert.firstSeen, alert.tier, best.manoeuvre_type, best.magnitude].join("|"),
      };
    });
}

/** The watch list: confirmed tier 2 pairs, which never carry a manoeuvre. */
export function watchListFromAlerts(active = []) {
  return active
    .filter((alert) => alert.tier === 2)
    .map((alert) => ({
      id: alert.id,
      pair: alert.pair,
      severity: alert.severity,
      display: alert.display,
      timeToCpaSeconds: alert.timeToCpaSeconds,
      cpaLateralNm: alert.cpaLateralNm,
      cpaVerticalFt: alert.cpaVerticalFt,
      probability: alert.classifierProbability,
      reason: alert.reason,
    }));
}

/**
 * Sector metrics.
 *
 * Only what the system actually measures. The mock version showed an on-time rate, an
 * "AI optimisation score", average spacing, wind and visibility - none of which any
 * model or feed produces. They are gone rather than invented.
 */
export function metricsFromState(flights = [], conflicts = {}, feed = {}) {
  const counts = conflicts.counts || {};
  const enRoute = conflicts.eligibleAircraft ?? 0;
  const climbing = flights.filter((f) => f.verticalRateFpm > 300).length;
  const descending = flights.filter((f) => f.verticalRateFpm < -300).length;

  return [
    { id: "active", value: String(flights.length), label: "AIRCRAFT TRACKED",
      delta: feed.source === "live" ? "OpenSky live" : "Recorded session", valueColor: "amber" },
    { id: "enroute", value: String(enRoute), label: "EN-ROUTE (≥10,000 FT)",
      delta: "Conflict detection applies here", valueColor: "text_primary" },
    { id: "alarms", value: String(counts.tier_1 ?? 0), label: "TIER 1 ALARMS",
      delta: "0–3 min, manoeuvres offered", valueColor: "red", pulse: (counts.tier_1 ?? 0) > 0 },
    { id: "watch", value: String(counts.tier_2 ?? 0), label: "TIER 2 WATCH LIST",
      delta: "3–10 min, no manoeuvre", valueColor: "teal" },
    { id: "assessed", value: String(conflicts.pairsAssessed ?? 0), label: "PAIRS ASSESSED",
      delta: `${conflicts.durationMs ?? 0} ms this update`, valueColor: "text_primary" },
    { id: "climbing", value: String(climbing), label: "CLIMBING",
      delta: "> 300 ft/min", valueColor: "green" },
    { id: "descending", value: String(descending), label: "DESCENDING",
      delta: "< −300 ft/min", valueColor: "amber" },
    { id: "suppressed", value: String(counts.repeats_suppressed ?? 0), label: "REPEATS SUPPRESSED",
      delta: "Still on the active list", valueColor: "text_primary" },
  ];
}

/**
 * Mark the aircraft involved in a confirmed alarm so the list and map colour them.
 * The status field otherwise comes from the flight-phase heuristic in the backend.
 */
export function withConflictStatus(flights = [], active = []) {
  const inConflict = new Map();
  for (const alert of active) {
    for (const callsign of alert.pair) {
      const existing = inConflict.get(callsign);
      if (!existing || alert.tier < existing.tier) inConflict.set(callsign, alert);
    }
  }
  return flights.map((flight) => {
    const alert = inConflict.get(flight.callsign);
    if (!alert) return flight;
    return {
      ...flight,
      status: alert.tier === 1 ? "CONFLICT" : flight.status,
      cpaPair: alert.pair.find((c) => c !== flight.callsign),
      cpaSeconds: Math.round(alert.timeToCpaSeconds),
      alertTier: alert.tier,
      alertSeverity: alert.severity,
    };
  });
}

/**
 * A timeline of predicted closest approaches.
 *
 * The mock version showed scheduled runway slots. Nothing in this system produces a
 * schedule - that needs flight plans, which ADS-B does not carry - so rather than keep
 * inventing arrival times, the timeline now shows what the models actually predict:
 * when each tracked pair reaches its closest point, over the ten-minute look-ahead.
 */
export function timelineFromAlerts(active = []) {
  return active
    .slice()
    .sort((a, b) => a.timeToCpaSeconds - b.timeToCpaSeconds)
    .map((alert) => {
      const startMin = Math.max(0, alert.timeToCpaSeconds / 60);
      return {
        flight: alert.pair.join(" ↔ "),
        aiManaged: alert.tier === 1,
        bars: [{
          type: alert.tier === 1 ? "conflict" : "holding",
          startMin,
          dur: 2,
          label:
            `${alert.tier === 1 ? "⚡ ALARM" : "WATCH"} · ` +
            `${alert.cpaLateralNm.toFixed(2)} NM / ${Math.round(alert.cpaVerticalFt)} ft ` +
            `at T+${Math.round(alert.timeToCpaSeconds)}s`,
        }],
      };
    });
}
