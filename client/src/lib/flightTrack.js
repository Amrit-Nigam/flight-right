// Only join actual reports from the current timeline. A missing stretch of feed
// should remain a gap, rather than looking like an observed straight flight.
export function flightTrackSegments(states, current) {
  if (!current) return [];
  const valid = (p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lng)
    && Math.abs(p.lat) <= 90 && Math.abs(p.lng) <= 180;
  const now = current.timePosition;
  const reports = states.filter((p) => valid(p)
    && (!current.source || !p.source || p.source === current.source)
    && (!Number.isFinite(now) || (Number.isFinite(p.timePosition) && p.timePosition <= now)));
  if (valid(current)) reports.push(current);
  const segments = [];
  let segment = [];
  let previous = null;
  for (const report of reports) {
    const gap = previous && Number.isFinite(report.timePosition) && Number.isFinite(previous.timePosition)
      ? report.timePosition - previous.timePosition : 0;
    if (gap < 0 || gap > 120 || (previous && Math.abs(report.lng - previous.lng) > 180)) {
      if (segment.length > 1) segments.push(segment);
      segment = [];
    }
    const last = segment.at(-1);
    if (!last || last[0] !== report.lng || last[1] !== report.lat) segment.push([report.lng, report.lat]);
    previous = report;
  }
  if (segment.length > 1) segments.push(segment);
  return segments;
}
