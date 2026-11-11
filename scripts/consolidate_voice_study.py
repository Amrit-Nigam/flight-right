"""Preserve the November speech study in its existing ledger; delete only its verified reports.

--prepare captures evidence and publishes the canonical pages, without deleting files.
--delete-reports verifies every byte first, then performs the user's explicitly requested cleanup.
No weights, datasets or unrelated reports are removed. No commit/push is performed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import consolidate_evaluations as maintenance

KEY = "asr_small_atc_p1"
STUDY = "voice_continuation_20261110"
REPORT = ROOT / "ml_pipeline/reports/voice_tuning_20261110"
WORK = ROOT / "checkpoints/voice_20261110"
LEDGER = ROOT / "docs/evaluations/asr_small_atc_p1.md"
EXTRAS = [ROOT / p for p in (
    "ml_pipeline/reports/voice_continue_20261110.log",
    "ml_pipeline/reports/voice_train_continue_lr1e4.json",
    "ml_pipeline/reports/voice_train_indian_mix_lr5e5.json",
    "docs/experiments/voice_tuning_20261110.md",
    "docs/evaluations/asr_small_atc_20261110.md",
)]


def load(name):
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def relative(path):
    path = path.resolve()
    assert path.is_relative_to(ROOT.resolve()), path
    return path.relative_to(ROOT.resolve()).as_posix()


def narrative(data, deployment):
    selection, test = data["selection"], data["test"]
    old, new = test["baseline"]["corpora"], test["selected"]["corpora"]
    lines = ["## November 2026 continuation: current served model and complete experiment", "",
        "**Current default: uniform_soup3, activated on 11 November at the user's explicit request.** "
        "This is the validation-selected combined model. Independent test results are mixed; activation "
        "does not turn the UWB regression into an improvement. Original P1 weights remain available as fallback. "
        "The prediction target, text normalizer, decoder and alert thresholds are unchanged.", "",
        "The purpose was to improve speech-to-text using existing recorded speech and previously unused "
        "Indian-accent generated practice calls. Two independent continuations start from the original best "
        "P1 adapter, not from each other. A third candidate averages the full weights of the original and "
        "both continuations equally. Identical tensors stay bit-exact; tied weights remain tied. "
        "All three source weight hashes were verified unchanged before/after averaging (287 tensors "
        "preserved, 192 averaged). The average is one ordinary Whisper model, not an inference ensemble.", "",
        "### How the data and comparisons were kept fair", "",
        "Base: openai/whisper-small; original adapter: local voice cache runs/p1_main/best_adapter. "
        "Exact base/adapter identities, original manifest hashes and synthetic-manifest hashes are in "
        "the protocol evidence. The exact pre-change training/source files were preserved under the "
        "archived source_at_training paths; the source snapshot pins their SHA-256 values.", "",
        maintenance.table(["Corpus", "Split", "Clips", "Hours"],
            [[r["corpus"], r["split"], r["clips"], r["hours"]] for r in data["inventory"]]), "",
        "ATCOSIM is human speech in simulation: train sm1/sm2/sm4/zf1/zf2, validation gm1/gf1, "
        "test sm3/zf3/gm2. UWB keeps published recording-disjoint test data, drops the overlapping "
        "recording, and chooses validation recordings by the existing SHA-1 modulo-10 rule. Speaker "
        "identities are unavailable for UWB. No ATCO2 audio is used for training; 559 mirror clips remain "
        "excluded. ATCO2 test has 762 primary clean clips and 109 clips contaminated for another published "
        "comparator, not for this model. Both subsets remain reported. Svarah is test-only ordinary "
        "Indian English, not aviation radio; accent and vocabulary are confounded.", "",
        "Generated practice validation has 416 calls, separate aircraft identities and three held-out "
        "generated voices (Ravi, Riya, Vikas). Noise comes only from UWB training audio. This is not "
        "real Indian controller speech. Training has 3,341 generated calls. The audio audit checked "
        "34,944 usable decoded waveforms: all distinct, no exact cross-split duplicates, valid bounds "
        "and durations. It does not exclude all possible near-duplicates or shared unknown speakers. "
        "All 22,891 training/validation targets fit: maximum 49 tokens, zero over the trainer limit.", "",
        "### Every training trial and checkpoint", "",
        "Both use seed 42, LoRA rank 32/alpha 64/dropout .05 on q/k/v/out and fc1/fc2 projections "
        "(12,976,128 trainable parameters), FP16 autocast, gradient checkpointing, AdamW weight decay .01, "
        "gradient clipping 1.0, batch 8 accumulated twice (effective batch 16), warmup 30, at most "
        "300 optimizer updates, evaluation every 100 and patience 3. A new optimizer/schedule is used "
        "for each continuation; this is initialization from P1, not a resumed legacy optimizer. "
        "The starting checkpoint stays eligible. Checkpoint selection uses the mean of the two "
        "recorded-speech validation WERs; generated speech never chooses a checkpoint. "
        "Training monitoring uses a fixed seed-42 sample of 200 clips per corpus and greedy GPU decoding; "
        "these numbers are distinct from the full production-decoder validation/test scores.", ""]
    trials = []
    checkpoints = []
    for name, state in data["training"].items():
        args = state["args"]
        trials.append([name, state["stage"], args["lr"], state["step"], state["best"]["step"],
                       json.dumps(state["train_clips"], sort_keys=True),
                       json.dumps(state.get("weighted_epoch_clips", state["train_clips"]), sort_keys=True)])
        for event in state["evals"]:
            score = event["wer"]
            checkpoints.append([name, event["step"], score["atcosim"], score["uwb"],
                                score.get("tts_indian", "not applicable"), score["mean"], event["utc"]])
    lines += [maintenance.table(["Trial", "Stage", "LR", "Updates completed", "Best update", "Available train pool", "Weighted epoch pool"], trials), "",
        "P1 uses all recorded ATCOSIM/UWB data in the epoch pool. P2 uses all generated data and 25% "
        "of each recorded corpus per epoch, then stops after the stated 300 updates. Available pool "
        "size is not a claim that every item was consumed in this short continuation. P2 update 100 "
        "was retained: later generated-speech gains worsened recorded-speech validation.", "",
        maintenance.table(["Trial", "Update", "ATCOSIM WER %", "UWB WER %", "Generated WER %", "Real-corpus mean %", "Measured UTC"], checkpoints), "",
        "### Validation selection, before final-test inference", "",
        "Export each candidate to CTranslate2 int8_float16. On all 1,632 recorded validation clips "
        "(516 ATCOSIM and 1,116 UWB), use identical English transcribe, beam 5, temperature 0, "
        "no timestamps, no prior-text conditioning and no VAD (`fw1-beam5-v1`). Choose the lowest "
        "equal-corpus mean WER, allowing at most 0.5 percentage points regression per real corpus; "
        "the original stays eligible. Generated voices and final-test scores do not select the winner.", "",
        maintenance.table(["Configuration", "ATCOSIM validation WER %", "UWB validation WER %", "Outcome"],
            [[name, score["atcosim"], score["uwb"], "selected" if name == selection["winner"] else "unselected"]
             for name, score in selection["validation"].items()]), "",
        "The uniform average was a documented validation-only amendment after the real-only continuation "
        "failed to beat the original on full validation and P2 showed forgetting. The selection rule "
        "stayed fixed. The coordinator restarted with 100 P2 validation clips cached; training and "
        "exports were already complete, no progress was lost, and no selection/test report existed. "
        f"Final choice frozen at {selection['frozen_utc']}. Only that winner received new full test inference.", "",
        "### Final test: measurements from 10 November, activation on 11 November", "",
        "WER counts substitutions, deletions and insertions per 100 reference words; lower is better, "
        "and it is not sentence accuracy. Do not combine corpora into one accuracy number. "
        "The selected model freshly transcribed 12,053 test clips. Original-model predictions were "
        "cached and re-scored using the same current normalizer/extractor, not newly inferred in full. "
        "Fresh original-model controls on 64 clips in each of four corpora (256 total, seed 42) "
        "matched cached normalized text and log-probability exactly. Timing includes cached and "
        "concurrent-load observations; it is not a new isolated latency benchmark.", ""]
    lines += [maintenance.table(["Corpus", "Clips", "Original WER %", "Current WER %", "Original numeral-normalized %", "Current numeral-normalized %"],
        [[key, new[key]["clips"], old[key]["wer"], new[key]["wer"], old[key].get("wer_numerals_spoken"),
          new[key].get("wer_numerals_spoken")] for key in new]), "",
        "Complete callsign + action + value instructions on ATCO2 clean: **20/31 (64.52%) -> "
        "21/31 (67.74%)**. Plausible-tag subset: 19/24 -> 20/24. The small, imperfectly tagged "
        "instruction subset is not a certification or a measured end-to-end runtime alert gain. "
        "Callsign matching uses the same proxy list from annotated airport/frequency/day for both models, "
        "not a prompt to the recognizer. All action, value, callsign, extraction-agreement and per-first-language "
        "results remain verbatim in the test evidence. No accuracy is invented for unselected models' tests: not run.", "",
        "Generated-voice development diagnostic, after selection froze: 416 held-out generated calls, "
        "same runtime decoder, original WER **24.62%**, selected **16.60%**. This does not measure "
        "real Indian controllers. No real Indian radio benchmark was available/used in this study.", "",
        "### Uncertainty, rejected work and implementation checks", "",
        maintenance.table(["Corpus", "Clusters", "Word-error change, percentage points", "Paired cluster 95% interval"],
            [[name, r["clusters"], r["word_error_change_percentage_points"], r["paired_cluster_95_percent_interval"]]
             for name, r in data["uncertainty"]["cohorts"].items()]), "",
        "Paired cluster percentile bootstrap: 2,000 resamples, seed 42, recording clusters for "
        "ATCO2/UWB and speaker clusters for ATCOSIM. Negative changes mean fewer errors. ATCOSIM "
        "has only three test speakers. No speaker-level Svarah interval is claimed because IDs are absent. "
        "The ATCO2/UWB intervals include zero; these small effects are uncertain. The historical test "
        "has been inspected in earlier work, so this is retrospective exploratory evidence, not a fresh blind benchmark.", "",
        "Unselected/rejected work is retained: real-only continuation; accent continuation and its later "
        "worse checkpoints; four-worker speed probe (290 matching transcripts/confidences but no "
        "consistent speed gain); initial batch probe with a feature-cropping error; corrected batch "
        "probe with 14/128, 13/128 and 14/128 transcript differences. Neither speed variant was adopted. "
        "The batch findings describe our experimental code, not a library defect. Official scores "
        "always use the unchanged sequential production decoder.", "",
        "Trainer repairs: final partial gradient groups are processed/scaled, exact data cursor and "
        "random/scaler state are saved, legacy non-exact resumes are refused, loading failures propagate, "
        "initial weights stay eligible, synthetic WER does not select real-radio checkpoints, and "
        "existing runs/exports are not silently overwritten. Export supports isolated output paths; "
        "runtime loading accepts an already converted complete folder. All 90 pre-activation Python "
        "tests passed, including nine focused training/selection/averaging checks. Today's activation "
        "check loaded the actual configured SpeechService and reproduced evaluated ATCOSIM/UWB transcripts.", "",
        "Hardware/software: " + json.dumps(data["environment"], sort_keys=True) + ".", "",
        "### Current deployment, artifact identity and reproduction", "",
        f"Runtime folder: `{deployment['runtime_model']}`. Full-precision export and useful original/"
        "continuation adapters/models remain under `checkpoints/voice_20261110/`; original data, "
        "P1 fallback and validation/test prediction caches are retained. The user authorized latest-model "
        "activation despite mixed test results. The app defaults to this runtime folder when complete; "
        "explicit FLIGHT_RIGHT_ASR_MODEL_ID overrides remain supported. No confidence/alert thresholds, "
        "trajectory weights or conflict-classifier weights changed. Classifier early catches stay the "
        "recorded 270/284 (95.1%), not remeasured.", "",
        maintenance.table(["Runtime file", "Bytes", "SHA-256"], [[name, r["bytes"], r["sha256"]]
             for name, r in deployment["artifacts"].items()]), "",
        "```python\nfrom server.app.config import ASR_MODEL_ID\nfrom ml_pipeline.voice.transcribe import load_model, DECODING\n"
        "model = load_model(ASR_MODEL_ID, device='auto')\nsegments, _ = model.transcribe('recording.wav', **DECODING)\n"
        "print(' '.join(segment.text.strip() for segment in segments))\n```", "",
        "Weights use UWB-ATCC CC BY-NC-SA 4.0 research data. Research and source references: "
        "[Whisper training guide](https://huggingface.co/blog/fine-tune-whisper), "
        "[Whisper-ATC](https://research.tudelft.nl/en/publications/whisper-atc-open-models-for-air-traffic-control-automatic-speech-/), "
        "[model soups](https://proceedings.mlr.press/v162/wortsman22a.html), "
        "[cluster resampling](https://arxiv.org/abs/1912.09508), "
        "[UWB source/license](https://huggingface.co/datasets/Jzuluaga/uwb_atcc). "
        "Learning rates, trial budget, 0.5-point guard, equal blend and cluster choices are our experimental "
        "design, not published guarantees. Additional sources were researched; no new corpus was downloaded.", "",
        "All working reports, diagnostic sources, preserved training-source copies, logs and report-specific "
        "prediction data are retained losslessly below with SHA-256 and in source_inventory.json. "
        "The user requested removal of the separate dated reports after consolidation; no model/data "
        "cleanup is implied. Restore any individual historical input with "
        "`venv/Scripts/python.exe scripts/consolidate_evaluations.py --restore ORIGINAL_PATH`. "
        "Historical finalize.py is archived evidence, not the current publisher. The active study tools "
        "read the archive without recreating deleted reports. New experiments must use new run paths.", ""]
    return "\n".join(lines)


def prepare():
    payload = maintenance.read_ledger(KEY)
    if any(x["id"] == STUDY for x in payload.get("speech_iterations", [])):
        raise SystemExit("Already consolidated; use --delete-reports or the verifier")
    selection = load("selection.json")
    runtime = Path(selection["runtime_model"]).resolve()
    assert runtime.is_relative_to(WORK.resolve())
    pinned = load("selected_artifact.json")
    for name, info in pinned["files"].items():
        assert maintenance.sha((runtime / name).read_bytes()) == info["sha256"], name
    check = load("activation_runtime_check.json")
    assert check["same_words_as_evaluated_model"] and check["status"]["loaded"]
    assert Path(check["status"]["modelId"]).resolve() == runtime
    files = sorted(p for p in REPORT.rglob("*") if p.is_file()) + EXTRAS
    assert all(p.is_file() for p in files)
    # Preserve the original detailed model README before replacing it with a canonical pointer.
    records = [maintenance.make_record(p) for p in files]
    records.append(maintenance.make_record(runtime / "README.md"))
    cleanup_paths = [relative(p) for p in files]
    (runtime / "README.md").write_text(
        "# Flight Right speech model: uniform_soup3\n\n"
        "This folder is the configured speech runtime. The single maintained evaluation/history, "
        "exact experiments, mixed results, usage and artifact fingerprints are in "
        "`docs/evaluations/asr_small_atc_p1.md` at the project root. "
        "The current cross-model comparison is `docs/evaluation.md`.\n\n"
        "Keep model.bin, config.json, tokenizer.json, vocabulary.json and preprocessor_config.json together.\n",
        encoding="utf-8")
    artifacts = {p.name: {"path": relative(p), "bytes": p.stat().st_size,
                           "sha256": maintenance.sha(p.read_bytes())} for p in runtime.iterdir() if p.is_file()}
    data = {"selection": load("selection.json"), "test": load("test.json"), "protocol": load("protocol.json"),
            "inventory": load("data_inventory.json"), "uncertainty": load("uncertainty.json"),
            "environment": load("environment.json"), "training": {
                name: json.loads((WORK / name / "state.json").read_text())
                for name in ("continue_lr1e4", "indian_mix_lr5e5")}}
    deployment = {"status": "served_default", "authorized_by": "User request, 11 November 2026",
                  "activated_utc": datetime.now(timezone.utc).isoformat(), "runtime_model": str(runtime),
                  "runtime_check": check, "artifacts": artifacts}
    normalized = {"measured_at_utc": load("source_snapshot.json")["finalized_utc"],
                  "activation": deployment, "selection": selection, "models": {
                      "previous_reference": data["test"]["baseline"], "served_uniform_soup3": data["test"]["selected"]}}
    normalized_path = ROOT / "ml_pipeline/reports/voice_eval_20261111_activation.json"
    assert not normalized_path.exists()
    normalized_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    records.append(maintenance.make_record(normalized_path))
    cleanup_paths.append(relative(normalized_path))
    summary = ("Served default: uniform_soup3, user-authorized 11 Nov; equal full-weight average of original P1 "
        "and two independent 300-update continuations, selected on 1,632 validation clips before test. "
        "10 Nov tests: ATCO2 clean WER 27.95%, ATCOSIM 4.80%, UWB 15.33% (regression from 15.11%), "
        "Svarah 31.46%; complete instructions 21/31 versus 20/31. Generated practice WER 24.62% to 16.60% "
        "on 416 development calls, not real Indian radio accuracy. Original test scores are cached re-scoring, "
        "with 256 fresh controls matching exactly. Small/mixed retrospective effects; no new latency claim.")
    entry = {"id": STUDY, "deployment": deployment, "cleanup_paths": cleanup_paths,
             "current_summary": summary, "narrative_markdown": narrative(data, deployment),
             "normalized_evaluation_source": relative(normalized_path),
             "source_ownership": "Existing Whisper-small ATC family ledger, as explicitly requested by the user"}
    known = {r["path"]: r for r in payload["records"]}
    for record in records:
        if record["path"] in known:
            assert known[record["path"]] == record, record["path"]
        else:
            payload["records"].append(record)
    payload["records"].sort(key=lambda r: r["path"])
    payload.setdefault("speech_iterations", []).append(entry)
    maintenance.write_ledger(KEY, payload)
    index = json.loads(maintenance.INDEX.read_text())
    indexed = {e["path"]: e for e in index["sources"]}
    for record in records:
        if record["path"] in indexed:
            assert indexed[record["path"]]["sha256"] == record["sha256"]
            continue
        removable = record["path"] in cleanup_paths
        index["sources"].append({"path": record["path"], "models": [KEY],
            "sha256": record["sha256"], "bytes": record["bytes"], "cleanup": removable,
            "status": "preserved_before_user_authorized_cleanup" if removable else "historical_model_readme_replaced_by_pointer",
            "preservation": "Checksum-verified inline ledger evidence; local and uncommitted, not claimed in the old pushed checkpoint",
            "replacement": "docs/evaluations/asr_small_atc_p1.md#source-register",
            "cleanup_reason": "User requested one existing speech evaluation/history and deletion of the separate new reports",
            "regeneration": "Restore exact bytes with consolidate_evaluations.py --restore ORIGINAL_PATH"})
    maintenance.INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    maintenance.refresh()
    maintenance.verify()
    # Explicit round-trip check for every newly captured source, including binary reports.
    archived = maintenance.records_all()
    for record in records:
        assert maintenance.raw(archived[record["path"]]) == maintenance.raw(record)
    print(f"Preserved {len(records)} exact sources in {relative(LEDGER)}; no reports deleted yet.")


def delete_reports():
    maintenance.verify()
    entry = next(x for x in maintenance.read_ledger(KEY)["speech_iterations"] if x["id"] == STUDY)
    records = maintenance.records_all()
    allowed_extras = {p.resolve() for p in EXTRAS + [ROOT / "ml_pipeline/reports/voice_eval_20261111_activation.json"]}
    targets = []
    for name in entry["cleanup_paths"]:
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT.resolve())
        assert path.is_relative_to(REPORT.resolve()) or path in allowed_extras, path
        if path.exists():
            assert path.is_file() and maintenance.sha(path.read_bytes()) == records[name]["sha256"], path
            assert path.read_bytes() == maintenance.raw(records[name]), path
            targets.append(path)
    # All absolute paths and all evidence bytes have passed before the first unlink.
    removed_bytes = sum(p.stat().st_size for p in targets)
    for path in targets:
        path.unlink()
    if REPORT.exists():
        for directory in sorted((p for p in REPORT.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            assert directory.resolve().is_relative_to(REPORT.resolve())
            directory.rmdir()  # fails safely if a concurrent/unrecognized file exists
        REPORT.rmdir()
    index = json.loads(maintenance.INDEX.read_text())
    for source in index["sources"]:
        if source["path"] in entry["cleanup_paths"]:
            source["status"] = "consolidated_original_removed"
            source["removed_utc"] = datetime.now(timezone.utc).isoformat()
    index.setdefault("user_authorized_cleanups", []).append({"iteration": STUDY,
        "removed_files": len(targets), "removed_bytes": removed_bytes,
        "authorization": "11 November user request; exact inline ledger preservation verified before deletion",
        "weights_and_original_datasets_removed": False})
    maintenance.INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    maintenance.verify()
    print(f"Deleted {len(targets)} verified standalone report/source-cache files ({removed_bytes:,} bytes). Model weights and original datasets retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--delete-reports", action="store_true")
    args = parser.parse_args()
    prepare() if args.prepare else delete_reports()


if __name__ == "__main__":
    main()
