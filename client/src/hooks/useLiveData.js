// One subscription to the backend, feeding the whole dashboard.
//
// The backend pushes aircraft states and conflict assessments together on a single
// socket, because an alert about two aircraft is meaningless if it arrives before the
// positions it refers to. If the socket cannot be opened - backend down, or a proxy
// that will not upgrade - this falls back to polling the same two endpoints, and says
// which of the two it is doing rather than pretending.
//
// There is no mock fallback. When the backend is unreachable the dashboard shows that
// it is disconnected. Inventing traffic to fill the gap is how a demo ends up showing
// aircraft that do not exist.

import { useCallback, useEffect, useRef, useState } from "react";
import { getActiveConflicts, getLatestAircraft, streamUrl } from "@/lib/api";

const POLL_MS = 5000;
const RECONNECT_MS = 4000;

const EMPTY_CONFLICTS = {
  active: [],
  notifications: [],
  counts: {},
  lowConfidence: { count: 0, reason: "" },
  pairsAssessed: 0,
  eligibleAircraft: 0,
};

export function useLiveData() {
  const [flights, setFlights] = useState([]);
  const [conflicts, setConflicts] = useState(EMPTY_CONFLICTS);
  const [feed, setFeed] = useState({
    mode: null, source: null, provider: null, updatedAt: null,
    error: null, replay: null, creditsRemaining: null, count: 0,
  });
  // "connecting" until the first payload lands, then "streaming" or "polling";
  // "offline" once the backend has stopped answering.
  const [connection, setConnection] = useState("connecting");
  const [lastError, setLastError] = useState(null);

  const socketRef = useRef(null);
  const pollRef = useRef(null);
  const reconnectRef = useRef(null);
  const mountedRef = useRef(true);

  const applyPayload = useCallback((aircraft, conflictPayload) => {
    if (!mountedRef.current) return;
    if (aircraft) {
      setFlights(Array.isArray(aircraft.flights) ? aircraft.flights : []);
      setFeed({
        mode: aircraft.mode, source: aircraft.source, provider: aircraft.provider,
        updatedAt: aircraft.updatedAt, error: aircraft.error, replay: aircraft.replay,
        // The time the picture describes: the recording's own time in replay, now in live.
        dataTimeUtc: aircraft.dataTimeUtc || aircraft.replay?.dataTimeUtc || null,
        creditsRemaining: aircraft.creditsRemaining, count: aircraft.count ?? 0,
      });
    }
    if (conflictPayload) setConflicts({ ...EMPTY_CONFLICTS, ...conflictPayload });
    setLastError(null);
  }, []);

  const pollOnce = useCallback(async () => {
    try {
      const [aircraft, conflictPayload] = await Promise.all([
        getLatestAircraft(),
        getActiveConflicts(),
      ]);
      applyPayload(aircraft, conflictPayload);
      if (mountedRef.current) setConnection((c) => (c === "streaming" ? c : "polling"));
    } catch (error) {
      if (!mountedRef.current) return;
      setConnection("offline");
      setLastError(error.message);
    }
  }, [applyPayload]);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollOnce();
    pollRef.current = setInterval(pollOnce, POLL_MS);
  }, [pollOnce]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    let socket;
    try {
      socket = new WebSocket(streamUrl());
    } catch {
      startPolling();
      return;
    }
    socketRef.current = socket;

    socket.onopen = () => {
      if (!mountedRef.current) return;
      stopPolling();
      setConnection("streaming");
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "update") applyPayload(message.aircraft, message.conflicts);
      } catch {
        /* a malformed frame is not worth tearing the socket down for */
      }
    };
    socket.onerror = () => { /* onclose always follows; handled there */ };
    socket.onclose = () => {
      if (!mountedRef.current) return;
      socketRef.current = null;
      // Poll while the socket is away, so the picture keeps updating rather than
      // freezing on the last frame, and keep trying to get the socket back.
      startPolling();
      setConnection((c) => (c === "offline" ? c : "polling"));
      reconnectRef.current = setTimeout(connect, RECONNECT_MS);
    };
  }, [applyPayload, startPolling, stopPolling]);

  useEffect(() => {
    mountedRef.current = true;
    pollOnce();
    connect();
    return () => {
      mountedRef.current = false;
      stopPolling();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
      }
    };
  }, [connect, pollOnce, stopPolling]);

  return { flights, conflicts, feed, connection, lastError, refresh: pollOnce };
}
