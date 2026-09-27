// Talks to the Flight Right backend.
//
// Restored from the Express-era client that was deleted on 30 August 2026 and extended
// for the model endpoints that did not exist then: conflicts, resolutions and the
// server-side audit log. The request envelope is unchanged, so this file reads the same
// way it did before - only the base URL and the endpoint list have grown.

const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.detail || data.error || `Request failed: ${response.status}`);
  }
  return data;
}

// ---------------------------------------------------------------------- aircraft
export const getLatestAircraft = () => request("/api/aircraft/latest");
export const getAircraftSource = () => request("/api/aircraft/source");
export const getAircraftHistory = (icao24) =>
  request(`/api/aircraft/history?icao24=${encodeURIComponent(icao24)}`);
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

// ---------------------------------------------------------------------- speech
export const getSpeechStatus = () => request("/api/speech/status");
export const getSpeechClips = () => request("/api/speech/clips");
export const speechClipAudioUrl = (id) => `${API_BASE_URL}/api/speech/clips/${encodeURIComponent(id)}/audio`;
export const hearClip = (id, cached = true) =>
  request(`/api/speech/hear?clip=${encodeURIComponent(id)}&cached=${cached}`, { method: "POST" });
export const getTranscriptions = (limit = 20) => request(`/api/speech/transcriptions?limit=${limit}`);

export const streamUrl = () => `${API_BASE_URL.replace(/^http/, "ws")}/ws/stream`;
export { API_BASE_URL };
