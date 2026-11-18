// Display policy only. These ages and scopes never change model eligibility or alerts.
export const TRACK_STALE_SECONDS = 60;
export function reportAge(flight, nowSeconds) {
  return Number.isFinite(flight?.timePosition) && flight.timePosition > 0
    ? Math.max(0, Math.floor(nowSeconds-flight.timePosition)) : null;
}
export function ageLabel(seconds) {
  if (seconds == null) return 'Report age unknown';
  return seconds < 60 ? `${seconds}s old` : `${Math.floor(seconds/60)}m ${seconds%60}s old`;
}
export function presentFlight(flight, nowSeconds) {
  const age=reportAge(flight,nowSeconds);
  const stale=age==null || age>TRACK_STALE_SECONDS || !!flight.staleSelection;
  return {...flight, reportAgeSeconds:age, staleTrack:stale,
    qualityWarning:flight.onGround&&(flight.altitudeFt>10000||flight.speedKt>200)?'Ground flag accompanies high reported altitude or speed; verify the source report.':null,
    phaseLabel:flight.onGround?'On ground / surface movement':`${flight.status || 'Unknown phase'} · inferred`,
    displayEta:stale?'Withheld — old report':flight.eta || 'Unavailable'};
}
export function localTraffic(flight, radius=50) {
  return Number.isFinite(flight.distanceToVabbNm)&&flight.distanceToVabbNm<=radius;
}
export function sortLocalTraffic(flights) {
  const priority=f=>f.status==='CONFLICT'?0:f.onGround?1:/VABB$/.test(f.route || '')?2:3;
  return [...flights].sort((a,b)=>priority(a)-priority(b)
    || String(a.callsign).localeCompare(String(b.callsign)));
}
export const INSTRUCTION_BOUNDS={TURN:[0,360,'Heading must be between 0° and 360°.'],
  CLIMB:[1000,60000,'Altitude must be between 1,000 and 60,000 ft.'],
  DESCEND:[1000,60000,'Altitude must be between 1,000 and 60,000 ft.'],
  SPEED:[100,600,'Speed must be between 100 and 600 kt.']};
export function instructionError(action,value) {
  if (value==='') return 'Enter a value.';
  const n=Number(value), bounds=INSTRUCTION_BOUNDS[action];
  return !Number.isFinite(n)?'Enter a finite number.':bounds&&(n<bounds[0]||n>bounds[1])?bounds[2]:'';
}
export function forecastLabel(track) {
  if(track?.prediction?.status==='ready')return `${Math.round(track.prediction.probability*100)}% candidate weight`;
  if(track?.predictionStatus==='warming')return `History ${track.prediction?.reportsReceived ?? '?'}/${track.prediction?.requiredReports ?? 10} reports · ${track.elapsedSeconds || 0}s waiting`;
  if(track?.predictionStatus==='loading')return `Forecast loading · ${track.elapsedSeconds || 0}s`;
  return `Forecast unavailable${track?.predictionError?` · ${track.predictionError}`:''}`;
}
