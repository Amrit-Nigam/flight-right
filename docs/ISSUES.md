# Known Issues — Flight Right

**Status: open list, nothing fixed yet.** This is a record of what does not work, gathered
by running the system rather than by reading the code. Nothing here has been resolved. The
plan is to finish the major implementation and connection work first, then come back and
work through this list.

**How this was gathered.** Backend on `:8000` in `replay` mode with PostgreSQL, frontend on
`:5173`, driven through a complete encounter from the recorded session
`session_c_20260904_204503_combined.parquet`. Two genuine tier 1 alarms fired
(`JZR533 × UAE325` and `UAE325 × ABY821`), and those two alarms are the source of most of
what follows. Every number below was read off the running system, not inferred.

**The headline number is not affected.** 94.0% of conflicts caught with at least three
minutes of warning still stands. Everything here is runtime and integration behaviour, not
a model, threshold or gate. But several of these mean the *running* system does not behave
the way that 94.0% describes, which is the reason the list exists.

**Last tested:** 9 September 2026.

---

## Contents

- [Critical — the system gives dangerous advice](#critical--the-system-gives-dangerous-advice)
- [High — audit and safety-net gaps](#high--audit-and-safety-net-gaps)
- [Hardcoded values that should not be](#hardcoded-values-that-should-not-be)
- [Minor](#minor)
- [What genuinely works](#what-genuinely-works)
- [Suggested order of attack](#suggested-order-of-attack)

---

## Critical — the system gives dangerous advice

### C1. The top-ranked manoeuvre descends an aircraft into the one it is separating from

- [ ] **Not fixed.** File: `ml_pipeline/utils/resolution_engine.py`

Both live alarms, checked against the actual altitudes reported by the feed at that moment:

| Alarm | Current altitudes | Suggestion offered | Real gap after it | What the UI said |
|---|---|---|---|---|
| JZR533 × UAE325 | 39,525 / 38,425 ft | "Descend JZR533 to FL385" | **75 ft** | "holds vertical separation at 1,100 ft" |
| UAE325 × ABY821 | 38,425 / 37,350 ft | "Descend UAE325 to FL374" | **50 ft** | "holds vertical separation at 1,068 ft" |

Both were ranked **first**, with scores 0.81 and 0.80, `resolves: true` and
`residual_risk: 0.0`. Both aircraft were level at 0 fpm, so this is not a transient reading.

**Why it happens.** The `resulting_vertical_separation_ft` field is the *current* separation
echoed back, not a recomputed post-manoeuvre value. With time-to-CPA at 0–30 s and a 38 s
response delay, the aircraft never moves inside the simulation window, so nothing is
recalculated — and the explanation template then presents that stale number as the outcome
of the manoeuvre.

**What a fix has to do.** Recompute `resulting_vertical_separation_ft` from the post-
manoeuvre state, and never let the explanation string quote a separation the simulation did
not actually produce.

### C2. Manoeuvres are offered that finish after the aircraft have already passed

- [ ] **Not fixed.** File: `ml_pipeline/utils/resolution_engine.py`, `is_offerable` (~line 188)

Observed text, verbatim:

> "Fully established about 78 s from now, against a closest approach in 0 s."

with `established_before_cpa: false` on the same option.

The flag is computed and then deliberately ignored. The docstring on `is_offerable` explains
the reasoning:

> "There is no separate 'in time' test. The simulation already contains the 38 s response
> delay and the real turn and climb rates, so a manoeuvre that is too slow simply fails to
> prevent the violation and `resolves` is False."

That reasoning only holds when there **is** a violation to prevent. In these two alarms
there is none (see C3), so `resolves` is trivially true for every candidate, all 26 pass,
and three get offered.

This directly contradicts the finding recorded in the decision log for 6 September, that at
90 seconds to CPA **all 26 candidates are rejected** because nothing arrives in time. At
0 seconds, three were offered.

### C3. Tier 1 alarms fire on legally separated pairs, and the classifier is never consulted

- [ ] **Not fixed.** File: `server/app/ml/inference.py` line ~410

| Pair | Predicted CPA | `ruleIsConflict` | Classifier probability | Escalation probability | Result |
|---|---|---|---|---|---|
| JZR533 × UAE325 | 4.23 NM / **1,100 ft** | `false` | **0.0035** | 1.0 | tier 1, severity high |
| UAE325 × ABY821 | 4.04 NM / **1,068 ft** | `false` | **0.0041** | 1.0 | tier 1, severity high |

Both pairs are above the 1,000 ft vertical minimum. They are legally separated, ordinary
traffic. The deterministic geometric rule says no conflict. The XGBoost classifier says
0.35% and 0.41%. The system raised an audible tier 1 alarm with manoeuvre suggestions
anyway.

**Why it happens.** `assess_pair` calls:

```python
escalation = escalate_pair(cpa_for_tiering, [...])
```

The classifier result is computed and attached to the outgoing payload a few lines earlier,
but it is **never passed into `escalate_pair`**. Escalation therefore runs entirely on the
alert-volume probability from `conflict_probability()`, which returns 1.0 for anything
inside 8 NM / 1,500 ft. Both pairs sit inside that volume, so both score exactly 1.0.

**Two consequences worth stating separately.**

1. `TIER_1_PROBABILITY_THRESHOLD = 0.85` and `TIER_2_PROBABILITY_THRESHOLD = 0.60` are being
   compared against a number that is effectively binary in the running system. The
   thresholds are not doing the work they were chosen to do.
2. **The model the entire 94.0% headline is measured on gates nothing at runtime.** It is
   computed, displayed, and ignored by the decision that matters.

**This one needs Archit's sign-off before it is changed** — per the operating rules, any
change to when a controller gets alerted is his call, not a session's.

### C4. The SHAP explanation argues against the alert it is explaining

- [ ] **Not fixed.** Surfaced by `server/app/ml/inference.py`, rendered in the alert detail.

Top feature contributions on the JZR533 × UAE325 alarm: **−1.74, −0.73, −0.44**. Every one
negative, meaning every top feature was pushing *away* from "conflict". Those are displayed
to the controller as the reason the alert fired.

This is consistent with C3 — the classifier scored 0.0035, so of course its explanation
argues against a conflict. It stops being nonsense once the alarm actually comes from the
classifier. Listed separately because if C3 is fixed some other way, this still needs a
guard: an explanation whose contributions all point the other way should not be presented as
justification.

---

## High — audit and safety-net gaps

### H1. Most "audit" entries never leave the browser

- [ ] **Not fixed.** Files: `client/src/lib/siteLogger.js`, `client/src/pages/LogsPage.jsx`

`logAudit()` writes to `sessionStorage`, which is erased when the tab closes. There are
**44 `logAudit()` call sites across 15 files**. Only accept and dismiss reach the server, via
`acceptSuggestion` / `dismissSuggestion`.

Measured: after a full session of clicking around, the server-side audit log held
**10 entries**.

- `/logs` — the page the "Logs" link in the top bar points at — reads `sessionStorage` only.
  That is the page the project's own Section 12 calls "demo-grade only, not the real thing",
  and it is still the only log page in the app.
- The real server-side log is only visible in the `AIAuditTrail` dropdown on the map toolbar.
- `postAuditLog` is exported from `client/src/lib/api.js` and **never called anywhere**.

The naming is the trap: a function called `logAudit` that writes to a browser tab.

### H2. `modelVersion` is null on every audit row

- [ ] **Not fixed.** Files: `client/src/pages/HomePage.jsx`, `server/app/services/database.py`

Section 12 requires the model version attached to every entry. The resolve-modal accept path
sends `modelVersion: conflict.sources`; the suggestions-panel accept path sends nothing. Rows
written during testing all came back with `"modelVersion": null`.

### H3. Dismissing a suggestion hides that pair permanently

- [ ] **Not fixed.** File: `client/src/pages/HomePage.jsx`, `handledIds`

`handledIds` filters suggestions by `alert.id`, and `alert.id` is just the sorted callsign
pair (`"-".join(callsigns)` in `server/app/services/conflict_service.py`). So dismissing a
tier 2 suggestion keeps it hidden **after it escalates to tier 1**, and after the pair
separates and re-converges later.

This is a display action silently becoming a detection action — the exact failure the alert
feed module was built to prevent, reintroduced one layer above it.

### H4. `estimatedFields` is shipped by the backend and ignored by the frontend

- [ ] **Not fixed.** Files: `server/app/services/normalizer.py`, `client/src/components/FlightDetailDrawer.jsx`

The normalizer deliberately tags which fields have no ADS-B source:

```python
"estimatedFields": ["route", "eta", "aircraft", "fuel", "waypoint"],
```

with a comment saying it exists "so the UI can label them rather than imply they are
measured". Nothing in the frontend reads it. `FlightDetailDrawer` renders ROUTE, ETA,
SQUAWK, FUEL and WAYPOINT as though they were measured fact. Every aircraft shows
`ROUTE: BOM TMA`, `ETA: --`, `SQUAWK: ----`, `FUEL: --`, and an *inferred* waypoint.

---

## Hardcoded values that should not be

| Value | Where | Why it is a problem |
|---|---|---|
| `"ATIS M"`, `"RWY 27R / 27L"` | `TopBar.jsx`, under the heading **"Airport Status"** | Invented, and not labelled demo. Also contradicts `mockData.js`, which says `ATIS KILO` — two different fake ATIS letters in one app |
| `"A. SHARMA"` | `TopBar.jsx`, "Controller" | The backend records `demo-controller`. The UI shows a different, invented name |
| METAR `VABB 211200Z 27018KT 7200 FEW030 28/22 Q1012` | `FlightListPanel.jsx`, "Weather & ATIS" strip | **Not labelled demo.** The decision log claims weather is labelled on screen; the map toolbar button is, this panel is not |
| `"Saved 14 minutes total delay"` | `RunwayStatusPanel.jsx`, AI AUTO-BALANCE toast | An invented measured benefit, attributed to a model that does not exist. Header says DEMO DATA, the toast still claims a specific saving |
| `"SEVERE WX"` polygon + `deviationRoutes: { BA118: ... }` | `RadarCanvas.jsx`, `mockData.js` | Fixed weather cell drawn at screen percentages; the deviation route is keyed to a callsign that will never appear in live traffic |
| `"No new system notifications."` | `TopBar.jsx`, bell button | Fires unconditionally, including while the badge shows N alarms |
| `${38}` seconds, weights `0.60 / 0.15 / 0.10 / 0.10 / 0.05` | `lib/adapters.js`, `xaiReason` string | Duplicates backend constants. If `RESPONSE_DELAY_SECONDS` or the weights change, the UI keeps quoting the old ones |
| `SEPARATION_LATERAL_NM = 5`, `SEPARATION_VERTICAL_FT = 1000` | `lib/adapters.js` | Duplicated from the backend rather than served with the alert |
| `dur: 2` | `lib/adapters.js`, `timelineFromAlerts` | Every timeline bar is arbitrarily two minutes wide regardless of the encounter |
| Wall-clock UTC | `TopBar.jsx` | Shows *today's* real time while replaying a recording from 4 September. Clock and traffic disagree, with nothing on screen reconciling them |

---

## Minor

- [ ] `RUNNING.md` says to allow about 30 seconds for an alarm after startup. Measured from a
      cold start: **3 minutes 33 seconds** (boot 14:34:55, first alarm 14:38:28).
- [ ] Mixed casing inside a single payload: `resolution.blockedUnsafe`, `candidatesEvaluated`,
      `checkedAgainst`, `rejectedNewConflict` are camelCase, while `options[].manoeuvre_type`,
      `resulting_lateral_separation_nm`, `score_components`, `new_conflict_risk` are
      snake_case. `adapters.js` handles it today, so this is latent rather than broken.
- [ ] Dead props: `theme` passed to `DataSourceBar` and never used; `feed` accepted by
      `NLPCommsPanel` and never passed; `weatherDevAccepted={false}` hardcoded at the call site.
- [ ] `"Backend started"` audit rows are written with `userId: demo-controller` — a system
      event attributed to a person.
- [ ] Stale servers from a previous session were still holding ports 8000 and 5173 about
      18 hours later. This is the documented trap from the 8 September entry, and it still
      bites. Worth a startup check that refuses to run against an already-bound port.

---

## What genuinely works

Recorded so the list is not read as a verdict on the whole system. All verified in the same
session:

- WebSocket `/ws/stream` connects and pushes aircraft and conflicts together in one typed
  envelope, exactly as designed.
- PostgreSQL is selected and the audit log is append-only **by permission** — `UPDATE` and
  `DELETE` are refused by the database, not merely avoided by the code.
- The audit round-trip works: POST to `/api/actions/accept` returns the persisted row with
  `userId`, `decision`, `confidence` and the detail blob intact.
- Replay seek lands three minutes before a genuine encounter in real recorded data.
- The three-consecutive-updates rule holds. Alarms did not fire on update 1, and the reason
  strings correctly reported "confirmed on 4 consecutive updates".
- `DataSourceBar` reports provenance honestly — mode, session, frame, pairs assessed,
  duration, and the permanent "PROTOTYPE · DECISION SUPPORT · CONTROLLER DECIDES" strip.
- `ResolveModal` says "Nothing is transmitted; accepting records your decision" and the
  button reads ACCEPT — RECORD DECISION.
- The batched multi-path call holds: roughly 0.75–0.86 s for 15–24 pairs.
- The invented "ATCO match: 94% (847 cases)" is genuinely gone.
- `NLPCommsPanel` is labelled honestly, three times over.

---

## Suggested order of attack

Not a schedule, just the dependency order.

1. **C3 first**, because it is upstream of C1 and C2. Once escalation consults the
   classifier, legally separated pairs at 1,100 ft stop reaching Model 3 at all, and the bad
   descend suggestions disappear with them. **Needs Archit's sign-off** — it changes when a
   controller is alerted.
2. **C1 regardless of C3.** `resulting_vertical_separation_ft` must be recomputed after the
   manoeuvre. Even with C3 fixed, a stale separation quoted as an outcome is a defect that
   will resurface on a real conflict.
3. **C2**, once C1 and C3 are in: decide explicitly whether `established_before_cpa` should
   gate offering, now that the "resolves covers it" argument is known not to hold in every
   case.
4. **H1 and H2 together** — they are the same wiring job, and Section 12 compliance is a
   submission requirement rather than a nicety.
5. **H3**, small and self-contained.
6. **H4 and the hardcoded-values table** — largely labelling work, and the cheapest way to
   remove the "presented as real" criticism from a review.

---

## A note on how to talk about this list

Most of these are integration defects in a system whose models are measured and sound. When
this comes up in review, the useful framing is that the models were evaluated properly and
the *wiring between them* is where the defects are — which is both true and the normal shape
of a project at this stage. C3 is the one that deserves a straight answer rather than a
framing: the classifier is currently display-only, and until it gates escalation, the
running dashboard is not the system the 94.0% describes.
