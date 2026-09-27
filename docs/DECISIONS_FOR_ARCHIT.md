# Waiting on you

Everything below was measured and then stopped at the point where the project's rules say a
person decides. Each item says what the choice is, the numbers behind it, and where the
evidence is. Last updated 26 September 2026.

---

## Decided on 26 September (kept here so the trail is readable)

- **Dialled altitude in the conflict classifier — SERVED**, at the same false-alarm rate as before
  ("build it, same alarm rate"). Headline 94.0% → **95.1%** (270 of 284); four seeds give 269–271.
  GATE 1 (95% recall) now passes. Cost: 4 more false audible alarms on test (17 → 21). Live feed:
  adsb.lol, ODbL 1.0 (credited in `/api/health`). Evidence: `classifier_intent_seeds_20260926_172128.json`.
- **The "more data" trajectory model — SERVED** ("switch to newer model"). Arrivals, one of five paths
  within 5 NM: 71.5% → 75.4%. Cost accepted: one real audible alarm demoted on the validation pairs.
- **Heard-clearance confidence floor — 0.85** ("good for numbers and good for safety"). On real radio it
  applied 12 of 20 correct clearances and no wrong ones (24 heard clearances; small sample).
- **GATE 1 (open since 5 September) — closed** by the item above, not by moving the threshold.

## Decisions still yours

**1. Which speech model the running system uses — DECIDED 27 Sep: our own.** Comparison finished
(`ml_pipeline/reports/voice_eval_20260927_015420.json`); you chose "whichever is better overall". Ours
gets 20 of 31 held-out ATCO2 clearances completely right against 11 for the best published model,
15.1% word error on unseen Czech radio against 46.9%, and is ~3.5x faster. It is now the default in
`server/app/config.py` whenever its directory exists.

**2. Destination in the trajectory model — DONE 27 Sep (you: "if adding destination gets us benefit then
do that").** Rebuilt and retrained; it passed all 11 checks written before training
(`ml_pipeline/reports/destination_row_20260927_023146.json`) and is now served. Ten-minute height error
1,051 -> 889 ft; arrivals best-of-5 75.4 -> 76.5; no real alarm lost; one fewer false loud alarm on test.
The previous model is kept as `trajectory_multipath_20260926_archive_backup.pkl` if you want it back.

**3. The collapsed "low-confidence" group hides 7 real conflicts (issue H5).** Unchanged. All seven
still have more than three minutes of warning. Requiring both models to agree before collapsing
(option B1) cuts that to 3, at the cost of 50 more false rows on the main list (test split). Evidence:
`docs/ISSUES.md` H5, `ml_pipeline/reports/alert_prominence_20260924_193159.json`.

**4. Other trades measured and not adopted**, in case you want a different balance:
- Letting the model's paths add to the safety net: 271 of 284 caught instead of 269, for +18.3
  false alarms per 1,000 (`offsets_ab_20260924_181140.json`, measured before the 26 Sep models).
- Tier-1 promotion only from a conflicting path (idea A): 3 fewer false loud alarms on test, but one
  real conflict loses its loud alarm.
- The dialled-altitude classifier at the old recall-floor threshold instead: 94.0% caught at only
  76.1 false alarms per 1,000 (you chose "same alarm rate" instead). Numbers in `docs/metrics.json`,
  `model2.recall_margin_what_if`.

## Things only a person can do

**5. Accept two licences on Hugging Face** (account AS0711): `ai4bharat/indic-parler-tts` (the
Indian-accented voices, Apache 2.0) and `ai4bharat/Svarah` (real Indian English for testing, CC BY 4.0,
asks for contact details). Until then there is no Indian-accent training step and no Indian-voice score.

**6. Listen to 20 generated clips** once item 5 is done (`synthesize.py --listen 20` writes them).
Fifteen minutes. If the voices sound wrong for radio calls, everything built on them is wasted.

**7. Check the runway detector by eye (plan 9.1).** Open `docs/figures/runway_spotcheck.png`
and confirm each red line lies on the runway it is labelled with.

**8. Real Mumbai recordings (plan Phase 5)** are still the only way to get a speech figure on real
Indian ATC phraseology. The synthetic voices can train the model; they can never be its test.
