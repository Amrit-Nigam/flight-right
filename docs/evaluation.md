# Flight Right: latest evaluation

Classifier headline: **95.07% (270/284)** caught with at least three minutes of warning. Full served alert chain: **95.42% (271/284)**. Trajectory/conflict figures retain their recorded measurement dates. Speech was tested November 10 and configured as the default November 11. No new benchmark was run for this summary refresh.

## Model inventory and best supported configuration

Best means the recorded validation-selected configuration that passed its stated checks, not the largest isolated test score. Served and candidate numbers are separated below. Different tasks, corpora and metrics cannot be ranked together.

| Model / evaluated component | Status / how achieved |
| --- | --- |
| [Residual LSTM (Model 1)](evaluations/trajectory_lstm.md) | Served baseline; selected ten-minute-head candidate remains undeployed |
| [Constant velocity](evaluations/constant_velocity.md) | Deterministic trajectory baseline, not a learned model. |
| [Tree trajectory reference](evaluations/tree_reference.md) | Benchmark only. Saved test predictions survive; fitted estimators are not retained. |
| [Multi-path trajectory bundle (Model 1b)](evaluations/multipath.md) | Archive + destination served; continue_800 candidate undeployed |
| [XGBoost conflict classifier (Model 2)](evaluations/conflict_classifier.md) | 27-input selected-altitude classifier served; raw threshold 0.07465646415948868 |
| [Secondary XGBoost conflict filter](evaluations/conflict_filter.md) | refit_unweighted + raw threshold 0.07932812720537186 + veto floor 0.00928506813943386; undeployed |
| [Resolution engine (Model 3)](evaluations/resolution.md) | Deterministic simulation and ranking engine; a learned resolution ranker is deferred and has no trained model or scores. |
| [Full alert chain](evaluations/full_alert_chain.md) | Integration evaluation, not another trained model. Keep separate from classifier-only scores. |
| [Path-confidence experiment](evaluations/path_confidence.md) | Rejected/rolled-back all-pairs shadow-policy experiment; no deployed model. |
| [Alert feed](evaluations/alert_feed.md) | Deterministic notification suppression; measures interruptions, not conflict prediction accuracy. |
| [Clearance and callsign extraction](evaluations/clearance_extractor.md) | Deterministic parser/matcher, human-transcript upper bound, clearance-chain and oracle demonstrations; not an ASR model. |
| [openai/whisper-small](evaluations/asr_small.md) | Untouched speech baseline. |
| [FlightRight Whisper-small ATC](evaluations/asr_small_atc_p1.md) | uniform_soup3 configured default; equal average of P1 and two independent continuations, selected using real validation recordings before test |
| [openai/whisper-medium](evaluations/asr_medium.md) | Untouched speech comparator. |
| [jlvdoorn/whisper-medium-atcosim](evaluations/asr_medium_atcosim.md) | Published ATC comparator; ATCOSIM is training-contaminated. |
| [jlvdoorn/whisper-large-v3-atco2-asr-atcosim](evaluations/asr_large_atc.md) | Published ATC comparator. ATCO2 recording overlap and ATCOSIM training contamination must stay attached to its scores. |
| [ai4bharat/indic-parler-tts](evaluations/indic_parler_tts.md) | Synthetic voice generation for training/demo; no objective TTS quality benchmark found. Script extraction recovery is not TTS accuracy. |
| [Silero VAD (faster-whisper)](evaluations/silero_vad.md) | Pretrained speech gate used in the live speech service. No labelled VAD evaluation or fine-tuning found. |

## Trajectory: historical test split

39,614 test windows; ten-minute targets available for 18,662. Rates are percentages. RMSE/mean are horizontal NM, altitude MAE is ft. Earlier horizons and every slice/seed remain in the corresponding model ledger.

| Configuration | Horizon | n | Mean NM | RMSE NM | Within 5 NM % | Altitude MAE ft |
| --- | --- | --- | --- | --- | --- | --- |
| Constant velocity | 1 min | 38110 | 0.49242 | 1.76901 | 98.42561 | 119.94 |
| Constant velocity | 3 min | 32324 | 1.68810 | 3.68365 | 89.46294 | 471.34 |
| Constant velocity | 5 min | 27587 | 3.65366 | 7.16213 | 77.32990 | 910.53 |
| Constant velocity | 10 min | 18662 | 10.30497 | 16.86169 | 50.50370 | 2231.10 |
| Tree reference (saved predictions) | 1 min | 38110 | 0.43230 | 1.70491 | 98.46497 | 94.84 |
| Tree reference (saved predictions) | 3 min | 32324 | 1.27093 | 2.96305 | 92.62777 | 294.72 |
| Tree reference (saved predictions) | 5 min | 27587 | 2.39033 | 5.01676 | 85.08355 | 511.70 |
| Tree reference (saved predictions) | 10 min | 18662 | 5.56803 | 9.51012 | 65.66284 | 1079.97 |
| Undeployed last_head_adam_lr1e4, seed 42, epoch 4 | 1 min | 38110 | 0.45025 | 1.73104 | 98.46497 | 98.63 |
| Undeployed last_head_adam_lr1e4, seed 42, epoch 4 | 3 min | 32324 | 1.37553 | 3.10388 | 91.95953 | 304.26 |
| Undeployed last_head_adam_lr1e4, seed 42, epoch 4 | 5 min | 27587 | 2.68786 | 5.37192 | 82.90499 | 509.58 |
| Undeployed last_head_adam_lr1e4, seed 42, epoch 4 | 10 min | 18662 | 6.34813 | 10.39758 | 61.38678 | 1103.95 |

The LSTM candidate freezes the encoder, shared layers and one-/three-/five-minute heads; Adam learning rate 1e-4, SmoothL1 beta .05, validation-selected seed 42 epoch 4, confirmed at seeds 43/44. It is not a simultaneous improvement of every metric or regime. See all three LSTM studies and guards in its ledger.

## Multi-path: ten-minute coverage

Best-of-five is coverage of alternatives. A joint 3-D hit requires the same candidate within 5 NM and 1,000 ft. Arrivals is the existing <40 NM VABB bucket, not independent arrival labels.

| Configuration | Group | n | Top-1 mean NM | Top-1 5 NM % | Best-5 5 NM % | Top-1 3-D % | Best-5 3-D % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Undeployed continue_800 seed 0 | all | 18662 | 5.49463 | 68.26707 | 88.64538 | 56.02829 | 68.31529 |
| Undeployed continue_800 seed 0 | arrivals | 2923 | 9.89244 | 47.51967 | 76.90729 | 34.65618 | 49.02497 |

continue_800 extends only the ten-minute per-mode regressors: 800 along-track / 800 cross-track / 468 altitude trees. Validation-frozen, seed 0; no independent multi-seed claim. Route classifier and temperature stay fixed. Route classification and its full 40-class confusion matrix/calibration are preserved in the multi-path ledger.

## Conflict: 4,690 historical test pairs, 303 positives

| Decision | Precision | Recall | F1 | TN | FP | FN | TP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Served classifier | 0.38584780 | 0.95379538 | 0.54942966 | 3927 | 460 | 14 | 289 |
| Served full chain | 0.37760417 | 0.95709571 | 0.54154995 | 3909 | 478 | 13 | 290 |
| Undeployed filtered classifier | 0.39643347 | 0.95379538 | 0.56007752 | 3947 | 440 | 14 | 289 |
| Undeployed filtered full chain | 0.38718291 | 0.95709571 | 0.55133080 | 3928 | 459 | 13 | 290 |

The served classifier adds selected-altitude inputs with validation threshold matched to the prior false-alarm rate. The refined proposal uses a new unweighted 400-tree depth-3 XGBoost filter (learning rate .04, minimum child weight 20, L2 20, subsample .9, seed 42) after the threshold change; the independent straight-line safety net bypasses it. Classifier early catches remain 270/284; full-chain early catches remain 271/284. The proposal retains the same detected true pairs, with 459 full-chain false positives, 19 false tier-1 alerts and 28 real tier-1 alerts. Existing full-chain FN remain 13. This is repeated historical-benchmark exploration, not a guarantee on future traffic.

## Speech: latest accepted result per checkpoint and corpus

WER is percent; lower is better. Columns distinguish raw and spoken-numeral-normalized WER. Corpus contamination limits comparison. Latest here means the latest accepted record for that model/corpus, even when another model has a more recent report. Superseded checkpoints of our model appear only in its history; scores are not cherry-picked per corpus.

| Checkpoint | Status | Corpus | Measured / re-scored | Clips | WER % | Spoken-numeral WER % | Basis / limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| jlvdoorn/whisper-large-v3-atco2-asr-atcosim | reference | atco2_clean | 2026-10-30 (cached re-score) | 762 | 25.88 | 25.87 | clip-held-out (same airports and days as its ATCO2 training clips) |
| jlvdoorn/whisper-large-v3-atco2-asr-atcosim | reference | atco2_contaminated | 2026-10-30 (cached re-score) | 109 | 15.95 | 15.95 | NOT held out: these exact recordings are in its training data (Phase 2.5) |
| jlvdoorn/whisper-large-v3-atco2-asr-atcosim | reference | atcosim_heldout_speakers | 2026-10-30 (cached re-score) | 1712 | 14.69 | 14.69 | NOT held out: trained on all ten ATCOSIM speakers |
| jlvdoorn/whisper-large-v3-atco2-asr-atcosim | reference | uwb_heldout_recordings | 2026-10-30 (cached re-score) | 2814 | 46.94 | 46.94 | held out (UWB-ATCC not in its training corpus) |
| openai/whisper-medium | reference | atco2_clean | 2026-09-26 | 762 | 62.55 | 44.72 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-medium | reference | atco2_contaminated | 2026-09-26 | 109 | 47.8 | 31.26 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-medium | reference | atcosim_heldout_speakers | 2026-09-26 | 1712 | 61.87 | 24.03 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-medium | reference | uwb_heldout_recordings | 2026-09-26 | 2814 | 78.23 | 58.43 | held out as far as is known (web-scale training data, undisclosed) |
| jlvdoorn/whisper-medium-atcosim | reference | atco2_clean | 2026-09-26 | 762 | 39.51 | 39.51 | held out (never trained on ATCO2) |
| jlvdoorn/whisper-medium-atcosim | reference | atco2_contaminated | 2026-09-26 | 109 | 26.45 | 26.51 | held out (never trained on ATCO2) |
| jlvdoorn/whisper-medium-atcosim | reference | atcosim_heldout_speakers | 2026-09-26 | 1712 | 0.14 | 0.14 | NOT held out: trained on ATCOSIM |
| jlvdoorn/whisper-medium-atcosim | reference | uwb_heldout_recordings | 2026-09-26 | 2814 | 53.04 | 53.05 | held out |
| openai/whisper-small | reference | atco2_clean | 2026-10-30 (cached re-score) | 762 | 75.2 | 59.18 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-small | reference | atco2_contaminated | 2026-10-30 (cached re-score) | 109 | 53.19 | 37.18 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-small | reference | atcosim_heldout_speakers | 2026-10-30 (cached re-score) | 1712 | 65.95 | 27.54 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-small | reference | svarah_indian_english | 2026-10-30 (cached re-score) | 6656 | 9.3 | 8.47 | held out as far as is known (web-scale training data, undisclosed) |
| openai/whisper-small | reference | uwb_heldout_recordings | 2026-10-30 (cached re-score) | 2814 | 91.02 | 73.88 | held out as far as is known (web-scale training data, undisclosed) |
| uniform_soup3 | served default | atco2_clean | 2026-11-10 | 762 | 27.95 | 27.95 | held out (no ATCO2 audio in training) |
| uniform_soup3 | served default | atco2_contaminated | 2026-11-10 | 109 | 17.34 | 17.34 | held out (no ATCO2 audio in training) |
| uniform_soup3 | served default | atcosim_heldout_speakers | 2026-11-10 | 1712 | 4.8 | 4.8 | held out by speaker (sm3, zf3, gm2 never trained on) |
| uniform_soup3 | served default | svarah_indian_english | 2026-11-10 | 6656 | 31.46 | 27.22 | held out |
| uniform_soup3 | served default | uwb_heldout_recordings | 2026-11-10 | 2814 | 15.33 | 15.33 | held out by recording |

Current speech default: uniform_soup3, an equal weight average of original P1 and two independent 300-update continuations. Selected on 1,632 real validation clips before test; one checkpoint supplies every reported score for our model. Complete instructions on ATCO2 clean: 21/31 (67.74%). Generated-voice diagnostic: 16.60% WER on 416 held-out generated calls; this does not measure real Indian controllers. Effects are small and uncertain, with a UWB regression documented in the model history. The actual GPU speech service loaded the model and reproduced two validation transcripts; no persistent backend was restarted. All previous checkpoints, baseline scores, rejected trials and uncertainty estimates remain in the speech ledger. Svarah measures general Indian English, not ATC. Cached transcription re-scoring does not constitute fresh latency benchmarking.

## Other evaluated components

Resolution: 45 classifier-triggered tier-1 encounters (27 real / 18 false), 1,170 simulated manoeuvres; 1 unsafe and 923 ineffective rejected, 0 secondary-conflict rejections; 46 instructions across 21 encounters, 24 without options. 35 instructions on real conflicts, 11 on false alarms. The harness lacks surrounding traffic; zero secondary rejections does not validate runtime domino checks. Classification F1 is inapplicable.

Extractor with human transcripts on ATCO2 clean: 77.42% clearance accuracy (31 eligible), 93.9% callsign accuracy with proxy aircraft lists (328 eligible). These are upper-bound parser results, not ASR scores. The rejected number rule is excluded from latest accepted results. Latest November 2 chain check is an oracle-text replay demonstration, not measured microphone/ASR accuracy.

Alert feed: replay interruptions 680 to 179 (73.7%) and 909 to 235 (74.1%), zero pairs lost in both. This measures display suppression. Path-confidence all-pairs policy was rolled back; its trials, replay and source remain in its ledger. Indic Parler TTS and Silero VAD have no recorded objective model-quality evaluation; no numbers are invented for them.

## Provenance and maintenance

Original non-speech served-model refresh: 2026-10-30. Trajectory/conflict candidate studies: 2026-11-01. Latest chain demonstration: 2026-11-02. Initial consolidation: 2026-11-09. Speech tuning/test: 2026-11-10; latest speech model activated 2026-11-11.

[Source inventory and cleanup audit](evaluations/source_inventory.json) contains evidence ownership, checksums, preservation and cleanup status. Each model ledger includes original evidence. Model fingerprints are checked; consolidation does not make old measurements newly measured results.

```powershell
venv\Scripts\python.exe scripts/consolidate_evaluations.py --verify
# Add a newly generated evaluation (choose all affected model keys from the inventory):
venv\Scripts\python.exe scripts/consolidate_evaluations.py --ingest PATH --models MODEL_KEY
# Restore archived inputs needed by an older report script (does not overwrite):
venv\Scripts\python.exe scripts/consolidate_evaluations.py --restore ORIGINAL_PATH
```

When ingesting new work, update the latest-result selection in `refresh()` for newly selected configurations. The summary shows the validation-selected speech checkpoint across all corpora; previous checkpoints remain in its model ledger. Never promote a candidate by maximizing its historical test score.
