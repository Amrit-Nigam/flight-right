const percent=n=>Number.isFinite(n)?`${Math.round(n*100)}%`:'not reported';
export default function AlertEvidence({alert}) {
  if(!alert)return null;
  return <div className="alert-evidence">
    <strong>Why this pair is listed</strong>
    <p>{Number.isFinite(alert.nominalCpa?.lateralNm)?`Nominal straight-line CPA: ${alert.nominalCpa.lateralNm.toFixed(2)} NM / ${Math.round(alert.nominalCpa.verticalFt)} ft.`:'Nominal straight-line geometry not separately supplied in this payload.'} Nominal rule: {alert.ruleIsConflict==null?'not reported':alert.ruleIsConflict?'breach predicted':'no breach predicted'}.</p>
    <p>Qualifying gate: <strong>{alert.triggerGate || 'not supplied in this payload'}</strong>{alert.confirmationUpdates!=null?` · ${alert.confirmationUpdates} consecutive qualifying updates`:''}. {alert.triggerGate==='classifier'?'The classifier uses its configured operating threshold; 50% is not its decision boundary.':alert.triggerGate==='separation-minimum'?'Deterministic separation minimum qualifies independently of classifier output.':alert.triggerGate==='probability'?'Candidate-path probability gate applies.':''}</p>
    {Number.isFinite(alert.alternativeCpa?.lateralNm)&&<p>Representative alternative-path CPA: {alert.alternativeCpa.lateralNm.toFixed(2)} NM / {Math.round(alert.alternativeCpa.verticalFt)} ft.</p>}
    <p>Alternative-path breach weight: {percent(alert.multipathProbability)} · {alert.combinationsBreaching ?? '?'} candidate combinations breach. This can differ from the nominal path above.</p>
    <p>Classifier conflict probability: {percent(alert.probability)}. This is a separate calibrated classifier output, not the alert tier or option reliability.</p>
    {alert.classifierDecision?.alert!=null&&<p>Saved classifier verdict: {alert.classifierDecision.alert?'alert':'no alert'}.{Number.isFinite(alert.classifierDecision.calibratedThreshold)?` Equivalent calibrated operating threshold: ${(alert.classifierDecision.calibratedThreshold*100).toFixed(2)}%.`:''} The implementation compares its raw output with the saved raw threshold.</p>}
    <details><summary>Trigger and processing basis</summary><p>{alert.reason}</p><p>The server combines path geometry, classifier / probability gates, time horizon and confirmation across updates. A nominal non-breach does not rule out a classifier or alternative-path alert.</p></details>
  </div>;
}
