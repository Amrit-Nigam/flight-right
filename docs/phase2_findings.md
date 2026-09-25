# Phase 2 — the five cheap questions, answered

**Measured 22–23 September 2026.** Every number here is produced by a committed script and
written to a dated JSON in `ml_pipeline/reports/`. Nothing is typed by hand.

> **Updated 23 September: Trino access was granted, and 2.1, 2.2 and 2.3 are now answered
> rather than blocked.** The original blocked findings are kept below the line in each
> section, because the diagnosis they record is what made the fix a one-line retry.

| Reproduce with | Covers |
|---|---|
| `python scripts/check_trino.py` | 2.1, 2.2, 2.3 |
| `python ml_pipeline/voice/check_corpora.py` | 2.4, 2.5 |
| `python scripts/check_adsblol_history.py` | 2.6 |

**Summary.** Four of the five came back better than expected once Trino access arrived; the
fifth is a permanent limit that is worth knowing about now rather than later. *(Corrected
23 September: the fifth, 2.2, is permanent for OpenSky only — the same value is available
from adsb.lol. See the correction under 2.2.)* Three of the
answers only came out right because the obvious way of checking was wrong:

- **2.3** would have looked fine to anyone who checked "is there Indian data" instead of
  "is there Indian data *low down*" — and the honest answer changes which years are usable.
- **2.4** was written off twice as unobtainable. The blocker turned out to be **our own
  certificate store**, not the site, and the labels were free all along.
- **2.5** reads as 27.7% by transcript and 0.1% by file bytes. Both are wrong, in opposite
  directions. The real figure is 12.5%.

| Question | Answer | Effect |
|---|---|---|
| 2.1 Is Trino live? | **Yes, as of 23 Sep** | Archive open; bulk download started |
| 2.2 Target-state table? | **No — now verified directly** | ~~Selected altitude permanently out of scope~~ **Corrected 23 Sep:** out of scope *from OpenSky only*; available from adsb.lol — see the correction under 2.2 and plan item 9.0 |
| 2.3 Indian data, low down? | **Yes, from Jan 2025 onwards. Nothing before** | Phase 3 gets far more data, and only post-2025 is usable |
| 2.4 Speech labels? | **Not in the HF mirror — but the official release has them, free** | No hand-labelling needed; 786 callsign labels and 246 real aircraft identities |
| 2.5 Trained on its own test set? | **12.5% contaminated** | 762 clean clips remain; large-v3's 22.27 WER may not be quoted |
| 2.6 adsb.lol history, directly? *(added 24 Sep)* | **Last ~6 weeks reliably; older patchy** | Collector fetches daily per aircraft; backfill comes from the GitHub releases |

---

## 2.1 — Trino is live

**Answer (23 September): yes.** Permission was applied to the account and every probe now
passes:

```
2.1a authentication      : authenticated=True
2.1b trivial (no table)  : OK
2.1b metadata            : OK
2.1  -> QUERIES ALLOWED: True
```

Nothing in the script or the credentials changed — the same username and password that
were refused on 22 September are accepted on 23 September. That is the signature of a
permission flag being applied server-side, and it confirms the diagnosis below was right:
the problem was never anything we could fix from here.

**Measured query costs**, useful for planning anything that follows:

| Query | Cost |
|---|---|
| One hour, Mumbai box, all states | 3.7 s → 175,180 rows / 125 aircraft |
| One hour, below 10,000 ft near VABB | 5.7 s → 33,679 rows / 56 aircraft |
| One day, airborne, model-usable, every 10 s | ~11 s → 203,849 rows / 590 aircraft |
| One month of the Mumbai box | **refused** — of order 126 million rows |

That last row is a real constraint: **a month cannot be counted in one query.** Everything
below therefore samples rather than exhausts, and says so.

---

<details>
<summary><b>The original 22 September finding, kept for the trail</b></summary>

**Answer: access is not open to us.** The account exists and the password is correct — a
token comes back, valid for 7,200 seconds. Every query is then refused:

```
2.1b trivial (no table)  : PERMISSION_DENIED
2.1b metadata            : PERMISSION_DENIED
```

**The diagnosis is exact, and it rules out all three of the plan's suggested causes.** The
plan says to check username case, a missing partition filter, and the permission flag, in
that order. The first two are eliminated by the probe:

- The username is already lowercase.
- `SELECT 1` **touches no table and has no partition to filter**, and it is refused too.

So this is not a query we wrote wrongly. The account has no permission to execute anything
on Trino. Only OpenSky can change that.

**A distinction worth carrying, because it explains why the credentials we already had
were never going to work.** pyopensky authenticates Trino with `grant_type=password`
against the OpenSky **website account**, with `client_id` hardcoded to `"trino-client"`
([pyopensky/trino.py:104-116](../venv/Lib/site-packages/pyopensky/trino.py)). The three
`clientId`/`clientSecret` pairs in `secrets/opensky/` are **REST API credentials** for
state-vector polling and are a different thing entirely. Holding them says nothing about
archive access.

**What to do:** ask OpenSky to apply the Trino permission to this account. Everything else
is ready — `scripts/check_trino.py` runs 2.2 and 2.3 automatically the moment it is
granted, and the credentials are already in `settings.conf`.

</details>

## 2.2 — There is no target-state table, and this is permanent

**Answer: no — and as of 23 September this is verified directly** against the live server
rather than inferred from the client library. `SHOW TABLES` returns 14:

```
acas_data4            allcall_replies_data4  flarm_decoded       flarm_raw
flights_data4         flights_data5          identification_data4
operational_status_data4  position_data4     readsb_adsc_sv      readsb_mlat_sv
rollcall_replies_data4    state_vectors_data4  velocity_data4
```

**The near miss is the interesting part.** `operational_status_data4` carries a column
called `supportstargetstatereport`. That is a **capability flag**: it records *which
aircraft are able to broadcast* a Target State report. It does not record *what they
broadcast*. So the archive can tell you an aircraft could have told you its selected
altitude, and cannot tell you what that altitude was.

**The caveat that was here on 22 September is now discharged.** The table list was
originally read from pyopensky's schema definitions because `SHOW TABLES` was refused;
`verified_directly` is now `true`, and the live list confirms it. It also turned up three
tables the client library does not declare — `flarm_decoded`, `readsb_adsc_sv`,
`readsb_mlat_sv` — none of which carries a target state either.

**Consequence:** selected altitude stays permanently out of scope. This closes the open
item in `Claude outputs/Missing_Data_For_Trajectory_Prediction.md`, which listed it as
*"Unverified — test once Trino access arrives"* and called it possibly "the biggest
conflict-detection improvement available". It is not available. That is worth knowing now
rather than after building toward it.

It also retires the hope behind the rejected level-flight filter (7 September): that filter
failed precisely because we infer level flight from observed vertical rate instead of a
cleared level, and this confirms the archive cannot supply the cleared level either.

### Correction, 23 September 2026 — right about OpenSky, wrong as a general statement

**What stands.** Everything above is correct *about OpenSky*: its archive has no target-state
table, `supportstargetstatereport` is a capability flag and not the value, and that is why
the September level-flight filter could not be rescued from the OpenSky archive.

**What was wrong.** The conclusion "selected altitude stays permanently out of scope"
generalised from one source to all of them. Only OpenSky was checked. Other open ADS-B
networks decode the same broadcasts and keep the value. Checked directly on 23 September
2026:

| Check | Result |
|---|---|
| Live, `api.adsb.lol/v2/point/19.0887/72.8679/60` (60 NM of VABB) | **9 of 13** aircraft carry `nav_altitude_mcp` — **9 of 11 airborne**. Of the four without it, two are on the ground, one transmits ADS-B version 0 (which has no message for this value), one is a version 2 aircraft at 4,000 ft. Examples: AXB1340 36992, IGO5196 28000, AIC6CC 28000, AXB1671 3808, IGO6030 8000. Archit's earlier check the same day: 12 of 12 |
| History, `adsb.lol/data/traces/42/trace_full_801742.json` (VT-IWQ, A321neo) | 3,339 trace points covering 22 Sep 09:10 → 23 Sep 10:08 UTC. Element index 8 is a non-null object on **834** points, **781** of them with `nav_altitude_mcp`. It changes through each flight — IGO5323 on 22 Sep: 8992 → 16000 → 28000 → 32992 → 31008 → 26016 → 8992 → 7008 → 6016. A second file (`trace_full_80180e.json`, VT-NHB): 816 of 3,266 points, 792 with the field |
| Other fields in the same index-8 object | all present on most detailed points: `wd`, `ws`, `oat`, `tat`, `ias`, `tas`, `mach`, `roll`, `track_rate`, `nav_qnh` (e.g. 801742: wind on 604 of 834, temperature on 487) |
| [readsb README-json.md](https://github.com/wiedehopf/readsb/blob/dev/README-json.md) | defines `nav_altitude_mcp` as "selected altitude from the Mode Control Panel / Flight Control Unit (MCP/FCU) or equivalent equipment"; trace element 8 is "aircraft object with extra details or null" |
| [adsb.lol historical data](https://www.adsb.lol/docs/open-data/historical/) | dumped daily, published as GitHub releases (`adsblol/globe_history`), one JSON GZIP file per aircraft per day. Licence **ODbL 1.0** |

**Two limits worth knowing before building on it.** The detailed object is on roughly a
**quarter** of trace points, not every one, so the value is sampled more sparsely than
position. And the trace file fetched directly is a **rolling window of about 25 hours**,
spanning several flights by the same airframe — whether older days can be fetched the same
way is question 2.6 in the plan, still open. *(Answered 24 September — see 2.6 below:
the last ~six weeks, reliably.)*

**One nuance for the report.** The selected altitude is what the crew *dialled*, which is
normally but not always the level they were *cleared* to. EUROCONTROL's STCA Option E names
"Cleared and/or Selected Flight Level" for exactly that reason. A mis-set dial is itself a
level-bust cause, so this field narrows the gap the September filter fell into; it does not
close it.

**Status: reopened.** Selected altitude moves from "permanently unavailable" to "available
from adsb.lol, at a cost in download volume" and now sits in plan item **9.0**. The
original finding above is left as written, because having been wrong and caught it is part
of the record.

## 2.3 — Mumbai traffic goes back years. Low-altitude Mumbai traffic starts in January 2025.

**This is the most consequential finding in Phase 2, and it is exactly the split the plan
warned to look for.**

**Method.** 36 months, sampling the 15th of each month at 00, 08 and 16 UTC — three hours
per month, not the whole month, because a month cannot be queried (see 2.1). Test A counts
everything in the Mumbai box; Test B counts only states **below 10,000 ft and within 60 NM
of VABB**, which is the arrival and departure traffic that is our weakest prediction
regime. Both run in one query per month by conditional aggregation.

**Result.**

| | Months sampled | Months with data |
|---|---|---|
| **Test A** — anything in the Mumbai box | 36 | **29** |
| **Test B** — below 10,000 ft near VABB | 36 | **20** |

**Nine months have cruise traffic over Mumbai and exactly zero traffic near the airport:**

```
2023-10  2023-11  2023-12  2024-01  2024-02  2024-03  2024-05  2024-07
```

2024-03 is the cleanest illustration: **188,407 rows and 196 aircraft in the box, and 0
rows below 10,000 ft near VABB.** Not a thin result — a categorically empty one.

Then it switches on. January 2025 shows the onset (461 low rows, 4 aircraft), and from
February 2025 every sampled month is healthy — a median of **71,075 low rows and 128
distinct aircraft per three sampled hours**, against 303 aircraft in the box overall.

**What this means, in one sentence:** somebody put an ADS-B receiver near Mumbai at the
turn of 2025, and before that the archive can see aircraft passing over the region at
cruise but not the arrivals and departures we actually need.

**This is precisely the trap the plan described** — *"Test A can look healthy on cruise
traffic overflying the box while this is empty"* — and it is real. Anyone who had run only
Test A would have concluded the archive held three years of usable Mumbai data and built a
training set that was silently missing every arrival before 2025.

**This is publishable.** OpenSky's own 2025 coverage report describes South Asia as "still
improving" without quantifying it. As far as we can tell nobody has measured Indian
low-altitude coverage in the largest open ADS-B network, and this dates its arrival to
within a month.

### What it changes for the project

**Usable window: February 2025 to September 2026, about twenty months.** Only that window
may be used for anything involving arrivals or terminal traffic. Earlier months are not
merely sparse, they are absent, and mixing them in would quietly bias a dataset back
towards the easy en-route cruise case — the same bias the per-horizon mask exists to
prevent.

**The scale is the striking part.** Measured on 2026-03-15, one day of airborne
model-usable rows at 10-second sampling is **203,849 rows from 590 aircraft**. The entire
existing dataset, twelve days of polling across 35 sessions, is 627,344 states. So:

> **Three days of archive ≈ the whole collection effort to date.**

`scripts/download_archive.py` pulls this down in the poller's own schema. **Downloaded:**

| | |
|---|---|
| usable days | **38** (9 Feb 2025 → 20 Sep 2026) |
| total rows | **7,969,128** — **12.7× the existing dataset** |
| median per day | 209,569 rows from 792 aircraft |
| below 10,000 ft | **20.0%** of rows |
| on disk / time | 243 MB / 23 minutes |

One further day, 20 April 2026, returned 6 rows. That is not a downloader fault — it is the
same April 2026 gap the coverage sweep found independently, arriving by a second route.

**It writes to `ml_pipeline/data/archive/`, deliberately not `data/raw/`.**
`preprocess_sequences.py` globs `raw/*.parquet` and concatenates whatever it finds, so a
download dropped there would silently change the dataset underneath every number this
project has published. Adopting the archive is a separate, deliberate, logged step.

### The archive is worth more per row than the polled data, and the reason is structural

Tested by running the real `preprocess_sequences.py` against **three archive days alone**,
in an isolated data root so nothing real was touched:

| | Airborne states | Training samples | 10-min target valid |
|---|---|---|---|
| Entire existing dataset (35 sessions, 12 days) | 627,344 | 291,008 | **49.9%** |
| **Three archive days** | 642,945 | **568,867** | **61.2%** |

**Three days of archive produce nearly twice the training samples of the entire collection
effort, from a similar number of raw states.** That is not a rounding artefact — it is
structural, and the cause is measurable:

| | Wall-clock span | Median track length | Tracks ≥10 min |
|---|---|---|---|
| One archive day | 24.0 h | **180.8 min** | 89% |
| One polled session | 1.7 h | **19.1 min** | 72% |

**A 90-minute polling window can never observe more than 90 minutes of any aircraft**, and
most aircraft enter or leave part-way through, so tracks are truncated at both ends. A
training sample needs 10 past states *and* a future position at the target horizon, so
every truncated track costs samples — and costs them hardest at the ten-minute horizon,
which is exactly where the model is weakest and the data thinnest.

**This says something uncomfortable and useful about the last month of work:** the
collection strategy itself was capping the dataset, independently of how many days were
collected. More 90-minute sessions would have kept hitting the same ceiling. Continuous
history does not.

### A second door this opened

`flights_data4` turns out to carry `estdepartureairport`, `estarrivalairport` and the full
track per flight. On 2026-03-15 it holds **336 flights arriving at VABB**, tracks up to
2,400 points each. That is ground truth for destination — the "Route A" recorded as
pending in `Claude outputs/Missing_Data_For_Trajectory_Prediction.md` — and it is what
makes plan item **9.2** (how accurate are callsign-to-route lookups over India, a figure
nobody has published) measurable rather than aspirational. Not built; recorded as now
possible.

---

## 2.4 — The speech test set has no labels, but its ids carry more than expected

**Answer: no label columns.** `Jzuluaga/atco2_corpus_1h` is 871 rows, 59.2 minutes, six
columns:

```
id | audio | text | segment_start_time | segment_end_time | duration
```

None of `callsign`, `action` or `value`. No nearby-aircraft list. Exactly as the plan
predicted, now confirmed rather than assumed.

**What the plan did not know: every id parses, and carries real metadata.** All 871 of
them, in the form
`atco2_test-set-1h_<ICAO>_<position>_<frequency>MHz_<date>_<time>`:

| Airport | Clips | |
|---|---|---|
| LSGS | 258 | Sion, Switzerland |
| LSZB | 172 | Bern, Switzerland |
| LSZH | 126 | Zurich, Switzerland |
| LKPR | 102 | Prague, Czechia |
| **YSSY** | **102** | **Sydney, Australia** |
| LZIB | 79 | Bratislava, Slovakia |
| LKTB | 32 | Brno, Czechia |

**Two things follow.**

First, **the corpus is not purely European.** 102 clips — 11.7% — are Australian. The plan
states "The ATCO2 clips are European", and Phase 5 leans on that when arguing that Indian
accents are unrepresented. The argument survives (no South Asian audio at all), but the
premise needs correcting before anyone says "European" in a review.

Second, the ids give **93 distinct recordings** (airport + frequency + date). That is the
grouping Phase 6 needs for its callsign-list proxy: within one recording, the callsigns
appearing in neighbouring transmissions form a plausible stand-in for a surveillance list.
It has to be labelled plainly as a proxy, but it is now buildable without the official
annotations.

### The official annotations exist, are free, and remove the need to hand-label anything

**This was written off twice — by the plan and by me — and both times the reason was
wrong.** The plan says the annotations "live in the official release at `atco2.org/data`",
and on 22 September that page failed TLS certificate verification, so it was recorded as
unreachable. It is not. **The failure was our certificate store, not the site.** Retried
against `certifi`'s CA bundle instead of Windows' default, the page loads immediately and
links `atco2_1h_xml-tar.gz` — **50 KB, no registration, no login**.

Inside are **560 XML files, 877 annotated segments** — essentially one per clip — in this
form:

```xml
<segment>
  <start>0</start> <end>3.77</end>
  <speaker>A</speaker> <speaker_label>ATCO radar</speaker_label>
  <text>[#callsign]Oscar Kilo Papa Mike Bravo[/#callsign]
        [#command]descend[/#command]
        [#value]flight level one hundred[/#value]</text>
</segment>
```

That is exactly the `callsign | action | value` triple Phase 6 has to produce:

| Field | Segments | |
|---|---|---|
| callsign | **786** | 89.6% |
| command | 639 | 72.9% |
| value | 639 | 72.9% |
| **all three** | **497** | 56.7% |
| recordings matching the 871 HF clips | **509** | |

**And something better than the plan hoped for.** Each segment carries a `speaker_label`.
On the pilot side that is the **real aircraft identity** — `OK-PMB`, `RYR73AH`, `DLH8HR` —
for **246 segments**. Phase 6's actual contribution is matching a heard callsign to a real
aircraft, and this is ground truth for exactly that, rather than a proxy.

**One caveat, stated rather than glossed.** Every segment carries `correct_transcript=1`,
so the transcripts are verified. But `correct_tagging` is 1 on only **2 of 877** segments,
which most likely means the entity tagging was not separately human-verified. These should
be described as *the corpus authors' annotations*, not as doubly-verified gold labels. They
are still far better than 100–150 clips labelled by us, and they cover the whole set.

**Consequence: hand-labelling is off the Phase 6 critical path**, and the "state the sample
size" caveat that would have attached to every extraction number in Phase 8 goes with it.

## 2.5 — 12.5% of the test set is the same audio as the training data

**Answer: contaminated, but not fatally — and the honest number needed the right
measurement.**

`jlvdoorn/atco2-asr-atcosim` is **8,092 train + 2,026 validation rows and has no test
split**, confirming the plan's claim. That corpus is what
`whisper-large-v3-atco2-asr-atcosim` was fine-tuned on, so the question is whether the 871
evaluation clips are inside it.

**Three measurements, and only the third is right:**

| Method | Result | Why it is wrong |
|---|---|---|
| Matching transcripts | 241 of 871 — **27.7%** | **Overstates.** Short generic phrases recur across corpora by coincidence |
| Matching raw audio bytes | 1 of 871 — **0.1%** | **Understates.** Re-encoding changes every byte |
| **Matching decoded waveforms** | **109 of 871 — 12.5%** | **Correct.** Correlation 1.000 is literally the same recording |

The split by transcript length shows exactly why the naive method fails:

| Transcript length | Text-matched | Actually the same recording |
|---|---|---|
| 1–3 words | 10 | **0** |
| 4–5 words | 1 | **0** |
| 6–9 words | 28 | 1 |
| **10+ words** | **202** | **108 (53%)** |

Nothing short is a real match; half of everything long is. A pair like *"oscar kilo bravo
alfa lima request shortcut to vlasim if possible"* is not two people coincidentally saying
the same sentence.

**What this permits and forbids.**

- **Forbidden:** quoting the model card's **22.27 WER** as a held-out result, or reporting
  any large-v3 figure over the full 871 clips as though it were clean.
- **Permitted, and better than the plan's fallback:** the plan says that on high overlap
  *"medium-atcosim becomes your only held-out measurement"*. That is unnecessarily
  pessimistic. **762 clips are clean**, and the 109 contaminated ids are listed in the
  report JSON, so Phase 4 can simply exclude them and report a genuine held-out WER on the
  remainder — a stronger result than falling back to one model.
- **Required:** report both numbers, on the clean subset and on the full set, and say which
  is which.

---

## 2.6 — adsb.lol history can be fetched directly for the last six weeks, and not reliably before

**Measured 24 September 2026** by `python scripts/check_adsblol_history.py`
(report `ml_pipeline/reports/adsblol_history_20260924_232209.json`).

**The question.** The correction under 2.2 found the selected altitude in adsb.lol's
per-aircraft trace files. If past days can be fetched one aircraft at a time, the collector
never needs the ~2,115 GiB bulk archive. If not, it needs the daily GitHub releases.

**The answer.** Past days live at
`adsb.lol/globe_history/YYYY/MM/DD/traces/<last two hex digits>/trace_full_<hex>.json`.
Checked for two Indian A320-family airframes, VT-IWQ (`801742`) and VT-NHB (`80180e`):

| Period | Served? |
|---|---|
| **13 Aug 2026 → yesterday** | **Every day, both aircraft** — 42 of the last 60 days, and the switch-on date is identical for both |
| Feb → Jul 2026 | **Nothing** (404 for both, 18 sampled days) |
| Dec 2025 | **Refused** (403 for both) |
| Dec 2024 → Sep 2025 | **Partly** — VT-IWQ 15 of 21 sampled days; VT-NHB only from Sep 2025, likely because it had not yet been delivered |

Served days carry the selected altitude on roughly a quarter of points, as found under 2.2
(e.g. VT-IWQ 1 Sep 2026: 1,773 points, 419 with `nav_altitude_mcp`; 15 Mar 2025: 1,282
and 305).

**What it means.** The **recent ~six weeks form a rolling window** that can be relied on.
Anything older is patchy with an unexplained gap, so it cannot be relied on. The plan's
Phase 9.0 therefore takes this shape:

- **Going forward:** a daily collector fetches each Mumbai aircraft's file within the window.
  No bulk download is needed, as long as it runs at least once every six weeks.
- **Backfill:** the daily GitHub releases (`adsblol/globe_history`), not direct fetches.
- **Still needed either way:** a list of which aircraft were near Mumbai on each day. The
  per-aircraft path cannot discover it. The OpenSky archive can (2.1), or adsb.lol's live
  `point` endpoint for the collector going forward.

**Caveat:** two airframes, sampled days. The window's start date matching exactly on both
suggests a server-side retention rule, but its exact length should be re-checked before
depending on it.

---

## What this changes in later phases

| Phase | Adjustment |
|---|---|
| **3** | **Materially changed.** The archive supplies roughly 12× the current data, with real terminal traffic (26.7% of downloaded rows are below 10,000 ft). Train on the existing 35 sessions **first**, as the comparable baseline, then on the enlarged set as a **separate ablation row** — never silently merged. Restrict to **Feb 2025 onward**. |
| **4** | Evaluate large-v3 on the **762 clean clips**, not 871. Report the full-set figure beside it, labelled contaminated. `medium-atcosim` remains a genuine cross-corpus measurement. |
| **5** | Correct "the ATCO2 clips are European" to "European and Australian". The absence of South Asian audio is unaffected and is still the argument for recording Mumbai phraseology. |
| **6** | **Hand-labelling dropped.** Score against the official annotations (786 callsign, 639 command/value, 497 complete). Use the 246 pilot `speaker_label` identities as ground truth for callsign matching, with the 93 recording ids as the candidate-list proxy. Describe them as the corpus authors' annotations, not doubly-verified gold. |
| **8** | The "+ more data" ablation row is now live rather than conditional. Three new honest-claims entries: measured contamination in a public ATC speech benchmark, the archive's lack of any selected-altitude table, and **measured Indian low-altitude ADS-B coverage including the date it begins**. |
| **9.1** | Runway in use becomes tractable — `flights_data4` carries full tracks for 336 VABB arrivals a day. |
| **9.2** | Indian route-lookup accuracy becomes **measurable**: `estarrivalairport` is the ground truth that was missing. |
| **9.4** | Aircraft type still needs an external database; the archive does not carry it. |
| **9.x** | Selected-altitude decoding moves from "unverified" to **permanently out**, with the evidence. |

## Two things worth publishing

**Indian low-altitude ADS-B coverage, dated.** Nine sampled months in 2023–24 carry cruise
traffic over Mumbai and **zero** states below 10,000 ft near the airport; from January 2025
onward every sampled month is healthy. OpenSky's own coverage reporting calls South Asia
"still improving" without quantifying it, and this puts a date on it. It is also a
cautionary result in its own right: a study using only a bounding box would have concluded
the data was there.

**The contamination measurement is a result in its own right.** `whisper-large-v3-atco2-asr-atcosim`
is a publicly downloaded ATC speech model whose card reports a WER without naming its
evaluation set, and 12.5% of the obvious public test set for it is inside its own training
data. Nobody appears to have checked. The method is three lines of waveform correlation and
the finding is reproducible from `ml_pipeline/voice/check_corpora.py`.
