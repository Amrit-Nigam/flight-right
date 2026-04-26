const API_BASE_URL = (import.meta.env.VITE_API_URL || "http://localhost:3000").replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

export function getLatestAircraft() {
  return request("/api/aircraft/latest");
}

export function postAuditLog(entry) {
  return request("/api/audit", {
    method: "POST",
    body: JSON.stringify(entry),
  });
}

export { API_BASE_URL };
