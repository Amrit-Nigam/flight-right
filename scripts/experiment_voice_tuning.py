"""Local, validation-selected speech study. Never changes the application's model.

Run with venv/Scripts/python.exe -u scripts/experiment_voice_tuning.py.
Training inputs remain read-only; new weights/caches live in checkpoints/voice_20261110.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT / "checkpoints/voice_20261110"
REPORT = ROOT / "ml_pipeline/reports/voice_tuning_20261110"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def command(args, log):
    print("Running", " ".join(map(str, args)), flush=True)
    with log.open("w", encoding="utf-8") as output:
        subprocess.run([sys.executable, "-u", *map(str, args)], cwd=ROOT,
                       stdout=output, stderr=subprocess.STDOUT, check=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_selection(path, record):
    if path.exists():
        saved = json.loads(path.read_text())
        for key in ("winner", "model", "validation"):
            if saved[key] != record[key]:
                raise RuntimeError("Frozen validation choice changed; use a new study directory")
        return saved
    save(path, record)
    return record


def choose(validation):
    """Predeclared: lower equal-corpus mean; at most 0.5 pp worse per real corpus."""
    baseline = validation["baseline"]
    eligible = [name for name, scores in validation.items()
                if all(scores[c] <= baseline[c] + 0.5 for c in baseline)]
    return min(eligible, key=lambda name: sum(validation[name].values()) / len(baseline))


def write_summary(validation, winner, baseline_test, selected_test):
    lines = ["# Speech recognition tuning — measured results", "",
             f"Validation-selected result: **{winner}**. Lower word error is better.", "",
             "## Comparison used to choose the model", "",
             "All 1,632 real validation recordings, same application decoder for every model.", "",
             "| Model | ATCOSIM word error % | UWB word error % |",
             "| --- | ---: | ---: |"]
    for name, scores in validation.items():
        lines.append(f"| {name} | {scores['atcosim']} | {scores['uwb']} |")
    lines += ["", "## Final test", "", "Only the validation winner received new test inference.", "",
              "| Recording collection | Clips | Previous word error % | Selected word error % |",
              "| --- | ---: | ---: | ---: |"]
    for corpus, scores in selected_test["corpora"].items():
        old = baseline_test["corpora"][corpus]
        lines.append(f"| {corpus} | {scores['clips']} | {old['wer']} | {scores['wer']} |")
    old = baseline_test["corpora"]["atco2_clean"]
    new = selected_test["corpora"]["atco2_clean"]
    lines += ["", f"Complete radio instructions correct: {old['clearance_accuracy']}% → {new['clearance_accuracy']}% "
              f"on {new['clearance_n']} annotated instructions. This is a small sample.", "",
              "Word error counts words substituted, omitted or added per 100 reference words; "
              "it is not the percentage of whole sentences correct.", "",
              "Indian everyday English is reported separately from radio speech. Generated Indian "
              "practice voices cannot establish accuracy on real Indian controllers.", "",
              "The historical test has been examined before; these results are exploratory. "
              "Only two limited-budget training trials were searched, so no global-best claim is justified.", "",
              "The application's installed speech model was not changed. New exported weights, "
              "adapters and compressed runtime weights are in checkpoints/voice_20261110. "
              "The UWB training source has noncommercial share-alike terms.", "",
              "Recorded conflict detection remains 270/284 (95.1%), not remeasured."]
    (REPORT / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    if not REPORT.exists():
        from scripts.consolidate_evaluations import read_evidence
        try:
            archived = json.loads(read_evidence(REPORT / "selection.json"))
        except KeyError:
            pass
        else:
            print(f"Completed study is consolidated in docs/evaluations/asr_small_atc_p1.md; "
                  f"selected checkpoint: {archived['winner']}. No training or new reports run. "
                  "Restore the archived inputs explicitly for historical reproduction, or use a new study directory.")
            return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import pandas as pd
    from ml_pipeline.voice.train_whisper import all_rows, Audio
    from ml_pipeline.voice.build_audio_cache import CACHE
    from ml_pipeline.voice import transcribe as tr
    from ml_pipeline.voice import evaluate_voice as ev
    from ml_pipeline.voice.text_norm import normalise
    WORK.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    baseline = CACHE / "models/flightright-whisper-small-atc-p1"
    init = CACHE / "runs/p1_main/best_adapter"
    rows = all_rows()
    protocol = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": 42, "baseline": str(baseline), "initial_adapter": str(init),
        "manifest_sha256": sha(CACHE / "manifest.parquet"),
        "tts_manifest_sha256": {p.name: sha(p) for p in sorted((CACHE / "tts").glob("manifest*.parquet"))},
        "adapter_sha256": sha(init / "adapter_model.safetensors"),
        "corpus_counts": rows.groupby(["corpus", "split"]).size().to_dict().__str__(),
        "trials": {"continue_lr1e4": "p1", "indian_mix_lr5e5": "p2"},
        "derived_candidates": {"uniform_soup3": "equal full-weight average of original, continue_lr1e4 and indian_mix_lr5e5"},
        "training": "300 updates each, batch 8 x accumulation 2, warmup 30, evaluate every 100",
        "selection": "lowest mean WER on ALL real ATCOSIM/UWB validation clips; no corpus > baseline+0.5 percentage points; baseline eligible",
        "test_policy": "only validation winner gets new test inference; historical baseline cached; test never selects trial",
        "decoder": tr.DECODING, "quantisation": "int8_float16",
        "limits": "Historical test repeatedly inspected previously; not a fresh blind benchmark. Synthetic speech cannot validate real Indian ATC.",
        "sources": ["https://huggingface.co/blog/fine-tune-whisper",
                    "https://research.tudelft.nl/en/publications/whisper-atc-open-models-for-air-traffic-control-automatic-speech-/",
                    "https://huggingface.co/datasets/Jzuluaga/uwb_atcc"],
        "design": "Trial budget, learning rates and 0.5-point validation guard are our own experimental design, not a paper's guarantee.",
    }
    if not (REPORT / "protocol.json").exists():
        save(REPORT / "protocol.json", protocol)
    else:
        old = json.loads((REPORT / "protocol.json").read_text())
        for key in ("manifest_sha256", "adapter_sha256", "selection", "trials"):
            if old[key] != protocol[key]:
                raise RuntimeError(f"Study input/protocol changed: {key}")
        # Add provenance for still-unused synthetic data before its training trial begins.
        if "tts_manifest_sha256" not in old:
            assert not (WORK / "indian_mix_lr5e5/state.json").exists()
            old["tts_manifest_sha256"] = protocol["tts_manifest_sha256"]
            save(REPORT / "protocol.json", old)
        elif old["tts_manifest_sha256"] != protocol["tts_manifest_sha256"]:
            raise RuntimeError("Synthetic training manifest changed")
        if "derived_candidates" not in old:
            assert not (REPORT / "selection.json").exists() and not (REPORT / "test.json").exists()
            old["derived_candidates"] = protocol["derived_candidates"]
            old["amendments"] = [{"utc": datetime.now(timezone.utc).isoformat(),
                "reason": "Full validation: real-only continuation 12.08/10.79 versus original 12.10/10.64; accent step-200 worsens recorded-speech validation while improving generated voices. Add one uniform weight average before any final test inference. Selection rule unchanged."}]
            save(REPORT / "protocol.json", old)
        elif old["derived_candidates"] != protocol["derived_candidates"]:
            raise RuntimeError("Derived-candidate recipe changed")
    for corpus in ("atcosim", "uwb", "tts_indian"):
        frame = rows[rows.corpus == corpus]
        groups = {split: set(frame.loc[frame.split == split, "group"]) for split in ("train", "val", "test")}
        for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
            assert not groups[left] & groups[right], (corpus, left, right)
    assert not rows.uid.duplicated().any(), "Duplicate clip IDs"
    if "--prepare-only" in sys.argv:
        print("Protocol frozen; split separation checked.", flush=True)
        return
    audit_path = REPORT / "data_audit.json"
    if not audit_path.exists():
        command(["scripts/audit_voice_data.py"], REPORT / "data_audit.log")
    assert not json.loads(audit_path.read_text())["cross_split_exact_duplicates"], "Audio leakage requires review"
    for name, stage in protocol["trials"].items():
        statefile = WORK / name / "state.json"
        state = json.loads(statefile.read_text()) if statefile.exists() else {}
        if not state.get("finished_utc"):
            args = ["ml_pipeline/voice/train_whisper.py", "--stage", stage, "--init", init,
                    "--output-root", WORK, "--run", name, "--lr", "0.0001" if stage == "p1" else "0.00005",
                    "--warmup", "30", "--max-steps", "300", "--eval-every", "100", "--val-per-corpus", "200"]
            if statefile.exists():
                args += ["--resume"]
            command(args, REPORT / f"{name}_train.log")
    models = {"baseline": str(baseline)}
    for name in protocol["trials"]:
        out = WORK / "models" / name
        if not (WORK / "ct2" / f"local__{name}__int8_float16/model.bin").exists():
            command(["ml_pipeline/voice/export_whisper.py", "--adapter", WORK / name / "best_adapter",
                     "--name", name, "--output-root", WORK / "models", "--ct2-root", WORK / "ct2"],
                    REPORT / f"{name}_export.log")
        models[name] = str(out)
    soup = WORK / "models/uniform_soup3"
    if not (WORK / "ct2/local__uniform_soup3__int8_float16/model.bin").exists():
        command(["ml_pipeline/voice/blend_whisper.py", "--sources", *models.values(),
                 "--output", soup, "--ct2-root", WORK / "ct2"], REPORT / "uniform_soup3_export.log")
    models["uniform_soup3"] = str(soup)
    # Existing baseline converted model can be read; only new outputs use workspace paths.
    original_ct2 = tr.CT2_DIR
    original_transcripts = tr.TRANSCRIPTS
    original_path = tr.ct2_path
    tr.CT2_DIR = WORK / "ct2"
    tr.TRANSCRIPTS = WORK / "transcripts"
    tr.ct2_path = lambda model, quant: (original_ct2 / f"{tr._slug(model)}__{quant}"
                                      if model == str(baseline) else original_path(model, quant))
    val = rows[(rows.split == "val") & rows.corpus.isin(["atcosim", "uwb"])]
    validation = {}
    for name, model in models.items():
        got = tr.transcribe_rows(model, val, device="cuda").set_index("uid")
        scores = {c: ev.wer(list(f.text), [normalise(t) for t in got.loc[f.uid].hyp.fillna("")])
                  for c, f in val.groupby("corpus")}
        validation[name] = scores
        print("VALIDATION", name, scores, flush=True)
        save(REPORT / "validation.json", validation)
    winner = choose(validation)
    runtime = (original_ct2 if winner == "baseline" else WORK / "ct2") / f"{tr._slug(models[winner])}__int8_float16"
    freeze_selection(REPORT / "selection.json", {"winner": winner, "model": models[winner], "runtime_model": str(runtime), "validation": validation,
                                                "frozen_utc": datetime.now(timezone.utc).isoformat()})
    print("Frozen validation winner:", winner, flush=True)
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    gold = ev.gold_atco2()
    tr.TRANSCRIPTS = original_transcripts
    baseline_test = ev.evaluate_model(str(baseline), manifest, gold, "cuda")
    tr.TRANSCRIPTS = WORK / "transcripts"
    winner_test = baseline_test if winner == "baseline" else ev.evaluate_model(models[winner], manifest, gold, "cuda")
    save(REPORT / "test.json", {"baseline": baseline_test, "selected": winner_test, "winner": winner})
    write_summary(validation, winner, baseline_test, winner_test)
    save(REPORT / "selected_artifact.json", {
        "runtime_model": str(runtime), "configured_by": "FLIGHT_RIGHT_ASR_MODEL_ID",
        "installed_in_application": False,
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in runtime.iterdir() if p.is_file()},
        "scope": "Offline research candidate; see validation and test results before installation",
        "licence": "Includes UWB-ATCC CC BY-NC-SA 4.0 training data; noncommercial research use",
    })
    print("Finished. Results:", REPORT, flush=True)


if __name__ == "__main__":
    main()
