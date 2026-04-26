# Client Model Training Notes

Model training should not run in the browser.

This folder exists to document how frontend work connects to model outputs from the server training pipeline.

## Frontend Role

The React client should:

- display model predictions
- display model confidence
- show explanations and conflict metadata
- let the controller accept, dismiss, or override suggestions
- send audit events to the backend

The React client should not:

- collect OpenSky training data directly
- train ML models in the browser
- store model datasets locally
- make safety decisions without backend validation

## Expected Future API

After the server model pipeline is connected, the frontend should consume:

```text
GET /api/conflicts/active
```

Expected response shape:

```json
{
  "ok": true,
  "model": {
    "type": "logistic_regression_baseline",
    "version": "conflict-baseline-model.json"
  },
  "conflicts": [
    {
      "aircraftA": "AI6302",
      "aircraftB": "SG881",
      "probability": 0.87,
      "severity": "HIGH",
      "timeToMinMinutes": 4,
      "minProjectedDistanceNm": 3.8,
      "verticalSeparationFt": 800,
      "explanation": "Projected lateral and vertical separation fall below MVP thresholds."
    }
  ]
}
```

## Frontend Integration Plan

Later, add:

```text
client/src/hooks/useConflictsFeed.js
```

That hook should:

1. poll `/api/conflicts/active`
2. update the conflict banner
3. update the AI suggestions panel
4. record audit events when a prediction is displayed

For now, the training pipeline lives in:

```text
server/modeltraining/
```
