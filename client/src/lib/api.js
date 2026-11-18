// Talks to the FlightRight backend.
//
// Restored from the Express-era client that was deleted on 30 August 2026 and extended
// for the model endpoints that did not exist then: conflicts, resolutions and the
// server-side audit log. The request envelope is unchanged, so this file reads the same
// way it did before - only the base URL and the endpoint list have grown.

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const service=path.includes('/trajectory')?'Forecast':path.includes('/history')?'Track history':path.startsWith('/api/aircraft')?'Traffic':path.startsWith('/api/planning')?'Sequence':path.startsWith('/api/conflicts')?'Conflict assessment':path.startsWith('/api/clearances')?'Instructions':path.startsWith('/api/airport')?'Airport':path.startsWith('/api/speech')?'Radio':path.startsWith('/api/audit')?'Audit':path.startsWith('/api/workspace')?'Strip workflow':'Backend';
  let response;
  try { response = await fetch(`${API_BASE_URL}${path}`, {
    signal: typeof AbortSignal.timeout==='function' ? AbortSignal.timeout(15000) : undefined,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  }); } catch(error) {
    throw new Error(`${service} service ${error.name==='TimeoutError'?'timed out':'unreachable'}. ${navigator.onLine?'Check the local server connection.':'Browser is offline.'}`);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    const detail=data.detail || data.error;
    throw new Error(`${service}: ${typeof detail==='string'?detail:detail?.problems?.join('; ') || detail?.message || `Request failed (${response.status})`}`);
  }
  return data;
}

// ---------------------------------------------------------------------- aircraft
export const getLatestAircraft = () => request("/api/aircraft/latest");
export const getAircraftSource = () => request("/api/aircraft/source");
export const getAircraftHistory = (icao24) =>
  request(`/api/aircraft/history?icao24=${encodeURIComponent(icao24)}`);
export const getAircraftTrajectory = (icao24) =>
  request(`/api/aircraft/trajectory?icao24=${encodeURIComponent(icao24)}`);
export const setDataMode = (mode) =>
  request("/api/aircraft/mode", { method: "POST", body: JSON.stringify({ mode }) });

// ---------------------------------------------------------------------- conflicts
export const getActiveConflicts = () => request("/api/conflicts/active");
export const getResolution = (pair) =>
  request(`/api/recommend/resolution?pair=${encodeURIComponent(pair)}`);

// ------------------------------------------------------------------- controller
// Neither of these transmits anything to an aircraft. They record what the controller
// decided. The system has no link to an aircraft and is not permitted one.
export const acceptSuggestion = (payload) =>
  request("/api/actions/accept", { method: "POST", body: JSON.stringify(payload) });
export const dismissSuggestion = (payload) =>
  request("/api/actions/dismiss", { method: "POST", body: JSON.stringify(payload) });

// ---------------------------------------------------------------------- audit
export const postAuditLog = (entry) =>
  request("/api/audit", { method: "POST", body: JSON.stringify(entry) });
export const getAuditLog = ({ limit = 200, level, search } = {}) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (level && level !== "all") params.set("level", level);
  if (search) params.set("search", search);
  return request(`/api/audit?${params.toString()}`);
};

export const getHealth = () => request("/api/health");
export const getWorkspace = () => request("/api/workspace");
export const updateWorkspace = (payload) => request("/api/workspace/event", { method: "POST", body: JSON.stringify(payload) });

// ---------------------------------------------------------------------- airport
// VABB's real runways, the METAR for the time on screen, runway in use and movements derived
// from the tracks (server/app/services/airport_service.py).
export const getAirport = () => request("/api/airport");

// ---------------------------------------------------------------------- clearances
// A typed instruction to one aircraft. Recorded, and it reshapes that aircraft's predicted
// paths; nothing is ever transmitted.
export const submitClearance = (payload) =>
  request("/api/clearances", { method: "POST", body: JSON.stringify(payload) });

// ---------------------------------------------------------------------- speech
export const getSpeechStatus = () => request("/api/speech/status");
export const getSpeechClips = () => request("/api/speech/clips");
export const speechClipAudioUrl = (id) => `${API_BASE_URL}/api/speech/clips/${encodeURIComponent(id)}/audio`;
export const hearClip = (id, cached = true, role = "auto") =>
  request(`/api/speech/hear?clip=${encodeURIComponent(id)}&cached=${cached}&role=${encodeURIComponent(role)}`, { method: "POST" });
export const getTranscriptions = (limit = 20) => request(`/api/speech/transcriptions?limit=${limit}`);
// Audio recorded from the controller's microphone (a WAV blob, 30 s at most) through the
// whole speech chain.
export const hearAudio = async (wavBlob, role = "auto", { live = false, heardAt, signal } = {}) => {
  const params = new URLSearchParams({ role, live: String(live) });
  if (heardAt != null) params.set("heard_at", String(heardAt));
  const response = await fetch(`${API_BASE_URL}/api/speech/hear?${params}`, {
    method: "POST", headers: { "Content-Type": "audio/wav" }, body: wavBlob, signal,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || `Request failed: ${response.status}`);
  return data;
};

export const getRadioConversation = () => request("/api/speech/conversation");
export const reviewRadioTransmission = (transcriptionId, text, role) => request("/api/speech/review", {
  method: "POST", body: JSON.stringify({ transcriptionId, text, role }),
});

export const streamUrl = () => `${API_BASE_URL.replace(/^http/, "ws")}/ws/stream`;
export { API_BASE_URL };

export const getClearances = (icao24) => request(`/api/clearances?limit=100${icao24?`&icao24=${encodeURIComponent(icao24)}`:''}`);

export const getPlan = () => request("/api/planning");
export const changePlan = (payload) => request("/api/planning/event", {method:"POST",body:JSON.stringify(payload)});
export const syncPlanningRadio = (scope) => request('/api/planning/radio/sync',{method:'POST',body:JSON.stringify({scope})});
export const submitPlanningCommunication = (payload) => request('/api/planning/communication',{method:'POST',body:JSON.stringify(payload)});
