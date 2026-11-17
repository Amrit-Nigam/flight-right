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
  const lastFrameRef = useRef(0);

  const applyPayload = useCallback((aircraft, conflictPayload) => {
    if (!mountedRef.current || !navigator.onLine) return;
    if (aircraft) {
      setFlights(Array.isArray(aircraft.flights) ? aircraft.flights : []);
      setFeed({
        mode: aircraft.mode, source: aircraft.source, provider: aircraft.provider,
        updatedAt: aircraft.updatedAt, error: aircraft.error, replay: aircraft.replay,
        receivedAt: new Date().toISOString(),
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
      const [traffic, assessment] = await Promise.allSettled([
        getLatestAircraft(),
        getActiveConflicts(),
      ]);
      if(traffic.status==='rejected')throw traffic.reason;
      applyPayload(traffic.value, assessment.status==='fulfilled'?assessment.value:null);
      if(assessment.status==='rejected'&&mountedRef.current)setLastError(`${assessment.reason.message} Traffic updates remain available; cached conflict results may be old.`);
      if (mountedRef.current && navigator.onLine) setConnection((c) => (c === "streaming" ? c : "polling"));
    } catch (error) {
      if (!mountedRef.current) return;
      setConnection("offline");
      setLastError(error.message);
    }
  }, [applyPayload]);

  const startPolling = useCallback(() => {
    if (pollRef.current || !navigator.onLine) return;
    pollOnce();
    pollRef.current = setInterval(pollOnce, POLL_MS);
  }, [pollOnce]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const connect = useCallback(function connectSocket() {
    if (!navigator.onLine || socketRef.current?.readyState < 2) return;
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
      // Opening a socket is not evidence that a traffic frame arrived.
    };
    socket.onmessage = (event) => {
      if(!mountedRef.current || socketRef.current!==socket)return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === "update" && navigator.onLine && message.aircraft) {
          applyPayload(message.aircraft, message.conflicts);
          lastFrameRef.current=Date.now();
          stopPolling();
          setConnection("streaming");
        }
      } catch {
        /* a malformed frame is not worth tearing the socket down for */
      }
    };
    socket.onerror = () => { if(mountedRef.current)startPolling(); };
    socket.onclose = () => {
      if (!mountedRef.current || socketRef.current!==socket) return;
      socketRef.current = null;
      // Poll while the socket is away, so the picture keeps updating rather than
      // freezing on the last frame, and keep trying to get the socket back.
      startPolling();
      setConnection((c) => (!navigator.onLine || c === "offline" ? "offline" : c==='polling'?'polling':"connecting"));
      reconnectRef.current = setTimeout(connectSocket, RECONNECT_MS);
    };
  }, [applyPayload, startPolling, stopPolling]);

  useEffect(() => {
    mountedRef.current = true;
    const offline=()=>{
      setConnection('offline');
      setLastError('Browser offline. Traffic and conflict services disconnected; cached reports remain visible.');
      stopPolling();
      socketRef.current?.close();
    };
    const online=()=>{setConnection('connecting');startPolling();pollOnce();connect();};
    window.addEventListener('offline',offline);
    window.addEventListener('online',online);
    startPolling();
    connect();
    const watchdog=setInterval(()=>{
      if(navigator.onLine&&lastFrameRef.current&&Date.now()-lastFrameRef.current>15000){
        setConnection(c=>c==='streaming'?'connecting':c);startPolling();
      }
    },5000);
    return () => {
      mountedRef.current = false;
      window.removeEventListener('offline',offline);
      window.removeEventListener('online',online);
      clearInterval(watchdog);
      stopPolling();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.onmessage = null;
        socketRef.current.onerror = null;
        socketRef.current.close();
        socketRef.current=null;
      }
    };
  }, [connect, pollOnce, startPolling, stopPolling]);

  return { flights, conflicts, feed, connection, lastError, refresh: pollOnce };
}
