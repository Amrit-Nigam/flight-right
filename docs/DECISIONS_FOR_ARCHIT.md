# Waiting on you

Everything below was measured and then stopped at the point where the project's rules say a
person decides. Each item says what the choice is, the numbers behind it, and where the
evidence is. Nothing here is switched on. Last updated 25 September 2026.

---

## Decisions (they change what a controller is shown or when they are alerted)

**1. Use the autopilot "dialled altitude" in the conflict classifier (plan 9.0).**
The information genuinely helps: at the same false-alarm cost, the classifier catches as many
or more real conflicts in all four seeds tested (0 to 4 more). The choice is how to spend that
gain:
- **Fewer false alarms:** the usual threshold rule cuts them by about 21% (97 → 77 per 1,000
  pairs, averaged over four seeds), but in 2 of 4 seeds it loses 2–3 real conflicts net.
- **More real conflicts caught:** keep today's false-alarm rate, and recall rises (0.9505–0.9604
  against 0.9406–0.9505 for the baseline).

It also needs a **live** dialled-altitude feed. adsb.lol has one (`api.adsb.lol/v2/point/...`),
but the backend does not poll it yet, and the data is ODbL 1.0 licensed, which requires credit.
Evidence: `docs/ablation.md` (last section),
`ml_pipeline/reports/classifier_intent_20260925_050817.json`.

**2. The collapsed "low-confidence" group hides 7 real conflicts (issue H5).** All seven
still have more than three minutes of warning. They stay on the list, but the controller sees
them only as a count until they are inside three minutes. Requiring both models to agree before
collapsing (option B1) cuts that to 3, at the cost of 50 more false rows on the main list
(test split). Evidence: `docs/ISSUES.md` H5, `ml_pipeline/reports/alert_prominence_20260924_193159.json`.

**3. The "more data" trajectory model (plan 3.3 archive row).** It is better at predicting
position across four seeds (arrivals, one of five within 5 NM: 75.6% against 72.0%). But through
the alert chain it was identical on test and cost one real audible alarm on validation, so it
is not served. The model file is kept at
`ml_pipeline/data/processed/seed_runs/multipath_archive_seed42.pkl`.

**4. The classifier's recall floor (GATE 1, open since 5 September).** It is 0.9439 against
0.95. The what-if table for a small safety margin is printed by `train_xgboost.py`; the
threshold is yours to set.

**5. Ways of trading false alarms against catches that were measured and NOT adopted**, in
case you want a different balance than the rule used:
- Letting the model's paths add to the safety net: 271 of 284 caught instead of 269, for
  +18.3 false alarms per 1,000 (`offsets_ab_20260924_181140.json`).
- Tier-1 promotion only from a conflicting path (idea A): 3 fewer false loud alarms on test,
  but one real conflict loses its loud alarm.

## Things only a person can do

**6. Check the runway detector by eye (plan 9.1).** Open `docs/figures/runway_spotcheck.png`
and confirm each red line lies on the runway it is labelled with. Claude looked and all eight
seem right, but the plan asks for a person.

**7. Record the Mumbai audio (plan Phase 5).** This needs three or four people reading
scripts, about 15 minutes each, on a phone in a quiet room. It is needed before any
Indian-accent speech figure can exist. Deferred with the rest of speech, at your request.

**8. The speech chain (plan Phases 4–6, 9.3).** Deferred at your request. Everything it
plugs into is built and tested: `ml_pipeline/utils/clearance.py`, `POST /api/clearances`, and
the `transcriptions` and `extracted_clearances` tables. Still to download: the three Whisper
models and the official ATCO2 annotations (a free 50 KB file).

**9. Stale server on port 8000.** Another project's backend (NeerNiti_Demo, running since
21 September) holds port 8000, which is Flight Right's default port. It was left alone. Stop it
or run Flight Right on another port.
