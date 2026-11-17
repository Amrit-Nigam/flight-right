export function instructionText(row) {
  const value=row.value;
  if(['CLIMB','DESCEND'].includes(row.action))return `${row.action} ${Number(value).toLocaleString('en-US')} ft`;
  if(row.action==='TURN')return `HDG ${String(Math.round(value)).padStart(3,'0')}°`;
  return `${row.action} ${(row.fix || value) ?? ''}${row.action==='SPEED'?' kt':''}`;
}
export function sameInstructionScope(row,context) {
  const recorded=row.report?.displayContext || row.notes?.displayContext;
  return !!recorded && recorded.scope===context?.scope && recorded.runId===context?.runId;
}
export function flightInstructions(data,flight) {
  const history=(data?.history || []).filter(r=>r.matched_icao24===flight?.icao24 && r.callsign_matched===flight?.callsign);
  const current=history.filter(r=>sameInstructionScope(r,data?.context));
  const accepted=current.filter(r=>r.applied);
  const level=accepted.find(r=>['CLIMB','DESCEND'].includes(r.action));
  const direction=accepted.find(r=>['TURN','DIRECT'].includes(r.action));
  return {history,current,earlier:history.filter(r=>!sameInstructionScope(r,data?.context)),
    levelRecord:level,directionRecord:direction,
    level:level?instructionText(level):null,direction:direction?instructionText(direction):null,
    at:accepted[0]?.issued_at ? `${accepted[0].issued_at.slice(11,19)}Z` : null};
}
export function instructionSummaries(data,flights) {
  return Object.fromEntries(flights.map(f=>[f.callsign,flightInstructions(data,f)]));
}
