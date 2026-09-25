# Flight Right — Implementation Plan (v8)

Restructured by dependency rather than by clock. Each phase exists because the one before it makes it possible or makes it trustworthy. Nothing here is timeboxed; a phase is done when its exit gate passes, not when a day ends.

Because the deadline is soft, several things that earlier versions cut purely for time have moved from **cut** to **deferred, in order** — see Phase 9.

---

## PART 1 — THE VERIFIED GROUND

Everything below was checked against the repository, the datasets or the model cards. Nothing is assumed.

### Your code

| Fact | Where |
|---|---|
| Multi-path already shipped: 40 clusters, best-of-5 **63.6%** arrivals, calibrated T=1.729 | `metrics.json`, `multipath.log` |
| Candidates are **fixed per-cluster averages** — no per-aircraft adjustment | `multipath.py:153-160`, `:284-288` |
| That design's ceiling: **74.7%** arrivals even with a perfect classifier | `multipath.py:119-130` |
| A non-neural tree beats the LSTM: **65.7% vs 61.3%** at 10 min | `metrics.json`, `evaluation.md` |
| LSTM worse than arithmetic on within-1-NM at 10 min: **24.73% vs 28.99%** (tree 33.1%) | `metrics.json` |
| Tier comes from **time-to-CPA alone** — ≤180 s tier 1, 180–600 s tier 2 | `cpa_conflict_detection.py:364-373` |
| `conflict_probability()` **does** use the multipath probability when present | `:223-237` |
| Multipath drives tier 2 only; tier 1 stays on constant velocity **by decision** | `inference.py:396-399` |
| Escalation notifies only when probability ≥ threshold (0.85 / 0.60) for **3 consecutive updates** | `:386-395`, `:424-429`, constants `:46-55` |
| The classifier is computed and **never passed into** `escalate_pair` | `inference.py:401-411`, `:415` |
| The domino check is **dead in production** — `traffic=` never passed | `conflict_service.py:126-128` vs `inference.py:332` |
| Backend reads `bundle["pattern_residuals"]` and passes it positionally | `inference.py:175`, `:185-187` |
| `callsign` still dropped in preprocessing; 0.00% null in raw data | `preprocess_sequences.py:51`; a real session file |
| No speech or audio code anywhere | repo-wide search |
| 35 session files, **9 distinct dates**, 291,008 examples | disk listing; `.npz` arrays loaded |
| Stale numbers are in **the .docx and the project-doc README copy**; the repo README is clean | all three opened |
| Hardware is an **RTX 4050, 6 GB** | `CLAUDE.md:1711` |

### The speech components

| Fact | Where |
|---|---|
| `whisper-large-v3-atco2-asr-atcosim` exists, card reports **WER 22.27** | model card |
| `whisper-medium-atcosim` card reports **WER 79.06** | model card |
| Neither card names its evaluation set — both say "fine-tuned on the None/unknown dataset" | both cards |
| `Jzuluaga/atco2_corpus_1h` = 871 rows, ~1 h, columns are only `id`, `audio`, `text`, timings | dataset card |
| **No callsign, command or value columns. No nearby-aircraft list.** | dataset card |
| `jlvdoorn/atco2-asr-atcosim` has train 8.09k, validation 2.03k, **no test split** | dataset card |
| faster-whisper on large-sized models: **int8 = 2,926 MB VRAM**, int8 batch 8 = 4,500 MB / 16 s | project benchmark |
| faster-whisper loads fine-tuned HF checkpoints via `ct2-transformers-converter` | project README |

**Not verifiable from here:** installed package versions, `nvidia-smi` output, free disk, whether `verify_pipeline.py` passes today. The 110/110 baseline appears three times in `CLAUDE.md`. Also unverified: whether `atco2.org` serves the annotated test set without registration — the page would not load for me.

---

## PART 2 — WHY THE ORDER IS THE ORDER

Four dependencies drive everything:

1. **You cannot measure an improvement against numbers that are wrong.** Three documents publish figures the code does not produce. Fix those before generating new ones, or every "better than before" claim is anchored to fiction.

2. **You cannot trust a measurement of a system that is not wired up.** The classifier the headline measures gates nothing at runtime; the secondary-conflict check runs on an empty list in production. Measure after fixing, not before, or the numbers describe a system nobody is running.

3. **Cheap questions must be answered before expensive work depends on them.** Whether the archive holds Indian low-altitude data, whether the speech test set carries labels, whether the model was trained on its own test set, and whether the field we wrote off as unavailable is actually available from a different open source — each takes minutes and each changes what comes after.

4. **Voice eliminates candidate paths, so the candidate paths have to be good first.** Narrowing a fan of five where four are 80 NM wrong is not a demonstration of anything.

---

## PHASE 0 — MAKE THE GROUND TRUE

Nothing else is meaningful until this is done.

**0.1 — Re-score from the saved files.** Run `python ml_pipeline/utils/reevaluate_models.py`. It opens every saved model in a fresh process with no access to the training code. This is your reference row.

**0.2 — Fix `Flight_Right_ML_Approach.docx`.** I opened it; it contains every one of these:

| It says | It should say |
|---|---|
| "18 sessions between 24 August and 1 September… 329,647 reports… 198,537 examples (143,117 / 27,552 / 27,868)" | 35 session files, 9 distinct dates 24 Aug – 5 Sep, **291,008 examples (205,757 / 45,637 / 39,614)** |
| table: 99.93 / 91.49 / 79.28 / 51.82 against 99.96 / 93.51 / 84.92 / 64.47 | **98.43 / 89.46 / 77.33 / 50.50** against **98.46 / 91.96 / 82.90 / 61.31** |
| "from 11.02 to 6.41 nautical miles" | **10.30 → 6.41** |
| "the straight-line method is right for 1.4% of them and our model for 30%" | **15.8% and 34.8%** |
| conflict table: 99 / 93 / 82 / 69% caught at 32–39 false alarms per 1,000 | the one measured operating point: **94.0% caught with ≥3 min warning, recall 0.944, precision 0.386, 96.8 false alarms per 1,000**, with the two rule-based rows beside it |
| "five options from 60 route patterns reaches 69.3%, against 30% today" | shipped configuration is **40 patterns, best-of-5 63.6%, top-1 38.6%** |

The 1.4% line is the worst single error in the document.

**0.3 — Fix the `README.md` copy in the Claude project.** Created 4 Sep, still has §4A and §13B with the same stale figures. The repo README was rewritten on 20 Sep and is clean — replace the project copy with it, or delete the copy so there is one README.

*On §13B's cluster table:* the 8 / 25 / 60 / 150 figures are real, recorded in `multipath.py:40-42` as the experiment that chose 40. Correct it by stating 40 is shipped; do not delete the experiment.

**0.4 — Add the two findings the .docx omits:** the tree leads the LSTM by 4.4 points at ten minutes, and the LSTM is worse than arithmetic on within-1-NM at ten minutes. Burying them is the only way they become a problem.

**0.5 — Resolve four internal contradictions:**
- `CLAUDE.md:1236` says arrivals 35.8 / all 60.9; `metrics.json` says 34.8 / 61.3
- 60.8 (`:1511`) vs 60.9 (`:1095`) vs 61.3 (`evaluation.md`)
- "all 36 raw parquets" (`:1069`) vs 35 on disk today
- the `gbt_*` values in `metrics.json` are hand-rounded to one decimal while everything else carries full float precision — Rule 8 is broken inside the file that enforces it

**0.6 — Build and verify the environment.** `pyopensky`, `transformers`, `faster-whisper`, `ctranslate2`, `librosa`, `soundfile`, `jiwer`, `rapidfuzz`. Import every one. On Python 3.13 with a very new numpy and pandas this is where an evening goes. Fallback: a separate Python 3.11 environment for voice only, kept away from the training environment.

**Exit gate:** `reevaluate_models.py` produces the reference row · `verify_pipeline.py` at its recorded 110/110 · every package imports · no document contradicts another.

**From here on: `docs/evaluation.md` and `docs/metrics.json` are authoritative. Everything else quotes them. No number is ever typed by hand into a document.**

---

## PHASE 1 — MAKE THE RUNNING SYSTEM MATCH THE DOCUMENTED ONE

Four defects where the code does something other than what the documents describe. All of them corrupt either a later measurement or the demo.

**1.1 — Wire the classifier into escalation.**

The system decides whether to raise an alarm using a geometric rule — "are these two inside 8 NM and 1,500 ft?" The XGBoost classifier, which is what the 94.0% headline measures, is calculated, displayed, and never consulted for that decision. Two observed alarms fired on aircraft 1,100 ft and 1,068 ft apart — legally separated, ordinary traffic — while the classifier said 0.35% and 0.41%.

**State the gap precisely or a reviewer will catch an overstatement.** Escalation is not blind to the models: `conflict_probability()` uses the multipath probability whenever one is attached, and multipath drives tier 2. But tier 1 stays on constant velocity by deliberate design, so for those two tier 1 pairs the probability fell back to a flat 1.0. **The gap is the classifier specifically, not multipath.**

The change:
- add an optional `probability` parameter to `escalate_pair` (`cpa_conflict_detection.py:415`), defaulting to `None` so `verify_pipeline.py`, `test_two_tier_demo.py`, `resolution_engine.py` and `reevaluate_models.py` keep their current behaviour
- pass `result["classifier"]["conflict_probability"]` at the single call site, `inference.py:409-411`
- **keep a floor:** if the pair genuinely breaches 5 NM / 1,000 ft, the geometric rule wins regardless. The safety net stays a safety net

**1.2 — Make the secondary-conflict check live.** `assess_pair` declares `traffic: Sequence[...] = ()` at `inference.py:332`, and `conflict_service.py:126-128` never passes it. The check added on 7 September runs with an empty neighbour list in production and works only inside `verify_pipeline.py`. Pass it.

**1.3 — Let the callsign through preprocessing.** `preprocess_sequences.py:51` requires eight columns and callsign is not one, so it is discarded — despite being 0.00% null in every session. At this stage it is a **join key, not a model feature**. Follow the pattern already used for `vertical_rate` at lines 56-61: excluded from the hard-required list with a documented fallback, because a missing value should not discard an otherwise good track.

**1.4 — Fix the datalink button.** `NLPCommsPanel.jsx:86` reads `APPROVE & TRANSMIT VIA DATALINK`, line 82 toasts "Datalink clearance transmitted", and the post-click state reads `TRANSMITTED`. The panel header at line 22 *is* labelled "(DEMO — NOT IMPLEMENTED)" and the internal log does say "mock" — so it is not unlabelled — but the button and toast make a claim the header's disclaimer does not cover, and on a demo screen that is what reviewers remember. Match the wording `ResolveModal.jsx` already uses: button → `APPROVE — RECORD DECISION (DEMO)`, toast → "Decision recorded. Nothing transmitted.", state → `RECORDED`. Text only.

**Then re-check C1, C2 and C4.** All three observed instances came from pairs that should never have reached tier 1. Fix what survives; document the rest as open.

**Exit gate:** `verify_pipeline.py` still 110/110 · `reevaluate_models.py` re-run and the new headline published with the reason stated · the two pairs from ISSUES.md no longer raise tier 1 · the frontend builds.

Expect the headline to move. **A number that moves for a stated reason is worth more than one that never moves.**

---

## PHASE 2 — ANSWER THE CHEAP QUESTIONS BEFORE BUILDING ON THEM

Six questions. Each is minutes of work and each changes what a later phase does.

**2.1 — Is Trino live?** Username in **lowercase**, password into pyopensky's `settings.conf` beside the client id and secret you already hold. Run one tiny query. Access was granted and your account is university-affiliated, so refusal is not expected. If refused, check username case, a missing partition filter, and whether the permission flag has actually been applied, before emailing.

**2.2 — The selected altitude: not in OpenSky, but available elsewhere.**

What it is, in plain terms: the number a pilot dials into the autopilot when told "climb to 30,000 feet". The aircraft stops at exactly that number. Knowing it means knowing where a climbing aircraft will level off — before it levels off. That is the single biggest available reduction in false alarms during vertical manoeuvres.

OpenSky's archive does NOT have it, and that is permanent. It stores `supportstargetstatereport`, a flag recording which aircraft were *capable* of broadcasting the value — not the value itself. Confirm this once, record it, and stop querying OpenSky for it.

But other open networks that decode the same broadcasts DO keep it. Verified over Mumbai on 23 September 2026 against adsb.lol:
- live, within 60 NM of VABB: 12 of 12 aircraft carried `nav_altitude_mcp` at one moment (Archit); 9 of 13 at another (Claude) — 9 of 11 airborne, the two misses being one ADS-B version 0 transponder, which has no message for this value, and one version 2 aircraft at 4,000 ft
- history: the per-aircraft trace files carry it too, at index 8 of each trace point, changing through the flight as the aircraft is re-cleared — e.g. IGO5323 on 22 Sep, 8992 → 16000 → 28000 → 32992 → 31008 → 26016 → 8992 → 7008 → 6016. **Index 8 is populated on roughly a quarter of trace points** (834 of 3,339 and 816 of 3,266 in the two files checked), not every point
- readsb defines the field as "selected altitude from the Mode Control Panel / Flight Control Unit (MCP/FCU) or equivalent equipment"

The same trace points also carry wind direction and speed (`wd`, `ws`), outside air temperature (`oat`), indicated and true airspeed, Mach and roll angle — none of which OpenSky provides.

So this item is NOT closed. It moves from "unavailable" to "available from a different source, at a cost in download volume". See Phase 9.

**2.3 — Does the archive hold Indian data, and does it hold it low down?** Every query must filter on the partition column — `hour` for `state_vectors_data4`, `day` for `flights_data4` — or it is rejected.

- **Test A** — rows in the Mumbai box by month, three years back
- **Test B** — the same, below 10,000 ft and within 60 NM of VABB

Test B matters more. Descending arrivals are your weak regime, and low-altitude reception needs a receiver nearby, so Test A can look healthy on cruise traffic while this is empty. OpenSky's own 2025 report describes coverage as saturated in Europe and the US with South Asia still improving. **A thin result is a publishable finding** — nobody has measured Indian low-altitude coverage in the largest open ADS-B network.

**2.4 — Does the speech test set carry the labels? (blocking for Phase 6)**

`Jzuluaga/atco2_corpus_1h` has audio and transcripts only — six columns, no callsign, action or value fields, no nearby-aircraft list. The named-entity annotations described in the corpus paper live in the official release at `atco2.org/data`, not in the HuggingFace mirror.

Pick one:
- **Get the official release** and use its XML annotations
- **Hand-label 100–150 of the 871 clips yourself** — callsign, action, value. Defensible as long as you state the sample size

**2.5 — Was the model trained on its own test set?**

`jlvdoorn/atco2-asr-atcosim` has no test split, so the large-v3 card's 22.27 is a validation score, not a score on the 871 test clips. The question is whether those 871 clips are inside its 10.1k training rows.

Load both, lowercase and strip punctuation from the transcripts, and count how many of the 871 appear in the training set. **If overlap is high you have no clean ATCO2 test for large-v3**, and `medium-atcosim` becomes your only held-out measurement. Report the overlap whatever it is.

**2.6 — How far back can we fetch per-aircraft trace files directly?** The trace file was fetched straight over the web, one aircraft at a time, with no bulk download. If that works for the recent past, the collector can simply request one file per Mumbai aircraft per day and the 2,115 GiB archive never needs touching. If it only serves the current day, we need the daily GitHub releases instead. Ten minutes to find out, and it decides the whole shape of Phase 9.

*Observed while verifying 2.2, not yet the answer:* `trace_full_<hex>.json` fetched on 23 Sep covered a rolling window of about 25 hours (22 Sep 09:10 → 23 Sep 10:08 UTC for one airframe, several flights). Whether older days are reachable directly is still the open question.

**Exit gate:** all six questions have written answers, and Phases 3–6 have been adjusted to whatever those answers were.

**If Test B came back healthy:** start a bulk download here — one query per calendar day, in sequence, appending to parquet. It runs unattended alongside everything else. It is an input to Phase 3's retrain, not a blocker for it.

---

## PHASE 3 — RAISE THE PREDICTION QUALITY

**3.1 — Per-mode regression: remove the ceiling.**

In plain terms: today, "you are on pattern 17, so add pattern 17's average offset" — every aircraft in a pattern gets the same number. Instead: "you are on pattern 17, so add the offset a model predicts *for you*, given that you are on pattern 17."

Why it should help: a per-pattern constant cannot beat 74.7% on arrivals even with a perfect classifier, and the shipped model is at 63.6%. A per-pattern regression has no such cap. The failure is visible in the repo's own worked example — option 1 was 3.81 NM out, options 2–5 were 24, 74, 77 and 88 NM out. Those are not alternative futures, they are other clusters' averages.

Use a `HistGradientBoostingRegressor` on the 83 features plus the pattern id. It is what already beats the LSTM at single-answer prediction, it is what the pattern classifier already is, it trains on CPU in minutes, and it leaves the GPU free for the speech model.

Touch points, all verified:

| Location | Change |
|---|---|
| `multipath.py:153-160` | the mean-residual loop becomes a per-(pattern, horizon) fit |
| `multipath.py:95,164` | return fitted models, not a `(40,4,3)` array |
| `multipath.py:284-288` | the table lookup becomes a prediction call; `features` is already in scope at line 272 |
| `multipath.py:167-182` | `print_cluster_report()` indexes the array directly — it will break |
| `multipath.py:466, 513-518, 554-579` | call site and pickle key |
| **`inference.py:175, 185-187`** | **reads `bundle["pattern_residuals"]` and passes it positionally. Version the pickle and keep the old array path loadable, or the backend the demo runs on will not start** |

That last row is the one most likely to bite.

**The honesty trap.** The regressor is trained with the *true* pattern id — standard, and fine. But at inference the pattern comes from the classifier, which is sometimes wrong. **Never report a number computed with true pattern ids.** `best_of_k_within` (`:291`) already scores against predicted patterns and carries a comment forbidding exactly this.

**If it misses the gate:** keep the shipped model, record the row, and report the 74.7% ceiling as a measured architectural limit. That is a finding, not a failure.

**Neural alternative, only if the tree route fails:** five learnable outputs on the LSTM with winner-takes-all. The trap is mode collapse — the first head to get good keeps winning and the others never receive a correction. The published fix is annealed winner-takes-all, which cut miss rate by roughly a third on standard motion-forecasting benchmarks.

**3.2 — Prune the candidate fan.** Conflict checking runs over all five candidates, including ones 80 NM out with probabilities under 0.03. Checking a path the model barely believes in, against every other aircraft, is a false-alarm generator. Keep only the candidates covering 90% of the probability mass, or drop below a floor. Measure conflict recall and false alarms per 1,000 both ways.

This also answers the obvious reviewer question — *"doesn't checking five paths give you five times the false alarms?"* — which currently has no answer. And it builds the plumbing Phase 7's constraint filter reuses.

**3.3 — Retrain and establish variance.** Full retrain of whatever cleared the gate, plus **three random seeds**. One run per method is a standard published signal that a result will not reproduce. If the Phase 2 bulk download landed, re-preprocess over the larger dataset and train on that too, as a separate row.

**Exit gate:** best-of-5 on test arrivals at ten minutes beats **63.6%** · top-1 not below **38.6%** · both still beat constant velocity at every horizon · gates read from stdout, not the exit code (`multipath.py:583-587` prints PASS/FAIL without exiting non-zero) · the backend loads both the new pickle and an old one · `verify_pipeline.py` still 110/110 · three seeds recorded.

---

## PHASE 4 — BUILD THE SPEECH-TO-TEXT COMPONENT

You are not training a speech model here. Published ATC models exist with peer-reviewed results; your contribution is the callsign matching and clearance extraction in Phase 6. Your own fine-tune is Phase 9.

**4.1 — Three models, one code path, all printed side by side.**

| Role | Model | Why |
|---|---|---|
| **Ships in the demo** | `whisper-large-v3-atco2-asr-atcosim` | Card: 22.27 WER. Trained on both corpora, so it handles real radio. Its transcripts are good enough for Phase 6 to work on |
| **Held-out measurement** | `whisper-medium-atcosim` | Card: 79.06 WER. Never saw ATCO2, so on ATCO2 it is a genuine cross-corpus test |
| **Permanent baseline** | untouched `openai/whisper-medium` | Your own README rule. Published figure for untouched Whisper on ATC audio is around 94.6% words wrong |

**The contrast between 22 and 79 is a result in itself** — a direct measurement of how badly ATC speech models collapse outside the corpus they trained on. That is the argument for why Indian ATC audio needs its own data, and the argument Phase 9's fine-tune exists to answer.

Both cards say "fine-tuned on the None/unknown dataset" and neither names its evaluation set. Treat 22 and 79 as indicative; your own measurement is what you report.

**4.2 — Make it fit 6 GB.** Whisper large is 1.55 billion parameters, about 3.1 GB of weights in fp16 — it fits, but not alongside a training job. Convert to CTranslate2 **int8** with `ct2-transformers-converter` and serve with faster-whisper: 2,926 MB single, 4,500 MB at batch 8, roughly four times faster.

**Verify the quantisation rather than assuming it.** Run the converted model and the plain `transformers` model on the same 50 clips and compare WER. If int8 costs more than about a point, drop to fp16 and accept the slower run. Record which you used — it goes in the model version string.

**4.3 — Build it model-agnostic from the start.** This is what "published now, fine-tune later" requires; designed in later means touching every file.

- **One config key.** `ASR_MODEL_ID` in `server/app/config.py`, beside the existing model paths. Nothing else in the codebase names a model.
- **Model version on every row.** The `transcriptions` table carries `model_id`, `quantisation` and `asr_version`. Your audit log already fails at this — H2, `modelVersion` null on every row — do not repeat it in a new table.

**4.4 — Where it lives.** Follow the split already there, offline under `ml_pipeline/`, serving under `server/app/ml/`, exactly as trajectory and multipath are organised:

```
ml_pipeline/voice/
  transcribe.py        run the model over a folder of clips, cache to parquet
  extract.py           transcript -> callsign | action | value   (Phase 6)
  match_callsign.py    rapidfuzz against your own airborne list  (Phase 6)
  evaluate_voice.py    the four metrics, three models side by side

server/app/ml/
  asr.py               loads the converted model, same shape as MultiPathPredictor
  saved_models/asr/    the CTranslate2 model directory
```

`evaluate_voice.py` is the voice equivalent of `reevaluate_models.py` — one command, opens the saved model, measures it, writes a dated JSON. Rule 8 applies to voice numbers too.

**4.5 — The four metrics.**

1. **Clearance accuracy (headline)** — out of 100 transmissions, how many became the completely correct aircraft + action + value
2. **Callsign accuracy**
3. **Action and value accuracy** — "descend 130" versus "descend 310" is the difference between safe and not
4. **Word error rate** — comparison with published work only, never the headline

Plus real-time factor, and reported per corpus — never averaged across clean and noisy.

*Why word error rate is not the headline, measured in a paper in your own pack:* a system hit 17% WER, but its callsign extractor scored 0.95 F1 on human transcripts and 0.67 on its own machine transcripts. It missed 43% of callsigns and WER hid it completely.

**Above about 85% word accuracy on real radio is not defensible.** Do not set a target above it.

**Exit gate:** all three models measured on all four metrics, per corpus · the quantisation check recorded · changing `ASR_MODEL_ID` to a different model runs the whole chain end to end without touching anything else.

---

## PHASE 5 — GET MUMBAI AUDIO

The ATCO2 clips are European. You cannot demonstrate matching a heard callsign against your own Mumbai aircraft list with them — there is nothing to match to. This phase produces the only legal Mumbai-callsign audio that exists.

Write scripts using real callsigns pulled from your own sessions, real Mumbai runways (09/27, 14/32) and real arrival routes. Three or four classmates, fifteen minutes each, phone microphone, quiet room. Then a 300–3400 Hz band-pass filter so it sounds like radio.

**Test set only, never training data.** Twenty to thirty minutes is far too little to train on, and enough to produce what is, as far as anyone knows, the first measurement of these models on Indian-accented ATC phraseology — reported as preliminary, with the sample size stated. Expect it to be worse: a model trained on European ATC scored 55.3% words wrong on another region's accent, and the authors concluded these models cannot generalise to accents absent from training.

**Do not attempt to record real Indian ATC radio.** No volunteer receiver coverage of Indian airports, and receiver licensing under the Indian Wireless Telegraphy Act 1933 and the Indian Telegraph Act 1885 is an open legal question the department should rule on first.

**Then pre-transcribe everything** — all 871 ATCO2 clips and all your recordings — into the `transcriptions` table.

**Exit gate:** recordings made, filtered, transcribed, and rows in the table with correct model version fields.

---

## PHASE 6 — TURN TRANSCRIPTS INTO CLEARANCES

**6.1 — Extraction.** Transcript text → `callsign | action (DESCEND / CLIMB / TURN / DIRECT / SPEED) | value`.

Rules first. ATC phraseology is a small, rigid vocabulary, so regular expressions get most of the way. Add a classifier only if the rules measurably fall short. Score against whatever Phase 2.4 produced — official annotations, or your own hand-labelled subset with the sample size stated.

Add a **confidence score computable without knowing the right answer**, so the dashboard can grey out transcripts it does not trust. A normalised uncertainty score of this kind is described in a paper already in your pack and correlates with word error rate.

**6.2 — Callsign matching. This is the part that is genuinely yours.**

Match the heard callsign to the nearest real callsign airborne in the Mumbai box at that timestamp, using rapidfuzz.

The callsign is the hardest part of a transmission and the most important — a perfectly transcribed "descend flight level 130" is worthless attached to the wrong aircraft. Published work that gave the recogniser the list of aircraft actually in the area took callsign accuracy from 35.2–64.4% to 87.0–95.0%. Most groups need a radar surveillance feed for that list. **Your poller produces it every 5–15 seconds** — and after Phase 1.3 it survives preprocessing.

**Do it as post-processing. Do not put the callsign list into Whisper's prompt.** Measured: prompting Whisper with a word list cut rare-word error from 23.7% to 18.0% but made *overall* accuracy worse on 6 of 11 test sets, because the prompt field behaves like a text-continuation prompt rather than a bias list. Biasing also degrades as the list grows — entity error rose from 1.80% with a perfect list to 5.61% with about 1,800 distractors. Post-processing cannot make the transcript worse.

**Report your own measured gain.** The 87–95% and 74.2% figures came from Kaldi-style recognisers where the list enters the decoder's search graph. Whisper does not work that way.

**Two measurements, never merged:** on ATCO2, using a callsign list built from the gold annotations of neighbouring transmissions in the same recording, labelled plainly as a proxy for a surveillance list. On your Mumbai recordings, against your real list.

**Exit gate:** extraction and matching accuracy measured on both corpora, separately, with the label source and sample size stated.

---

## PHASE 7 — JOIN IT UP

**7.1 — The oracle test: what is hearing the radio actually worth?** No audio needed. For arriving aircraft in your own sessions, read the clearance **out of the truth** — the level it actually levelled at, the heading it actually turned to — and feed it to the predictor as if heard perfectly.

**Run it against the Phase 3 model**, not the single-answer LSTM and not the old multi-path. The question is "what does a heard clearance add on top of 63.6% best-of-5", not "on top of 30%". Running it against the old baseline would overstate the value of voice by roughly a factor of two.

Label it **"upper bound, assuming perfect clearance recognition"**, every time it appears. Combined with Phase 4's measured clearance accuracy, the realistic estimate follows.

If the oracle number is barely above the Phase 3 model, the honest conclusion is that clearances are not the bottleneck — and finding that out cheaply is a good outcome.

**7.2 — The constraint filter.** When a clearance is extracted, drop the candidate paths that contradict it. Heard "descend flight level 130" → discard candidates that do not descend toward FL130. Heard "turn left heading 090" → keep only candidates consistent with it. Shares Phase 3.2's plumbing. **Voice does not pick the right path, it eliminates the wrong ones.**

*Why not the published fusion approach:* SIA-FTP (*Nature Communications*, 2024) retrains the trajectory model to consume instruction embeddings and reports over 20% relative reduction at longer horizons — but it needs time-aligned voice and surveillance data for the same airspace, which does not exist for Mumbai and cannot be legally collected. Their recogniser also ran at 1.39% character error against your 14–23% words wrong, so their robustness result does not transfer.

**7.3 — The demo, with the mechanism stated correctly.**

What the code actually does:

- `assign_tier()` decides the tier from **time-to-CPA alone** — ≤180 s tier 1, 180–600 s tier 2
- `conflict_probability()` returns the **multipath probability** when one is attached
- `meets_alert_conditions()` returns `probability >= threshold` for that tier — **0.60 for tier 2**
- `escalate_pair()` sets `notify` only when that has held for **3 consecutive updates**

So narrowing the fan changes the probability, which can push it under 0.60, which zeroes the consecutive count, which flips `notify` off. **The pair leaves the watch list.** That is the demo beat — the stated probability moving and watch-list membership changing. A tier change is a bonus, because tier only moves if the multipath CPA's timing shifts.

**Pick a tier 2 pair.** A tier 1 pair runs on constant velocity by decision and will not respond to the fan narrowing at all.

**Prove it before wiring any UI.** Replay a candidate pair and print its escalation dictionary — `probability`, `probability_threshold`, `notify`, `tier` — with the full fan and with a narrowed fan, side by side. If nothing moves, pick a different pair. This is the difference between a demo that lands and one that visibly does nothing.

**Serving.** Everything was pre-transcribed in Phase 5, so the demo reads rows from a database — **zero inference at demo time means zero demo risk.** Add a "transcribe now" button on one clip calling the same code path live; if the GPU is busy it falls back to the cached row. Do not transcribe on page load — a model that takes two seconds to warm up makes the dashboard feel broken.

**The chain on screen:**

> a recorded Mumbai transmission plays → transcript appears → extracted callsign, action and value appear with a confidence score → the callsign is matched to a real aircraft in the replayed session → that aircraft's candidate fan narrows → its stated conflict probability moves → the pair joins or leaves the watch list

**Two new tables**, fitting the existing schema: `transcriptions` (clip reference, timestamp, frequency, raw transcript, `model_id`, `quantisation`, `asr_version`, confidence) and `extracted_clearances` (transcription id, matched icao24, callsign heard, callsign matched, action, value, confidence).

**One scenario working perfectly, not five working badly.**

**Exit gate:** the full chain on a tier 2 pair, end to end, with the audit row written to PostgreSQL and read back through the API.

---

## PHASE 8 — THE EVIDENCE

**8.1 — The ablation table.** For a system paper this *is* the result.

| Configuration | Arrivals, 10 min, within 5 NM (top-1) | (best of 5) |
|---|---|---|
| Constant velocity | 15.8% | — |
| Single-answer LSTM | 34.8% | — |
| Tree reference (single answer) | — | — |
| Multi-path, fixed cluster offsets (shipped) | 38.6% | **63.6%** |
| + per-mode regression | ? | ? |
| + candidate pruning | ? | ? |
| + more data, if Phase 2 found any | ? | ? |
| + heard clearance (oracle — **upper bound**) | ? | ? |

Report per regime too — turn magnitude, vertical behaviour, distance to VABB. Every row reproducible from a saved config. **A feature that did not help stays in the table.**

**8.2 — Variance.** Mean and spread across the three seeds, with a confidence interval on the headline.

**8.3 — The honesty pass.**

**Can claim, with numbers:** each change's measured contribution; the false-alarm cost of multi-path candidate checking, measured both ways; measured coverage of Indian airspace in the OpenSky archive including the low-altitude case; your own measured callsign-matching gain; clearance accuracy per corpus, in-domain and held-out separately; the first measurement of these models on Indian-accented ATC phraseology, with sample size; the upper bound on what hearing the radio is worth.
- measured coverage of the autopilot selected-altitude broadcast over Mumbai, from an open ADS-B network — to our knowledge unpublished for Indian airspace

**Cannot claim:**
- any figure on real Indian ATC radio
- **any ATCO2 figure from large-v3 as held out**, unless Phase 2.5 came back clean
- **any extraction score as "against gold labels"** if the labels were your own hand-labelling — say so, with the sample size
- the published 87–95% or 74.2% callsign figures (different recogniser)
- the SIA-FTP robustness result (their recogniser was ten times more accurate)
- production-ready or real-time transcription
- that voice improves trajectory prediction, unless measured
- ">95% accuracy" as a blanket claim — defensible at 1 and 3 minutes, nowhere near it at 10
- **that the LSTM is your best trajectory model** — the tree beats it

**Must state:** that four critical runtime defects were found by driving the system; that the classifier gap was fixed; that the secondary-conflict check was inactive in the live path until Phase 1; and that H1 — most audit entries never leaving the browser — remains open. A project that finds its own defects and says so reads far better than one that did not look.

---

## PHASE 9 — AFTER THE CORE LANDS

Because the deadline is soft, these move from cut to queued. Roughly in value order.

**9.0 — Collect the selected altitude and wind from adsb.lol.** Highest value item in this phase, because it supplies two fields the plan had given up on.

Two routes, and 2.6 decides which:
- per-aircraft trace files fetched directly, one request per aircraft per day (tiny, preferred)
- the daily GitHub release dumps, filtered down to the aircraft IDs our own 35 OpenSky sessions already list (large download, no spatial index, so filtering by our known hex list is what makes it tractable)

Measure before building: over a full week, what share of Mumbai aircraft actually populate `nav_altitude_mcp`? 12 of 12 at one instant is encouraging, not a measurement — and 9 of 13 at another instant on the same day shows why. Measure also how often per flight: in the two trace files checked, the detailed object carrying it appears on roughly a quarter of trace points.

Then: a "will it level off" feature becomes a real observed field rather than the estimated substitute the earlier plan proposed. Report accuracy with and without it, as an ablation row, same as every other feature.

Licence: ODbL 1.0. It has attribution and share-alike conditions. Read them before anything derived from this data goes in the report.

**9.1 — Runway in use.** Mumbai's two runways are nearly perpendicular, so which is active flips the entire arrival geometry, and the model has no idea which it is looking at. Derive it from your own landings with `traffic`'s `Flight.landing()`, which detects alignment with a runway's approach path — do not hand-roll an angle-snapping heuristic. **Spot-check five to ten detected landings by eye before trusting the set.** Derived from real observations, not invented, and the manual check is what lets you say so.

**9.2 — Indian route-lookup accuracy.** How often adsbdb and hexdb agree with where your tracks actually ended up. Benchmarked elsewhere at roughly 60% in Southeast Asia and as low as 13–27% in the US. **There is no published figure for India.** About an hour's work, and a genuinely novel number.

**9.3 — Your own Whisper fine-tune.** LoRA on Whisper-small over ATCOSIM plus UWB-ATCC, roughly 25–30 hours of free audio, the published number to beat being 15.1% WER. **Split by speaker and recording session, never randomly** — one controller speaking 200 clips landing in both train and test inflates the score exactly the way random-row splitting once inflated your trajectory results. The HuggingFace copies ship pre-made splits; check them for speaker overlap before trusting them. It swaps in through `ASR_MODEL_ID` if it beats large-v3 on your own test set.

**9.4 — Aircraft type.** Join by `icao24` — the OpenSky aircraft-database page currently says the crowdsourced database returns "at a further date", so use `traffic`'s aircraft database or hexdb / adsbdb, one cached pass, results written to disk. Convert type to performance numbers with OpenAP rather than hand-building a table. Modest gain, mostly vertical.

**9.5 — Surrounding traffic.** Free, already on disk. It explains only the vectored residual — the part where a controller has taken an aircraft off its published route — so it **must** be measured on top of route structure or it gets credited with structure's gain.

**9.6 — Wind aloft.** Wind is reported by the aircraft themselves in the adsb.lol trace points (`wd` direction, `ws` speed, plus `oat` temperature). If 9.0 lands, wind arrives in the same file at no extra cost and is a real observation rather than a model estimate. Keep Open-Meteo documented as the fallback if 9.0 does not land: its Historical Forecast API has pressure-level winds, no key, free tier 10,000 calls a day; snap each track point to a coarse grid (0.25°, 1 hour, pressure level), deduplicate to a few hundred cells, cache, join back — **never call per row**. Either way, wind mostly fixes along-track error, which `evaluation.md` itself calls "mostly harmless for separation", so it improves the headline more than the safety case. Say that rather than letting a reviewer say it.

**9.7 — C1 properly fixed, regardless.** `resulting_vertical_separation_ft` must be recomputed after the manoeuvre. Even with the classifier gap closed, a stale separation quoted as an outcome will resurface on a real conflict.

**9.8 — H1, the audit gap.** 44 `logAudit()` call sites writing to `sessionStorage`; `postAuditLog` exported and never called. The append-only PostgreSQL guarantee is real but protects a fraction of what the documents imply reaches it.

### Permanently out

| Out | Why |
|---|---|
| Selected altitude from OpenSky specifically | OpenSky stores only a capability flag. Available from adsb.lol instead — see 9.0 |
| Destination as an arrivals feature | Every Mumbai arrival's destination is VABB. It cannot help the headline metric |
| REST `/flights` credit budgeting | Deleted by Trino's `flights_data4` |
| Real Indian ATC radio recording | No receiver coverage, and an unresolved legal question |
| Live streaming transcription | Chunking, voice activity detection, latency — and the demo does not need it |
| Retraining the LSTM to beat the tree | Tried three times, overfits from epoch 12, the tree never lost |

---

## RULES THAT DO NOT BEND

1. Split by session date, never randomly. For speech, split by speaker and recording session.
2. Print the baseline next to the model on every run — constant velocity for trajectories, untouched Whisper for speech. If the model does not beat it, there is a bug. Find it, do not tune.
3. One change at a time, with a recorded ablation row.
4. Per horizon and per regime; per corpus for speech. Never a single average.
5. Every oracle number is labelled an upper bound every time it appears.
6. Best-of-5 is coverage, not accuracy — always with "best of five candidate paths" attached, always beside top-1.
7. Derived is fine; inferred is fine if its own accuracy is reported; invented is banned. Synthetic demo audio is invented — demo only, never a number.
8. No number is typed by hand into a document. Everything comes from `metrics.json` and its voice equivalent.

---

## WHEN SOMETHING GOES WRONG

| Situation | Response |
|---|---|
| Phase 3's pickle breaks the backend | Most likely single failure. Version the pickle; keep the old array path loadable |
| Official ATCO2 annotations unobtainable | Hand-label 100–150 clips and state the sample size |
| Contamination check shows overlap | No clean ATCO2 test for large-v3. Report `medium-atcosim` as the only held-out number and say why |
| int8 conversion costs accuracy | Drop to fp16, accept the slower run, record which you used |
| Per-mode regression misses the gate | Keep the shipped model, record the row, report the 74.7% ceiling as a measured limit |
| The escalation dictionary does not move when the fan narrows | Pick a different tier 2 pair. You found out before wiring anything |
| Install fails on Python 3.13 | Separate 3.11 environment for voice only |
| Trino query refused | Check username case, partition filter, permission flag — in that order — before emailing |
| Coverage Test B is thin | Report the measurement as a finding. You lose nothing you had |
| Fixing the classifier gap changes the headline | Publish the new number with the reason |
| adsb.lol direct trace fetch only serves the current day | Fall back to the daily GitHub release dumps, filtered to our known aircraft IDs |
| nav_altitude_mcp coverage over a full week turns out to be low | Report the coverage figure as the finding and keep the estimated level-off substitute. A measured coverage rate for Indian airspace is publishable either way |
| Classmates fall through | Record it yourself in several voices, or text-to-speech. **Demo only, labelled, never in a quoted number** |
