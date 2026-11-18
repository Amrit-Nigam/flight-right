import { usePlanning } from "@/hooks/usePlanning";
import '@/workspace.css';
import SequencePanel, { PlanningControls, PlanningFlightActions, InstructionJournal } from "@/components/SequencePanel";
import StripOperations from "@/components/StripOperations";
import { useWorkspace } from "@/hooks/useWorkspace";
import FlightInstructions from '@/components/FlightInstructions';
import SequenceCommunications from '@/components/SequenceCommunications';
import ModelOverview from '@/components/ModelOverview';
import {instructionSummaries} from '@/lib/instructionContext';
import { useState, useCallback, useEffect, useMemo, useRef, lazy, Suspense } from "react";
import WorkspaceHeader from "@/components/WorkspaceHeader";
import ExaminerDemo from '@/components/ExaminerDemo';
import {useWideLayout,useNarrowLayout} from "@/hooks/useWideLayout";
import MetricsRow from "@/components/MetricsRow";
import ConflictBanner from "@/components/WorkspaceConflictBanner";
import ResolveModal from "@/components/ResolveModal";
import SuccessToast from "@/components/SuccessToast";
import RadarCanvas from "@/components/RadarCanvas";
import AIAuditTrail from "@/components/AIAuditTrail";
const FlightRadarMap = lazy(() => import("@/components/FlightRadarMap.tsx"));
import TimelinePanel from "@/components/TimelinePanel";
import ControllerWorkspace from "@/components/ControllerWorkspace";
import FlightDetailDrawer from "@/components/FlightDetailDrawer";
import AISuggestionsPanel from "@/components/AISuggestionsPanel";
import WatchListPanel from "@/components/WatchListPanel";
import DataSourceBar from "@/components/DataSourceBar";
import RunwayStatusPanel from "@/components/RunwayStatusPanel";
import NLPCommsPanel from "@/components/NLPCommsPanel";

import { useLiveData } from "@/hooks/useLiveData";
import { useFlightTrack } from "@/hooks/useFlightTrack";
import { useBackendInfo } from "@/hooks/useBackendInfo";
import {useDisplayClock} from '@/hooks/useDisplayClock';
import {presentFlight,forecastLabel} from '@/lib/trafficPresentation';
import {
  conflictFromAlerts, metricsFromState, resolveOptionsFromAlert,
  suggestionsFromAlerts, timelineFromAlerts, watchListFromAlerts, withConflictStatus,
} from "@/lib/adapters";
import { acceptSuggestion, dismissSuggestion } from "@/lib/api";
import { logActivity, logAudit } from "@/lib/siteLogger";

export default function HomePage() {
  // Everything on this page comes from the backend. There is no mock traffic, no mock
  // conflict and no mock resolution: if the backend is unreachable the dashboard says
  // so rather than showing aircraft that do not exist.
  const { flights: rawFlights, conflicts, feed, connection, lastError, refresh } = useLiveData();
  // Runways, METAR, runway in use (derived from the tracks), safety constants and the controller
  // identity -- the facts the panels used to invent.
  const { health, airport } = useBackendInfo();
  const constants = health?.constants || null;
  const workspace = useWorkspace();
  const planning = usePlanning(feed.source);
  const displayTime=useDisplayClock(feed,connection);
  const trafficScope=`${feed.source}:${feed.replay?.session || ''}:${feed.dataTimeUtc?.slice(0,10) || ''}:cycle${feed.replay?.cycle || 0}`;

  const active = useMemo(()=>conflicts.active || [],[conflicts.active]);
  const flights = useMemo(() => withConflictStatus(rawFlights, active).map(f=>presentFlight(f,displayTime)), [rawFlights, active,displayTime]);
  const conflict = useMemo(() => conflictFromAlerts(active, constants), [active, constants]);
  const suggestions = useMemo(() => suggestionsFromAlerts(active), [active]);
  const watchList = useMemo(() => watchListFromAlerts(active), [active]);
  const metrics = useMemo(
    () => metricsFromState(flights, conflicts, feed), [flights, conflicts, feed]);
  const resolveOptions = useMemo(() => resolveOptionsFromAlert(conflict, constants), [conflict, constants]);
  const timelineRows = useMemo(() => timelineFromAlerts(active, constants), [active, constants]);

  // The bell: the alert feed's own notifications (the updates that should interrupt), kept
  // for this page session. It used to say "No new system notifications" whatever was happening.
  const [notificationState, setNotificationState] = useState({incoming:null,log:[]});
  const incoming=conflicts.notifications;
  if(incoming?.length && incoming!==notificationState.incoming){
      const seen = new Set(notificationState.log.map((n) => n.key));
      const at = (feed.dataTimeUtc || new Date().toISOString()).slice(11, 19) + "Z";
      const fresh = incoming
        .map((n) => ({ key: `${n.id}|${n.reason}`, pair: n.pair || [], tier: n.tier, reason: n.reason, at }))
        .filter((n) => !seen.has(n.key));
      setNotificationState({incoming,log:fresh.length?[...fresh,...notificationState.log].slice(0,30):notificationState.log});
  }
  const notificationLog=notificationState.log;

  const [resolveModalOpen, setResolveModalOpen] = useState(false);
  const [chosenOption, setSelectedOption] = useState("OPT_1");
  const selectedOption=resolveOptions.some(o=>o.id===chosenOption)?chosenOption:resolveOptions[0]?.id || '';
  const [selectedFlight, setSelectedFlight] = useState(null);
  const [selectionSnapshot, setSelectionSnapshot] = useState(null);
  const currentSelection = flights.find((f) => f.callsign === selectedFlight) || null;
  if(currentSelection && (selectionSnapshot?.flight!==currentSelection || selectionSnapshot.source!==trafficScope)){
    setSelectionSnapshot({flight:currentSelection,source:trafficScope});
  }
  const selectedAircraft = currentSelection || (selectionSnapshot?.flight?.callsign === selectedFlight && selectionSnapshot.source === trafficScope
    ? { ...presentFlight(selectionSnapshot.flight,displayTime), staleSelection: true,staleTrack:true } : null);
  const selectedPlanRow = planning.plan?.rows.find(row => row.id === selectedFlight);
  const intentRevision=(workspace.data.clearances?.inForce?.[selectedAircraft?.icao24] || []).map(c=>c.issued_at).join('|');
  const selectedTrack = useFlightTrack(selectedAircraft, feed.source, feed.updatedAt, trafficScope, intentRevision);
  const instructions=useMemo(()=>instructionSummaries(workspace.data.clearances,flights),[workspace.data.clearances,flights]);
  const [aiEnabled, setAiEnabled] = useState(true);
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);
  useEffect(() => () => clearTimeout(toastTimer.current), []);
  const [position, setPosition] = useState("tower");
  const [acceptedCount, setAcceptedCount] = useState(0);
  const [handledIds, setHandledIds] = useState(new Set());

  const [theme, setTheme] = useState(()=>{
    try{return localStorage.getItem('aerosync.theme')==='dark'?'dark':'light';}catch{return 'light';}
  });
  useEffect(() => {
    if (theme === "light") document.documentElement.classList.add("light");
    else document.documentElement.classList.remove("light");
    try{localStorage.setItem('aerosync.theme',theme);}catch{/* Theme still works when browser storage is unavailable. */}
  }, [theme]);
  const toggleTheme = () =>
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      logAudit("dashboard:theme", "Application color theme switched", { next });
      return next;
    });

  // Only confirmed tier 1 alarms are interruptions. Tier 2 is a watch list.
  const alertCount = (conflicts.counts?.tier_1 ?? 0);

  const showToast = useCallback((message, type = "success") => {
    clearTimeout(toastTimer.current);
    setToast({ message, type });
    toastTimer.current = setTimeout(() => setToast(null), 6000);
  }, []);

  useEffect(() => {
    const handleToastEvent = (e) => showToast(e.detail);
    window.addEventListener("show-toast", handleToastEvent);
    return () => window.removeEventListener("show-toast", handleToastEvent);
  }, [showToast]);

  const handleResolveClick = () => {
    if (!conflict) return;
    logAudit("conflict:flow", "Conflict resolution flow opened", { pair: [conflict.flight1, conflict.flight2] });
    setResolveModalOpen(true);
  };

  /**
   * The controller accepted a suggestion. This RECORDS the decision in the server-side
   * audit log. It does not transmit anything to an aircraft and it does not change the
   * traffic picture: the next surveillance update decides whether the conflict is gone,
   * exactly as it would in a real centre.
   */
  const handleAcceptResolution = async () => {
    if (!conflict) return;
    const option = resolveOptions.find((o) => o.id === selectedOption) || resolveOptions[0];
    try {
      await acceptSuggestion({
        conflictId: conflict.id,
        callsign: option?.manoeuvre?.aircraft,
        action: option ? `Accepted: ${option.action}` : "Accepted resolution",
        confidence: option ? Number(String(option.confidence).replace("%", "")) / 100 : null,
        modelVersion: conflict.sources,
        detail: { optionId: selectedOption, pair: [conflict.flight1, conflict.flight2],
                  manoeuvre: option?.manoeuvre, score: option?.score },
      });
      showToast(`Decision recorded — ${conflict.flight1} & ${conflict.flight2}`);
    } catch (error) {
      showToast(`Could not record the decision: ${error.message}`, "error");
      return;
    }
    setResolveModalOpen(false);
  };

  const handleCancelResolution = async () => {
    if (conflict) {
      try {
        await dismissSuggestion({
          conflictId: conflict.id,
          action: "Dismissed resolution options — handling manually",
          detail: { optionId: selectedOption, pair: [conflict.flight1, conflict.flight2] },
        });
      } catch (error) {
        showToast(`Could not record dismissal: ${error.message}`, "error");
        return;
      }
    }
    setResolveModalOpen(false);
  };

  const handleAcceptSuggestion = async (suggestion) => {
    try {
      await acceptSuggestion({
        conflictId: suggestion.id,
        callsign: suggestion.flights[0],
        action: `Accepted suggestion: ${suggestion.text}`,
        confidence: Number(String(suggestion.confidence).replace("%", "")) / 100,
        detail: { pair: suggestion.flights, tier: suggestion.tier },
      });
      setAcceptedCount((c) => c + 1);
      setHandledIds((prev) => new Set([...prev, suggestion.episodeKey]));
      showToast(suggestion.actionToast);
    } catch (error) {
      showToast(`Could not record the decision: ${error.message}`, "error");
    }
  };

  const handleDismissSuggestion = async (id) => {
    const suggestion = suggestions.find((s) => s.id === id);
    try {
      await dismissSuggestion({
        conflictId: id,
        action: "Dismissed AI suggestion",
        detail: { pair: suggestion?.flights },
      });
    } catch (error) {
      showToast(`Could not dismiss suggestion: ${error.message}`, "error");
      return;
    }
    setHandledIds((prev) => new Set([...prev, suggestion?.episodeKey ?? id]));
  };

  const handleSelectFlight = (callsign, meta = {}) => {
    const next = callsign || null;
    logAudit("flights:select", next ? "Flight selection set" : "Flight selection cleared", {
      callsign: next, surface: meta.surface || "unknown",
    });
    setSelectedFlight(next);
    if(next){setPanel('flight');setLastTool('flight');if(meta.surface==='flight-strip')setTrafficVisibility(true);}
    setSelectionSnapshot(next ? {flight: flights.find(f => f.callsign === next) || selectedAircraft, source:trafficScope} : null);
  };

  const [timelineOpen, setTimelineOpen] = useState(false);
  const [auditTrailOpen, setAuditTrailOpen] = useState(false);
  const [mapView, setMapView] = useState("map");
  const [weatherOn, setWeatherOn] = useState(false);

  const bootLogged = useRef(false);
  useEffect(() => {
    if (bootLogged.current || connection === "connecting") return;
    bootLogged.current = true;
    logAudit("session:dashboard", "Controller dashboard connected to backend", {
      connection, source: feed.source, mode: feed.mode,
    });
    logActivity("dashboard", `Dashboard connected (${connection}, ${feed.source || "no source"})`);
  }, [connection, feed.source, feed.mode]);

  const visibleSuggestions = suggestions.filter((s) => !handledIds.has(s.episodeKey));
  const wide=useWideLayout();
  const narrow=useNarrowLayout();
  const [trafficVisibility,setTrafficVisibility]=useState('auto');
  const trafficOpen=trafficVisibility==='auto'?wide:trafficVisibility;
  const [panel,setPanel]=useState(null);
  const [lastTool,setLastTool]=useState('ml');
  const activeTool=panel;
  const openTool=key=>{if(key==='traffic')setTrafficVisibility(true);else{setPanel(key);setLastTool(key);}};
  const closeInspector=()=>{setPanel(null);document.querySelector(`[data-workspace-tool="${lastTool}"]`)?.focus();};
  const closeTraffic=()=>{setTrafficVisibility(false);document.querySelector('[data-workspace-tool="traffic"]')?.focus();};
  const closeTool=()=>{setPanel(null);setTrafficVisibility(false);document.querySelector('[data-workspace-tool="map"]')?.focus();};
  const mapHidden=narrow?(trafficOpen||!!activeTool):(!wide&&trafficOpen&&!!activeTool);
  useEffect(()=>{const content=document.querySelector('[data-tool-scroll]');if(content)content.scrollTop=0;},[activeTool,selectedFlight]);
  useEffect(()=>{if(activeTool)document.querySelector('.workspace-inspector')?.focus({preventScroll:true});},[activeTool]);
  const modelVersions=Object.keys(conflicts.modelVersions || {}).length?conflicts.modelVersions:health?.models || {};
  const modelCount=['trajectory_residual','trajectory_multipath','xgboost_conflict'].filter(key=>modelVersions[key]).length;
  const tools=[{id:'traffic',label:'Traffic',count:flights.length},{id:'sequence',label:'Sequence',count:planning.plan?.rows.length},
    {id:'flight',label:'Details',count:selectedFlight?1:null},{id:'ml',label:'ML',count:visibleSuggestions.length || `${modelCount}/3`},
    {id:'radio',label:'Radio'},{id:'airport',label:'Airport'}];
  const toolTitle=activeTool==='flight'&&selectedFlight?selectedFlight:tools.find(t=>t.id===activeTool)?.label || 'Tools';

  return <div className="workspace-root">
    <WorkspaceHeader feed={feed} connection={connection} airport={airport} health={health} theme={theme}
      onToggleTheme={toggleTheme} notifications={notificationLog} alertCount={alertCount} aiEnabled={aiEnabled}
      onToggleAI={()=>setAiEnabled(v=>!v)} />
    <ExaminerDemo mode={feed.mode} onTrafficChange={async()=>{await refresh();await planning.refresh();await workspace.refresh();}}/>
    <nav aria-label="Workspace tools" className="workspace-nav">
      <div className="workspace-tool-buttons">
        <button data-workspace-tool="map" aria-pressed={!activeTool&&!trafficOpen} onClick={closeTool}>Map</button>
        {tools.map(t=><button key={t.id} data-workspace-tool={t.id} aria-controls={`tool-${t.id}`} aria-pressed={t.id==='traffic'?trafficOpen:activeTool===t.id} onClick={()=>t.id==='traffic'?setTrafficVisibility(!trafficOpen):openTool(t.id)}>{t.label}{t.count!=null&&<span>{t.count}</span>}</button>)}
      </div>
      <div className="workspace-authority">
        <label><span className="sr-only">Controller position</span><select aria-label="Controller position" value={position} onChange={e=>{setPosition(e.target.value);logAudit('workspace:position','Working position view changed',{position:e.target.value});}}><option value="tower">Tower</option><option value="ground">Ground</option><option value="clearance">Clearance</option></select></label>
        {planning.plan?.mode!=='normal'&&planning.plan&&<button className="workspace-mode" onClick={()=>openTool('sequence')}>{planning.plan.mode==='emergency'?`Emergency · ${planning.plan.emergency}`:'ATCO control'}</button>}
        <button className="workspace-takeover" disabled={!planning.plan} onClick={()=>{window.speechSynthesis?.cancel();planning.act('takeover');}}>Take control</button>
      </div>
    </nav>
    {(connection==='offline'||lastError||feed.error)&&<div role="alert" className="workspace-error">{lastError || feed.error || 'Traffic service disconnected.'} {flights.length?'Cached aircraft reports remain displayed; check each report age.':'No traffic available.'}</div>}
    {planning.error&&connection!=='offline'&&<div role="alert" className="workspace-error">{planning.error} {planning.plan?'Last saved plan remains displayed.':''} <button onClick={()=>openTool('sequence')}>Open sequence</button><button onClick={planning.refresh}>Refresh</button></div>}
    <ConflictBanner conflict={conflict} onResolveClick={handleResolveClick} theme={theme}/>

    <div className="workspace-panel-access" aria-label="Panel visibility">
      <button aria-controls="tool-traffic" aria-expanded={trafficOpen} onClick={()=>trafficOpen?closeTraffic():openTool('traffic')}>{trafficOpen?'Hide traffic':'Show traffic'}</button>
      <span>{selectedFlight?`Selected: ${selectedFlight}`:'Select an aircraft to inspect'}</span>
      <button aria-controls="workspace-inspector" aria-expanded={!!activeTool} onClick={()=>activeTool?closeInspector():openTool(lastTool)}>{activeTool?'Hide right panel':selectedFlight&&lastTool==='flight'?'Show details':'Show right panel'}</button>
    </div>
    <main className={`workspace-main ${trafficOpen?'has-traffic':''} ${activeTool?'has-tool':''}`}>
      <aside className="workspace-tool-panel workspace-traffic-panel" hidden={!trafficOpen} aria-label="Traffic strips panel">
        <header className="workspace-tool-title"><h2>Traffic strips <small>{flights.length}</small></h2><button aria-label="Close traffic panel" onClick={closeTraffic}>Hide ×</button></header>
        <div className="workspace-tool-content"><div id="tool-traffic" className="tool-page traffic-page"><ControllerWorkspace compact position={position} flights={flights} selectedFlight={selectedFlight} onSelectFlight={handleSelectFlight} source={feed.source} workspace={workspace}/></div></div>
      </aside>
      <section className="workspace-map" hidden={mapHidden} aria-label="Map workspace">
        <div className="map-toolbar workspace-map-toolbar">
          <div className="workspace-map-switch"><button aria-pressed={mapView==='map'} onClick={()=>setMapView('map')}>Map view</button><button aria-pressed={mapView==='radar'} onClick={()=>setMapView('radar')}>Radar</button></div>
          {selectedAircraft&&<button className="workspace-selected-track" onClick={()=>openTool('ml')} title="View model and forecast details">{selectedFlight} · {selectedAircraft.staleTrack?'Old report · forecast context only':forecastLabel(selectedTrack)}</button>}
          <button className="workspace-weather" aria-pressed={weatherOn} onClick={()=>setWeatherOn(v=>!v)}>Weather</button>
        </div>
        <div className="workspace-map-canvas">
          <div className="absolute inset-0" hidden={mapView!=='map'}>
            <Suspense fallback={<MapLoading/>}><FlightRadarMap flights={flights} conflict={conflict} selectedFlight={selectedAircraft?selectedFlight:null} selectedTrack={selectedTrack} onSelectFlight={handleSelectFlight} theme={theme} airport={airport} constants={constants} source={feed.source} instructionSummaries={instructions}/></Suspense>
          </div>
          <div className="absolute inset-0" hidden={mapView!=='radar'}><RadarCanvas onSelectFlight={handleSelectFlight} flights={flights} selectedFlight={selectedAircraft?selectedFlight:null} theme={theme} selectedTrack={selectedTrack} conflict={conflict} airport={airport} feed={feed}/></div>
          {weatherOn&&<section aria-label="Map weather" className="workspace-weather-card"><div className="flex justify-between gap-3"><strong>VABB weather</strong><button aria-label="Close weather" onClick={()=>setWeatherOn(false)}>×</button></div>{airport?.metar?<><p>{airport.metar.raw}</p><p>Issued {airport.metar.issuedUtc.replace('T',' ')} · {airport.metar.source}{airport.metar.stale?' · STALE':''}</p></>:<p>No METAR available for this time.</p>}</section>}
        </div>
      </section>

      <aside id="workspace-inspector" className="workspace-tool-panel workspace-inspector" hidden={!activeTool} tabIndex={-1} aria-labelledby="workspace-tool-title">
        <header className="workspace-tool-title"><h2 id="workspace-tool-title">{toolTitle}</h2><button aria-label="Close right panel" onClick={closeInspector}>Hide ×</button></header>
        <div className="workspace-tool-content" data-tool-scroll>
          <div id="tool-sequence" className="tool-page" hidden={activeTool!=='sequence'}>
            <PlanningControls planning={{...planning,error:null}} selectedFlight={selectedFlight}/>
            <SequencePanel key={planning.plan?.scope || 'connecting'} planning={planning} selectedFlight={selectedFlight} onSelectFlight={handleSelectFlight} flights={flights} nowSeconds={displayTime}/>
            <details><summary>Plan advisories and delivery history</summary><InstructionJournal planning={planning}/></details>
          </div>
          <div id="tool-flight" className="tool-page" hidden={activeTool!=='flight'} aria-label="Flight details and tools">
            {!selectedAircraft&&!selectedPlanRow&&<p>{selectedFlight?`${selectedFlight} is no longer available in this traffic scope.`:'Select an aircraft on the map or in Traffic to view its details and recorded instructions.'}<button className="block mt-3 underline" onClick={()=>{openTool('traffic');closeInspector();}}>Choose a flight</button></p>}
            {selectedFlight&&<button className="self-end text-xs underline" onClick={()=>{handleSelectFlight(null);closeInspector();}}>Clear selected flight</button>}
            {selectedPlanRow&&!selectedAircraft&&<section aria-label="Selected planned movement"><h3>{selectedPlanRow.callsign} · planned {selectedPlanRow.kind}</h3><p>{new Date((planning.plan.baseTime+selectedPlanRow.target)*1000).toISOString().replace('T',' ')}</p><p>{selectedPlanRow.provenance}</p><p>No current aircraft report is linked to this movement.</p><button className="underline mt-2" onClick={()=>openTool('sequence')}>Edit sequence</button></section>}
            <FlightDetailDrawer embedded key={`details-${selectedFlight || 'none'}`} flight={selectedAircraft} onClose={closeInspector} theme={theme}/>
            <FlightInstructions key={`instructions-${selectedAircraft?.icao24 || 'none'}`} flight={selectedAircraft} shared={workspace.data.clearances}/>
            <PlanningFlightActions planning={planning} flight={selectedAircraft}/>
            {selectedAircraft&&!selectedAircraft.staleSelection&&<details><summary>Coordination and handoffs</summary><StripOperations key={selectedAircraft.icao24} flight={selectedAircraft} position={position} workspace={workspace}/></details>}
          </div>
          <div id="tool-ml" className="tool-page" hidden={activeTool!=='ml'}>
            <ModelOverview health={health} conflicts={conflicts} track={selectedTrack} flight={selectedAircraft} connection={connection} suggestionCount={visibleSuggestions.length} onSuggestions={()=>document.getElementById('model-suggestions')?.scrollIntoView({block:'nearest'})}/>
            <div id="model-suggestions"><AISuggestionsPanel suggestions={visibleSuggestions} onAccept={handleAcceptSuggestion} onDismiss={handleDismissSuggestion} aiEnabled={aiEnabled} acceptedCount={acceptedCount} selectedFlight={selectedFlight} onSelectFlight={handleSelectFlight}/></div>
            <WatchListPanel items={watchList} lowConfidence={conflicts.lowConfidence} theme={theme}/>
            <details><summary>Sector metrics</summary><MetricsRow metricsData={metrics}/></details>
            <div className="relative"><AIAuditTrail isOpen={auditTrailOpen} onToggle={()=>setAuditTrailOpen(v=>!v)}/></div>
          </div>
          <div id="tool-radio" className="tool-page" hidden={activeTool!=='radio'}><SequenceCommunications key={`communications-${planning.plan?.scope || 'none'}`} planning={planning} selectedFlight={selectedFlight}/><details><summary>Live audio receiver and radio transcript</summary><NLPCommsPanel/></details></div>
          <div id="tool-airport" className="tool-page" hidden={activeTool!=='airport'}><RunwayStatusPanel airport={airport}/><details><summary>Feed status and provenance</summary><DataSourceBar feed={feed} connection={connection} lastError={lastError} conflicts={conflicts} theme={theme}/></details><p className="text-xs text-[var(--text-muted)]">Planning demonstration · no pilot transmission. Route lookup is not a filed flight plan.</p></div>
        </div>
      </aside>
    </main>
    <div className="workspace-timeline"><TimelinePanel isOpen={timelineOpen} onToggle={()=>setTimelineOpen(v=>!v)} rows={timelineRows} dataTimeUtc={feed.dataTimeUtc} lookAheadSeconds={constants?.lookAheadSeconds}/></div>
    <ResolveModal open={resolveModalOpen} conflict={conflict} options={resolveOptions} countdown={conflict?.countdown || 0} selectedOption={selectedOption} onSelectOption={setSelectedOption} onApply={handleAcceptResolution} onCancel={handleCancelResolution} previewCommands={feed.mode === 'examiner'}/>
    <SuccessToast toast={toast}/>
  </div>;
}

function MapLoading() {
  return (
    <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center",
                  justifyContent: "center", background: "var(--bg-base)" }}>
      <span style={{ fontFamily: "'Geist Variable', system-ui, sans-serif", fontSize: 12,
                     color: "var(--text-muted)", letterSpacing: "0.2em" }}>
        LOADING RADAR MAP…
      </span>
    </div>
  );
}
