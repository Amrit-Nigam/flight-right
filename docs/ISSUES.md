# Known Issues — Flight Right

**Status: partly resolved. C3, C4 and C5 are fixed as of 22 September 2026; everything else
is still open.** This is a record of what does not work, gathered by running the system
rather than by reading the code. Each entry carries its own checkbox, and a fixed entry
keeps its original description so the trail stays readable — what was wrong, and what was
done about it.

**C1 and C2 need care when reading them.** Both were *observed* on two alarms that, after
the C3 fix, no longer fire at all. Their trigger is gone; the underlying defects are not,
and both will resurface on a genuine conflict. They stay open. See the note under each.

**How this was gathered.** Backend on `:8000` in `replay` mode with PostgreSQL, frontend on
`:5173`, driven through a complete encounter from the recorded session
`session_c_20260904_204503_combined.parquet`. Two genuine tier 1 alarms fired
(`JZR533 × UAE325` and `UAE325 × ABY821`), and those two alarms are the source of most of
what follows. Every number below was read off the running system, not inferred.

**The headline number is not affected.** 94.0% of conflicts caught with at least three
minutes of warning still stands. Everything here is runtime and integration behaviour, not
a model, threshold or gate. But several of these mean the *running* system does not behave
the way that 94.0% describes, which is the reason the list exists.

**That last sentence was the whole point, and it is now measured.** Fixing C3 closed the
gap it describes: the running system went from catching **87.3%** of conflicts with three
minutes of warning to **94.7%**, while the classifier's own 94.0% stayed exactly where it
was. Both numbers are now produced by every re-score, so the gap cannot reopen unnoticed.

**Last tested:** 9 September 2026. **Last updated:** 22 September 2026.

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

- [x] **FIXED, 25 September 2026 (plan 9.7).** File: `ml_pipeline/utils/resolution_engine.py`
  (`_pair_geometry(report_from_seconds=...)`, `evaluate_manoeuvre`). The separation quoted as
  what a manoeuvre achieves is now measured from the end of the 38 s response delay, never
  from t = 0, so a pre-manoeuvre separation can no longer be presented as the outcome. The
  violation test still covers the whole window. Together with the C2 fix below, a
  manoeuvre is offered only when doing nothing loses separation. Measured on the 41 test
  alarms (`ml_pipeline/reports/reevaluation_20260924_222306.json`, `model3`): instructions
  offered 76 -> 46; for conflicts that never happen 38 -> 11; for real conflicts 38 -> 35.
  The 3 real-conflict instructions removed were for alarms where the engine's own
  simulation showed no loss of separation to prevent, so nothing showed they helped.
  Every other value in the re-score is unchanged (683 of 698 identical; the 15 that
  differ are all Model 3).

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

#### Re-checked 22 September, after C3 was fixed — still open

**The observed instances are gone, and that is not the same as fixed.** Both alarms in the
table above came from pairs that no longer raise an alarm at all, so no manoeuvre is
generated for them and the bad text cannot appear. The trigger is removed.

**The defect underneath is untouched.** The reported separation comes from the worst point
of the simulated window, and with a 38-second response delay against a closest approach only
seconds away, that worst point falls *before the aircraft has moved*. So the number is the
pre-manoeuvre separation, correct as a worst case and misleading as "what this manoeuvre
achieves" — which is how the explanation template words it. Today's re-score still offers
**7 instructions across 11 alarms in the 0–60 s band**, so this remains reachable on a
genuine conflict.

Deferred to plan item 9.7, which exists for exactly this reason: *"Even with the classifier
gap closed, a stale separation quoted as an outcome will resurface on a real conflict."*

### C2. Manoeuvres are offered that finish after the aircraft have already passed

- [x] **FIXED, 25 September 2026 (plan 9.7).** File: `ml_pipeline/utils/resolution_engine.py`.
  `generate_resolutions` now simulates the do-nothing case for each aircraft (flown straight
  on against the other's plausible paths) and records it as `baseline_risk` on every option.
  `is_offerable` requires that doing nothing loses separation (`baseline_risk >
  RESIDUAL_RISK_LIMIT`). When it does not, no manoeuvre is offered, and the reason says so
  in plain words: "no loss of separation for a manoeuvre to prevent ... the alert itself
  stands; monitor the pair". The docstring's reasoning (a manoeuvre that is too slow fails
  `resolves`) now holds, because a violation to fail against is required. Numbers above,
  under C1.

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

#### Re-checked 22 September, after C3 was fixed — still open

Same position as C1. The specific contradiction above came from pairs where there was no
violation to prevent, so `resolves` was trivially true for every candidate; those pairs no
longer produce manoeuvres. But `established_before_cpa` is **still computed and still
ignored** (`resolution_engine.py:540`), and the 0–60 s band still yields offered
instructions. The reasoning in the docstring — that a manoeuvre too slow to help simply
fails `resolves` — holds only when a violation exists to fail against, and nothing yet
enforces that.

### C3. Tier 1 alarms fire on legally separated pairs, and the classifier is never consulted

- [x] **FIXED, 22 September 2026.** Files: `ml_pipeline/utils/cpa_conflict_detection.py`
  (`alert_gate`), `server/app/ml/inference.py`. Signed off by Archit as a change to when a
  controller is alerted. Full reasoning in the Section 15 change-log entry for 22 Sep.

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

#### What was done

Escalation now runs through `alert_gate()`, which tries three routes in strict priority
order: the **geometric safety net** (a predicted breach of the legal 5 NM / 1,000 ft minimum
alerts whatever any model says, so the rule is never overruled), then the **classifier**
where it has given a verdict, then the **old probability route** unchanged for when it has
not — which is what keeps the rule-only path and every existing test behaving as before.

**The obvious implementation would have been a disaster, and measuring first is what caught
it.** The natural move is to compare the classifier's probability against the existing tier
thresholds, 0.85 and 0.60. Those thresholds belong to a completely different quantity — the
multi-path joint probability. The classifier's own calibrated conflict line is **0.0285**,
about thirty times lower. Measured before changing anything: comparing against 0.85 would
have taken test recall from 0.9439 to **0.1881** and the headline metric from 94.0% to
**19.0%**.

#### Verified on the two pairs in the table above

| Pair | Before | After |
|---|---|---|
| JZR533 × UAE325 (4.23 NM / 1,100 ft, classifier 0.35%) | tier 1 alarm, manoeuvres offered | **no alarm, no manoeuvres** |
| UAE325 × ABY821 (4.04 NM / 1,068 ft, classifier 0.41%) | tier 1 alarm, manoeuvres offered | **no alarm, no manoeuvres** |

**Read the mechanism precisely:** the *tier* is still 1, because tier is assigned from
time-to-CPA alone and always has been. What changes is `notify` and `suggest_resolution`,
both of which go from `true` to `false` — so no audible alarm and no suggested manoeuvres.
The pair stays visible, with the reason string now saying why:

> "The conflict classifier puts this pair at 0.4%, below the level at which it calls a
> conflict, and the predicted closest approach stays outside 5 NM / 1000 ft."

#### What it cost, stated rather than buried

Tier 1 strictly improves: the same **27** real conflicts, with false alarms falling
**24 → 14**. But total alerts rise 613 → 762 and overall precision falls 0.436 → 0.378,
all of it in the silent tier 2 watch list (real 240 → 261, false 322 → 460). The system
watches 21 more genuine conflicts at the cost of 138 more watch-list rows that come to
nothing.

### C4. The SHAP explanation argues against the alert it is explaining

- [x] **FIXED, 22 September 2026.** File: `ml_pipeline/utils/cpa_conflict_detection.py`
  (`escalate_pair`). Surfaced by `server/app/ml/inference.py`, rendered in the alert detail.

Top feature contributions on the JZR533 × UAE325 alarm: **−1.74, −0.73, −0.44**. Every one
negative, meaning every top feature was pushing *away* from "conflict". Those are displayed
to the controller as the reason the alert fired.

This is consistent with C3 — the classifier scored 0.0035, so of course its explanation
argues against a conflict. It stops being nonsense once the alarm actually comes from the
classifier. Listed separately because if C3 is fixed some other way, this still needs a
guard: an explanation whose contributions all point the other way should not be presented as
justification.

#### What was done

Mostly it is fixed **by construction**. Now that the classifier gates alarms, an alert
raised on the classifier's own verdict necessarily has SHAP contributions pointing *toward*
conflict — the disagreement that produced this issue cannot arise on that route.

One route remains where it genuinely can: the geometric safety net, which alerts on a
predicted breach of 5 NM / 1,000 ft **whatever the classifier says**. That is deliberate and
must not change — the deterministic rule is never overruled by a model. So instead of hiding
the disagreement, the alert now states it:

> "alarm: closest approach 3.00 NM / 400 ft in 120 s, confirmed on 3 consecutive updates.
> **Raised by the separation rule, not by the classifier, which puts this pair at 0.4% and
> would not have alerted; the deterministic rule is never overruled by a model.**"

The controller is told which of the two is speaking, and that they disagree. The SHAP
contributions are still shown, but they are no longer presented as the justification for an
alert the classifier did not raise.

### C5. The check that stops a manoeuvre causing a second conflict never ran in production

- [x] **FIXED, 22 September 2026.** Files: `server/app/services/conflict_service.py`,
  `server/app/ml/inference.py`. Found during Phase 1, not in the 9 September sweep.

On 7 September the resolution engine gained a check against the *domino effect*: before
offering a manoeuvre, test it against every other aircraft nearby, and reject it if it would
fly the aircraft into a third one. It was verified at the time and it worked.

**It only ever worked inside the test suite.** `assess_pair` takes the neighbour list as
`traffic`, defaulting to empty, and the backend **never passed it**. So for two weeks, every
suggestion the running system offered had been checked against the conflicting aircraft and
nothing else. Nothing failed, no test caught it, and the system's own description of its
reasoning was the only visible symptom.

**What was done.** The backend now assembles the eligible traffic near either aircraft and
passes it in. The evidence is that description string, on a real replayed alarm:

| | what the system said it checked |
|---|---|
| before | "the other aircraft's 5 predicted paths" |
| after | "the other aircraft's 5 predicted paths **and 1 other aircraft nearby**" |

**Cost, measured on a replayed session of 44 aircraft and 36 assessed pairs:** the median
update goes from **0.34 s to 0.35 s**, against a ten-second budget. Two things keep it that
cheap, and both matter. Neighbours are assembled **only when a manoeuvre is actually going
to be proposed** — for a silent watch-list pair the engine ignores them anyway. And each
aircraft's predicted paths are **reused from the single batched call** already made for the
whole airspace; asking the multi-path model once per neighbour per pair is the same mistake
that made a 30-pair update take 46 seconds before 8 September, multiplied by the neighbour
count.

---

## High — audit and safety-net gaps

### H1. Most "audit" entries never leave the browser

- [x] **FIXED, 25 September 2026 (plan 9.8).** Files: `client/src/lib/siteLogger.js`,
  `client/src/pages/LogsPage.jsx`. `logAudit()` still records to the tab for the live view,
  and now also sends every entry to `POST /api/audit` through `postAuditLog`. That covers all
  44 call sites at once, and `postAuditLog` finally has a caller. A failed send is not
  hidden: the tab log gets a warning that audit entries are not reaching the server (at
  most once a minute). The `/logs` page now opens on the **server** audit log (append-only,
  enforced by PostgreSQL). The tab log is a second view, and the server view cannot be
  cleared. The frontend build passes. H2 (`modelVersion` null on UI rows) is still open.

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

- [x] **FIXED, 25 September 2026.** File: `server/app/api/routes.py` (`_served_model_versions`). The
  server now stamps the versions of the models actually running on every accept, dismiss and
  UI audit entry. The client is not asked, because it does not know them: the resolve modal
  sent source names, not versions. Anything the client sent is kept in the detail. This
  matters more now that every UI audit event reaches the server (H1).

Section 12 requires the model version attached to every entry. The resolve-modal accept path
sends `modelVersion: conflict.sources`; the suggestions-panel accept path sends nothing. Rows
written during testing all came back with `"modelVersion": null`.

### H3. Dismissing a suggestion hides that pair permanently

- [x] **FIXED, 25 September 2026.** Files: `client/src/lib/adapters.js` (`episodeKey`),
  `client/src/pages/HomePage.jsx`. A dismissal is now remembered against the episode: pair,
  first-seen time from the alert feed, tier, and best manoeuvre. Escalation, a new encounter
  or a changed option shows the suggestion again. The dismissal is still recorded server-side.

`handledIds` filters suggestions by `alert.id`, and `alert.id` is just the sorted callsign
pair (`"-".join(callsigns)` in `server/app/services/conflict_service.py`). So dismissing a
tier 2 suggestion keeps it hidden **after it escalates to tier 1**, and after the pair
separates and re-converges later.

This is a display action silently becoming a detection action — the exact failure the alert
feed module was built to prevent, reintroduced one layer above it.

### H5. The low-confidence group holds real conflicts with minutes of warning left

- [ ] **Open — a decision for Archit, measured 24 September 2026.** File:
  `ml_pipeline/utils/alert_feed.py` (`LOW_CONFIDENCE_RAW_PROBABILITY = 0.25`)

The alert feed collapses a tier 2 row into a counted group when the classifier's raw score
is under 0.25. On the served configuration that group holds **7 real conflicts on the test
split and 10 on validation**, all with at least three minutes of real warning. They are never
removed: they stay on the active list, and they are released into a full alarm once inside
three minutes. So detection and the 94.7% are unaffected. But until then the controller
sees them only as part of a count.

The multi-path model disagrees with the classifier on most of them. Requiring both models to
call a row unlikely before collapsing it (option B1: multi-path P(conflict) < 0.10) cuts the
real conflicts in the group from 7 to 3 on test. The cost is 50 more false rows on the
prominent list (297 → 347). It was not switched on, because the instruction was to cut false
alarms shown without costing a real conflict, and B1 trades the other way. Numbers:
`ml_pipeline/reports/alert_prominence_20260924_193159.json`; reasoning in `CLAUDE.md`
Section 14, 24 Sep.

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

1. ~~**C3 first**, because it is upstream of C1 and C2. Once escalation consults the
   classifier, legally separated pairs at 1,100 ft stop reaching Model 3 at all, and the bad
   descend suggestions disappear with them.~~ **Done 22 Sep, and it worked as predicted** —
   both observed pairs stopped alarming and stopped producing manoeuvres. C4 and C5 went
   with it.
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
of a project at this stage.

**C3 was the one that deserved a straight answer rather than a framing, and it now has one.**
The classifier was display-only, so the running dashboard was not the system the 94.0%
describes. It is now, and the size of that gap was measured rather than estimated: the
running system caught **87.3%** of conflicts with three minutes of warning where the
classifier alone scores 94.0%, and after the fix it catches **94.7%**.

**The better framing for a review is that this list exists at all.** Five critical defects
were found by driving the system, three are fixed with the fix measured, and the two that
remain are documented with their trigger removed and their root cause stated. A project that
finds its own defects and says so reads considerably better than one that did not look.
