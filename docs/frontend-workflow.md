# Controller workflow improvements — 16 November 2026

Requested scope: a flight-tracker map with correctly placed aircraft, map-only gestures,
fast selection, flight picking instead of repeated callsign entry, editable sequencing,
communication-derived sequence updates and visible per-flight instruction history.
Existing model weights, prediction inputs and alert thresholds are outside this change.

## Stepwise checklist

1. [x] **Map and aircraft.** Default to a labelled street/geographic map with visible
   attribution and an explicitly labelled offline fallback. Draw each aircraft at its
   reported longitude/latitude with its track orientation. Keep observations distinct
   from forecasts; display report time and freshness rather than inventing positions.
   Give hovered, selected and ordinary aircraft distinct styling and keyboard access.
2. [x] **Gestures.** Handle pinch/Ctrl-wheel as zoom around the pointer and ordinary
   two-finger trackpad scrolling as map panning. Retain mouse drag, touchscreen pinch
   and explicit controls. Install listeners only on the map; other panels/browser
   retain their normal wheel behavior. Device classification is a browser heuristic;
   retain a wheel-mode preference for mice/drivers that report indistinguishable events.
3. [x] **Selection performance.** Render feed details immediately without waiting for
   history/forecast requests or entry animations. Reuse/deduplicate cached track reads,
   protect against late responses and source/replay changes, and scroll selected
   details into view. Measure browser selection responsiveness with delayed APIs.
4. [x] **Instruction context.** Put last recorded altitude/direction instructions,
   their source/time/status and older instructions beside flight details and on hover.
   Distinguish observed altitude/track from instructions and from time-limited model
   intent. Unknown, rejected and earlier-session records must not become current clearance.
5. [x] **Sequencing.** Pick observed flights with one click; keep an optional manual
   future movement entry. Provide named remove controls, undo, visible order numbers,
   drag insertion feedback, arrow alternatives and UTC impact previews. Retain server
   revision, readiness, pin and emergency validation.
6. [x] **Communications integration.** Consume the existing transcript/role/callsign
   outputs without changing ASR or its acceptance rules. Understand a bounded set of
   tower movement/sequence phrases, journal why a message did/did not change the plan,
   avoid duplicate application, and preserve source/session identity. Pilot requests,
   readbacks, ambiguous matches, negations and unresolved speaker hints cannot silently
   reorder traffic. Show reviewable proposals and allow correcting transcript text.
   Planning updates do not authorize or transmit a new instruction.
7. [x] **Data and regression checks.** Unit/API tests for parsing, idempotency,
   rejected/conditional speech, scope changes, instruction filtering, caching, pins and
   existing workflows. No copied scores or synthetic UI fixtures reported as new ML results.
8. [x] **Rendered acceptance.** Start replay servers; use isolated Chromium with only
   the local app and required map assets. Check desktop/mobile, real marker coordinates,
   hover/selection, delayed details, wheel/pinch/pan inside versus outside the map,
   pick/add/remove/undo/drag, transcript processing and instruction history. Keep
   screenshots/results and record remaining physical-device or data-source limits.
9. [x] **ML integration.** Keep model identity/readiness, assessment time, coverage,
   selected-flight forecast, alarms, watch list and ranked resolution suggestions
   connected to backend results. Link suggestion aircraft to selection; preserve
   accept/dismiss audit actions, explanation, confidence, score and failure feedback.

## Implementation references

- [MapLibre scroll handler](https://maplibre.org/maplibre-gl-js/docs/API/classes/ScrollZoomHandler/)
- [Browser wheel events](https://developer.mozilla.org/en-US/docs/Web/API/Element/wheel_event)
- [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/): visible
  attribution, browser caching/referrer, no tile scraping/prefetch or offline downloading;
  best-effort public service. Provider URL is configurable for a deployment's own service.

## Verification and remaining limits

### Implemented workflow

- **Map:** labelled raster streets with visible attribution, yellow ordinary aircraft,
  blue hover and red selected state; keyboard focus also opens the tooltip. Positions
  stay at reported coordinates rather than extrapolating an invented flight path.
  Report time appears in the tooltip and details; solid history and dashed model
  forecast are distinct. Secondary filters/map key collapse to preserve map space.
- **Gestures:** pinch-shaped wheel events / Ctrl-wheel zoom around the pointer;
  ordinary two-finger wheel deltas pan. A Pan/Zoom wheel selector handles mice and
  driver differences. Browser behavior outside the canvas is untouched. Map buttons,
  mouse dragging and MapLibre touchscreen zoom remain available.
- **Selection:** feed details render immediately, with no drawer entry animation.
  History and forecast load independently, with bounded caches, in-flight request
  deduplication, late-response guards and source/session/cycle cache identities.
  Active intent revisions invalidate the forecast key. Selected details scroll to
  their top. Replaced three dashboard effect-state updates with guarded state
  synchronization / derived selection; fixed duplicate sibling keys. The resolution
  countdown uses the same guarded reset pattern rather than an effect-state reset.
- **Instructions:** last accepted altitude and heading/direct instruction show source
  and time above aircraft details. The timeline includes accepted and rejected records;
  earlier/unlinked records have their own disclosure. Server-run and replay scope
  metadata is journal correlation only, never a new model feature. Per-flight reads
  retrieve the latest 100 records and merge with shared recent records. Database
  history is retained; this is a bounded recent-history view, not a complete archive.
- **Sequence:** Add observed flight opens an ARR/DEP picker; airborne departure
  attempts are disabled and rejected by the server. Manual unreported movements remain
  optional. Numbered rows have named Remove, undo, drag insertion feedback, arrow
  controls, pinning and server-checked UTC slot previews.
- **Communications:** the existing speech conversation feeds an idempotent adapter
  through `/api/planning/radio/sync`. Reviewed or labelled ATCO messages with an exact
  accepted callsign match and sufficient existing ASR confidence can update the demo
  plan. Phrase hints, pilot/unknown speech, older/future timestamps, auto-off, takeover
  and emergency cases await review. Live radio cannot automatically update replay
  movements. Conditional, negated, ambiguous or unsupported instructions are journalled
  without a movement change. Unsupported messages require corrected text or manual
  sequencing. Supported phrases: cleared to land; taxi, line up, hold short, cleared
  for takeoff; number 1–100 (spoken one–ten); follow/behind a queued callsign.
  Sequence positions cannot imply missing, unobserved queue members. ETA readiness,
  movement type, pins, plan revision and resource limits remain authoritative.
- **ML workspace:** the compact map-side overview reads actual loaded core model
  versions, speech configuration/load state, assessment counts/time and eligibility.
  Expand for model roles and selected forecast. Review jumps to the suggestion queue;
  aircraft chips select the relevant flight. Existing conflict banner, watch list,
  explanations, ranked resolution options, confidence, score, delay/fuel proxies and
  decision audit actions remain connected. Forecast percentages are labelled candidate
  weights. The resolution dialog opens immediately, scrolls within the viewport and
  uses a compact phone header with stacked actions. No weights, features, calibration,
  alert thresholds or deployment selection changed.

### Checks and evidence

| Check | Result |
| --- | --- |
| Relevant backend suites | 66 passed: planning, communication adapter, speech semantics, radio HTTP, workspace and API contracts. The intentional recognition-failure test logs its injected exception. |
| JavaScript checks | 14 passed: cache/deduplication, instruction scope filtering, sequence previews and radio segmentation. |
| Changed JS/JSX lint | Zero errors; one existing ControllerWorkspace Fast Refresh export warning. Includes HomePage's three previous effect-state errors/dependency warnings and ResolveModal's previous countdown effect-state error, now corrected. |
| Production build | Passed; existing large bundle warning remains. |
| Isolated Chromium suite | 11 scenarios passed, no uncaught page exceptions or unexpected console errors. Additional focused desktop/phone resolution-dialog check passed after its final layout change. |
| Data placement | Real backend snapshot frozen for repeatable comparison; reported longitude/latitude and track match markers. Mercator screen projection agrees within 2 px. No invented aircraft used in this check. |
| Selection responsiveness | Final warm local Chromium check: 104 ms to visible details while both history and forecast APIs were delayed by 2,200 ms. Earlier checks were 364 ms and 265 ms. These are UI checks, not ML inference latency or an accuracy benchmark. |
| Browser layouts | Inspected actual desktop 1440×900, laptop 1366×768, tablet 1024×768 and phone 390×844 screenshots, including a scrolled phone map. |
| Planning cleanup | Temporary QAUI161/QAUI162 and the picker-added observed movement removed. Draft undo cleared when it contained only test movements. Simulated planning journal entries retained. |

Browser harness, results and screenshots: `checkpoints/ui_review_20261116/` (local
ignored run artifacts). Durable integration evidence and code/artifact fingerprints:
`docs/evaluations/evidence/controller_workflow_20261116.json`; registered in the
existing full-alert-chain and ASR ledgers. This integration check provides no new ASR,
extractor, trajectory, conflict-classifier or full-chain accuracy score.

Initial rendered inspection found stalled street tiles inside the network sandbox,
the correct offline fallback, misleading requested-basemap wording, overlapping
fallback/gesture controls and duplicate React keys. Fixed the labels/layout/keys;
street tiles returned HTTP 200 in the authorized isolated browser outside the network
sandbox. One pinned-slot test initially assumed an insertion was infeasible even
though its 120-second gap fit; corrected its clock fixture to test a real blocker.
One metadata assertion initially assumed a nested response report; corrected it to
the service's existing flattened response. All final affected tests pass. The small
screen inspection led to a taller map and collapsed filters. Focused model inspection
led to immediate, opaque dialog entry and a compact, scrolling phone layout.

### Remaining limits

- Physical trackpad/driver gestures and a real touchscreen were not exercised. Wheel
  pan/zoom behavior was exercised in Chromium; the device-dependent limitation remains.
- No microphone/receiver or fresh real-audio ASR accuracy evaluation was run. Speech
  integration uses scripted transcript tests and existing accepted matcher outputs;
  the reviewed-text UI is explicitly labelled as text entry. Flight following, landing,
  departure and emergency handling remain an educational planning demonstration.
- Public street tiles require connectivity and are best effort. Use `client/.env.local`
  with `VITE_MAP_TILE_URL` and `VITE_MAP_ATTRIBUTION` for an appropriately provisioned
  provider; see `client/.env.example`. The bundled Natural Earth map is a coarse offline
  geographic reference, not an airport surface chart. No bulk tile download was made.
- Replay reports are historical surveillance, not live FlightRadar24 coverage. Gaps,
  missing routes/instructions and ground-report coverage are shown as unavailable.
  The current bundled replay has airborne reports, not validated surface movements.
- The sequence still has the documented educational 120-second resource gap; no
  operational wake/surface/runway scheduling model or pilot transmission is claimed.
  A classifier alert is not required for a manual planning movement. Automated plan
  updates never issue clearances or authorize outbound advisories.
- The ML overview reports runtime state and outputs, not a new model evaluation.
  Current comparison, recorded accuracy headlines and served artifacts are unchanged.
- Chromium tested the development servers. The production build passes; a full static
  production-host/backend deployment was not exercised in this iteration.

Servers are left running locally at `http://127.0.0.1:5173` and
`http://127.0.0.1:8000`. No commit, push or hosted publication was performed.


## Responsive workspace correction — 16 November 2026

The user found the previous dashboard crowded. This correction supersedes the earlier
three-column/map-side-model layout described above; its earlier test evidence remains
historical. The workspace now presents the traffic picture with one chosen task panel.

1. Replaced the large airport header and repeated status/position/planning rows with
   a compact header and tool navigation. UTC/replay identity and feed problems remain
   visible. Controller identity, notifications, suggestion visibility and logs are in
   Session. Take control remains directly accessible.
2. Desktop widths of 1100 CSS pixels or more show the map and one flexible tool panel.
   Map closes the panel for a full-width traffic picture. Traffic, Sequence, Flight,
   ML, Radio and Airport each have their own view instead of a vertical stack of all
   cards. The compact position selector retains Tower/Ground/Clearance views.
3. Below 1100 pixels, the default is the full-width map. A selected tool uses the
   content area, with Back to map available. Navigation remains visible. No panel is
   squeezed into a narrow sidebar, and browser/window resizing preserves selected
   flights and in-progress drafts. Very short landscape windows use ordinary vertical
   page scrolling to keep the map usable.
4. Selecting an aircraft opens its Flight view. Instruction context, planning actions,
   aircraft details and handoffs are grouped there. Queue picking/editing remains in
   Sequence. Hidden tool pages stay mounted so a radio draft or capture is not torn
   down simply by navigating to another tool.
5. Moved model identities/readiness, forecast information, ranked suggestions, watch
   list, metrics and decision audit to ML. Urgent conflicts have a compact persistent
   alert outside the panels, including direct resolution review. Offline/stale feed
   status remains visible when Airport/status tools are closed. No inference,
   acceptance, alert selection or backend behavior changed in this correction.
6. Collapsed map layers/filter controls and made ordinary callsign labels optional
   (hover and selected labels remain available). The duplicate conflict detail card
   is opt-in; conflict geometry and the persistent alert remain. Wheel mode and basic
   navigation remain directly accessible. Added container resize observation so map
   pixels follow the actual available area after panel and viewport changes.
7. Radio opens with communication sequencing; live receiver/transcript controls are
   under a disclosure. Airport contains runway/feed context. Timeline remains one
   click away and opens over the map rather than consuming its layout height.

### Current rendered checks

Ten isolated Chromium scenarios passed, plus focused narrow-phone/header/alert
checks after final spacing adjustments. No uncaught browser exceptions were seen.
The screen-size sweep covers the following CSS-pixel viewports; map dimensions are
from actual rendered elements (minor rounding only).

| Viewport | Default map | Arrangement |
| --- | --- | --- |
| 1920 × 1080 | 1464 × 879 | Map + one panel |
| 1440 × 900 | 991 × 699 | Map + one panel |
| 1366 × 768 | 938 × 567 | Map + one panel |
| 1280 × 720 | 876 × 519 | Map + one panel |
| 1100 × 700 | 714 × 499 | Map + one panel |
| 1093 × 700 | 1071 × 503 | Map; selected tool gets full content area |
| 1024 × 768 | 1002 × 571 | Map; selected tool gets full content area |
| 768 × 1024 | 746 × 827 | Map; selected tool gets full content area |
| 640 × 800 | 618 × 550 | Map; selected tool gets full content area |
| 390 × 844 | 368 × 594 | Map; selected tool gets full content area |
| 320 × 740 | 298 × 460 | Map; selected tool gets full content area |
| 844 × 390 | 822 × 361 | Map; selected tool gets full content area |

Checked panel switching and canvas resizing, selected-flight details and selection
retention, sequence picker/manual entry access, controller position/ground-coverage
view, radio draft retention, model readiness, map options/gestures, weather, dark
theme, phone session menu, timeline and persistent alerts/offline status. Conflict
and decision-failure cases use explicitly labelled intercepted UI fixtures, not new
model detections or accuracy results. No planning movement, clearance or microphone
capture was created during these layout checks; ordinary local UI audit entries remain.

The production build passes, with the existing large bundle warning. The changed
JS/JSX and responsive hook were checked with zero lint errors and one existing
ControllerWorkspace Fast Refresh export warning. Browser screenshots/results/harness:
`checkpoints/ui_declutter_20261116/`. A fresh font-ready 320px screenshot also confirms
that airport/UTC/source/session labels fit the compact header. Chromium used a fresh
isolated profile and accessed only the project app and its required assets.

The existing replay servers were reused after the launcher reported port 8000 already
occupied; both frontend/API answered HTTP 200. They remain available at local
5173/8000. This is a frontend layout change: no new model evaluation/training was run,
and evaluation ledgers/comparison, weights, thresholds and deployment are unchanged
from the preceding integration task. Physical device gestures, live audio and full
production hosting remain outside this iteration's verified scope. No commit/push.


## Independent traffic and details panels — 16 November 2026

The user found that selecting a flight replaced the strip list and that restoring a
closed right panel was unclear. This correction supersedes the shared list/inspector
panel behavior in the preceding responsive-layout entry.

- Traffic strips now have their own independently collapsible panel. Selecting an
  aircraft opens a separate inspector and preserves the strip list, its search query
  and scroll position. Selection from a strip keeps that panel open across resizing.
- Desktop: strips, map and inspector occupy separate grid columns. Tablet: when both
  panels are open they use separate columns, with Map available through the navigation.
  Phone: compact strips and details occupy separate stacked grid rows and scroll
  independently; the inspector does not cover or replace the strips. Other data and
  actions remain in the relevant tool views.
- A persistent visibility bar provides Show/Hide traffic and Show details/right panel.
  The Traffic and Details navigation controls remain available as well. Closing either
  panel leaves the other intact. Map-only mode retains selection and both reopen
  controls. The right panel remembers its last tool, including radio draft state.
- Clicking an already selected aircraft reopens details instead of toggling selection
  off. Both the inspector header and embedded detail-card close controls hide the
  inspector without clearing the flight. Clear selected flight is a separate explicit
  action. Closing restores keyboard focus to the corresponding navigation control.

Nine isolated Chromium scenarios passed across ten viewport sizes: 1920×1080,
1440×900, 1366×768, 1100×700, 1024×768, 768×1024, 759×800, 390×844,
320×740 and 844×390. Bounding rectangles verify disjoint panels and, on desktop,
a separate map area. Tests cover same-flight reopening, independent close/restore,
map-only restoration, search/scroll preservation, last-tool/draft retention, resizing
and explicit selection clearing. No uncaught page exceptions. Visual screenshots
were inspected, including the compact phone list. Production build passed with its
existing chunk warning; changed JS/hook lint has zero errors and one existing Fast
Refresh export warning. Evidence: checkpoints/ui_panels_20261116/.

The browser used an isolated profile with a frozen copy of an actual replay response
for stable UI selections. No planning movement, clearance, microphone capture or
model evaluation was created by these checks. Existing servers remain running on
5173/8000; backend, models, thresholds, evaluation reports and deployment were not
changed. Earlier evidence and unrelated pending work are preserved. No commit/push.


## Dark theme refinement — 16 November 2026

Inspected the existing dark screen first: a dim light basemap kept black map labels,
neon green/cyan accents dominated, neutral aircraft headings were brown/low contrast,
and native form controls/theme persistence were inconsistent. Refined presentation:

- Slate base, distinct panel/raised/input surfaces, brighter neutral text and visible
  borders; calmer teal, amber, green and red accents. Selected strips have a distinct
  tinted surface and border. Removed decorative text glows in the workspace.
- Native dark colour scheme, readable inputs/placeholders/dropdowns, consistent
  checkbox/range/meter styling, visible keyboard focus and clearer disabled controls.
  Shared controls also apply to standalone radio/log pages. Fixed watch-list borders
  that incorrectly used an HSL token as a raw CSS colour.
- The online map now remaps the raster's light backgrounds to dark and its labels to
  light using the installed MapLibre raster brightness/saturation shader. This applies
  to basemap pixels only; aircraft colours, observed positions and overlay semantics
  are not inverted. Attribution, scale, popup surfaces and map controls use dark colours.
- Aircraft status headings use readable neutral/status colours. Conflict suggestion
  badges use the theme warning colour. Instruction/ML cards, alert banner, resolution
  dialog and error feedback match the dark palette. Primary amber buttons have explicit
  foreground colours in both themes. Speech model display uses the local model name
  rather than wrapping a full filesystem path across the card; runtime identity/API
  configuration is unchanged.
- The choice is saved only in the app-owned `aerosync.theme` browser-storage key.
  Startup applies the saved dark choice before React renders, and reload/navigation
  retain it. Storage failures fall back gracefully. The isolated browser tests did
  not inspect any personal profile or unrelated storage.

Nine Chromium scenarios passed: controls, reload persistence, all task views, offline
map/menu/keyboard focus, separate phone panels/restoration at 390px and 320px, contrast
samples, labelled conflict/resolution/decision-failure fixtures, standalone radio/log
navigation, and switching back to persisted light mode. Baseline and final desktop/
phone screenshots were visually inspected. Ten sampled text/theme colour pairs met
the 4.5:1 check (lowest approximately 6.49:1); the sampled input boundary passed 3:1.
These are scoped colour checks, not a complete accessibility audit or ML measurement.

An initial harness check expected a focus-visible outline after pointer interaction;
corrected the harness to use keyboard modality before checking keyboard focus. The
final checks pass with no uncaught page exceptions. No recording/clearance/planning
movement was submitted. Build and changed JS lint pass (zero lint errors/warnings in
the checked files); existing bundle-size warning remains. Evidence and before/after
screenshots: checkpoints/ui_dark_20261116/. Backend, inference, model weights,
thresholds, evaluation files and deployment selection are unchanged. Existing servers
remain running at 5173/8000. No commit or push.


## Route availability and display freshness — 16 November 2026

Investigated the user's missing destination question against the live API and source.
Initial snapshot: 33 aircraft, 26 with a route lookup. Subsequent snapshots change as
traffic enters/leaves; counts are availability checks, not destination correctness.
Some entries carried only a fallback aircraft hex identifier. ETD9644 had a cached
404; IGO2142/IGO76AC had no local/bundled route entry. Two valid on-disk routes,
IGO147 and CLX9931, were hidden by a ten-minute in-memory missing-value cache.

Corrected AircraftInfo.route display-cache expiry: unknown/partial/error results are
re-read after ten seconds; complete cached routes retain the existing ten-minute
display expiry. The reader remains fetch=False: no extra network lookup, mutation of
route-feature inputs, source dataset or model preprocessing was added. Three focused
tests pass for background cache population, partial/complete expiry and error recovery.
Restarted the existing launcher in live mode. Frontend/API returned 200 with live
source/no feed error; IGO147 and CLX9931 then showed their available cached routes.
No model accuracy/coverage improvement is claimed from changing traffic snapshots.

Remaining causes: OpenSky's live state vectors supply position/motion rather than a
live intended destination. Its flight origin/destination inference is historical.
The app uses adsbdb callsign lookups; unknown callsigns and missing identifiers cannot
always resolve. The existing model-triggered network lookup path and on-disk cache
freshness policy are unchanged, including retained 404 records. Lookup presence is
not proof of the current flight's destination; schedules/callsigns can be stale.
Reported track and the ten-minute movement forecast do not establish a filed route.
On compact phone layouts, route text is also collapsed in the quick strip list when
details are open; it remains in the selected-flight details when a lookup exists.

Sources: https://opensky-network.org/about/faq (questions 3 and 14) and
https://github.com/FugginOld/adsb-db/blob/main/README.md (callsign route and 404 schema).
No weights, feature calculation, thresholds, evaluation reports, datasets or deployment
selection changed. Unit tests did not run inference or external APIs. Servers remain
running in live mode. No commit/push.


## ATCO live-review corrections (17 November 2026)

Implemented the 16 November review and extended findings. Traffic transport now
survives React development remounts, polls until a valid websocket frame, and resumes
polling for failed/stalled streams. Browser offline is immediate; service-specific
errors and cached-state wording distinguish a conflict-only failure from traffic loss.
Header reports last successful traffic receipt separately from individual position age.
Tracks older than 60 seconds or undated are visibly old; their ETA is withheld. This
is a display cutoff, not an inference eligibility change. Surface phase is neutral;
contradictory ground/high-altitude or speed reports are flagged without rewriting data.

Strips default to 50 NM from VABB with 25/50/100/All options, stable surface/arrival/
callsign ordering and conflict/ownership exceptions. Map retains wider surveillance;
overlap choosers reveal identities while plane coordinates remain unchanged. Header
runway usage is explicitly estimated and not ATIS. Sources and uncertainty appear
beside route/type/ETA; missing metadata dates and filed plans remain unavailable.

Forecast shows distinct-report progress, elapsed wait and unavailable causes. It
does not claim an unexecuted physics fallback. Coverage accounting includes warming
aircraft separately from unchanged model-ready inputs. Alert presentation exposes
existing gate/confirmation, nominal versus alternative geometry, classifier verdict/
thresholds and candidate breach weight. Historical payloads missing these fields say
so. Resolution review separates classifier probability, option heuristic and rank;
it displays signed establishment margin, partial-manoeuvre rationale and residual
risk. No thresholds, weights, features, model inputs or acceptance logic changed.

Sequence rows show overdue duration and linked surveillance context. Controller
Completed/Cancelled close-out persists original movement/target/outcome/revision;
remaining targets stay unchanged and final close-out is not draft-undoable. Review
dialogs keep save/cancel outside scrolling content and contain keyboard focus.
Manual label is Movement callsign with explicit Arrival/Departure choice. Typed
instruction limits match server bounds and reject Heading 999 before submission.
Details prioritize current reported fields ahead of instruction history; phone
search/scope controls share space. Independent traffic/details and dark/light layouts
remain intact. Audit screen reports actual SQLite convention versus database-enforced
protection and fallback state, rather than asserting PostgreSQL immutability.

Validation: production build passes (existing chunk warning), targeted JS lint has
zero errors (existing ControllerWorkspace Fast Refresh warning), 21 Node tests,
75 backend tests and 14 isolated Chromium scenarios pass. Final browser run has no
uncaught page errors. Real live streaming/coverage inspected; failures, close-out and
historical alert rendering use labelled fixtures, with persistence in temporary DBs.
Live plan remains r8 / 8014DA, no QA movements or real instruction/acceptance writes.
No ML evaluation headline or evaluation ledger changes from this task; no backup
restore/failover certification. Both servers stopped at user request and ports 5173
and 8000 confirmed closed. Evidence and item-by-item limits:
../checkpoints/atco_review_fixes_20261117/REPORT.md. No commit/push.
