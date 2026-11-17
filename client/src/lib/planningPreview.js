// Display-only projection of the existing single-runway sandbox constraints.
// Saving always goes through server validation; this does not establish ATC feasibility.
export function previewSequence(plan, order) {
  const byId = new Map(plan.rows.map(row => [row.id, row]));
  let previous = -(plan.gap ?? 120);
  const rows = [];
  for (const id of order) {
    const row = byId.get(id);
    if (!row) return {rows, error: 'Plan changed. Cancel and propose the order again.'};
    const earliest = Math.max(row.earliest, previous + (plan.gap ?? 120));
    if (row.pinned && row.target < earliest) return {rows, error: `Pinned slot for ${row.callsign} blocks this sequence.`};
    const target = row.pinned ? row.target : earliest;
    if (target > row.latest) return {rows, error: `${row.callsign} exceeds its sandbox time window.`};
    rows.push({...row, previousTarget: row.target, target});
    previous = target;
  }
  return {rows, error: null};
}
