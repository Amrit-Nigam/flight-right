"""Maintain one Markdown evaluation ledger per model and one latest-results page.

Migration: --build --checkpoint COMMIT, then --verify, then --cleanup.
Future runs: --ingest REPORT --models MODEL [MODEL ...], then --refresh.
Restore old inputs for legacy report scripts with --restore PATH (never overwrites).
Only cleanup paths explicitly inventoried and verified against a pushed checkpoint.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evaluations"
INDEX = OUT / "source_inventory.json"
MARK = "<!-- evaluation-evidence-v1 -->\n```json\n"
MODELS = {
    "trajectory_lstm": ("Residual LSTM (Model 1)", "Learned single-position trajectory model; served baseline and all fine-tuning variants."),
    "constant_velocity": ("Constant velocity", "Deterministic trajectory baseline, not a learned model."),
    "tree_reference": ("Tree trajectory reference", "Benchmark only. Saved test predictions survive; fitted estimators are not retained."),
    "multipath": ("Multi-path trajectory bundle (Model 1b)", "KMeans route clusters, 40-class route classifier, temperature calibration and along/cross/altitude offset regressors are constituents of this jointly evaluated bundle. Includes table, per-mode, archive, destination and continuation variants."),
    "conflict_classifier": ("XGBoost conflict classifier (Model 2)", "Served classifier, calibration, selected-altitude changes, seed studies and threshold experiments."),
    "conflict_filter": ("Secondary XGBoost conflict filter", "Experimental learned veto, six initial depth/input variants, ensembles, refits and continuations. Not deployed."),
    "resolution": ("Resolution engine (Model 3)", "Deterministic simulation and ranking engine; a learned resolution ranker is deferred and has no trained model or scores."),
    "full_alert_chain": ("Full alert chain", "Integration evaluation, not another trained model. Keep separate from classifier-only scores."),
    "path_confidence": ("Path-confidence experiment", "Rejected/rolled-back all-pairs shadow-policy experiment; no deployed model."),
    "alert_feed": ("Alert feed", "Deterministic notification suppression; measures interruptions, not conflict prediction accuracy."),
    "clearance_extractor": ("Clearance and callsign extraction", "Deterministic parser/matcher, human-transcript upper bound, clearance-chain and oracle demonstrations; not an ASR model."),
    "asr_small": ("openai/whisper-small", "Untouched speech baseline."),
    "asr_small_atc_p1": ("FlightRight Whisper-small ATC P1", "Own LoRA fine-tune on openai/whisper-small; configured default when its local export exists. Local-path separator variants denote the same model."),
    "asr_medium": ("openai/whisper-medium", "Untouched speech comparator."),
    "asr_medium_atcosim": ("jlvdoorn/whisper-medium-atcosim", "Published ATC comparator; ATCOSIM is training-contaminated."),
    "asr_large_atc": ("jlvdoorn/whisper-large-v3-atco2-asr-atcosim", "Published ATC comparator. ATCO2 recording overlap and ATCOSIM training contamination must stay attached to its scores."),
    "indic_parler_tts": ("ai4bharat/indic-parler-tts", "Synthetic voice generation for training/demo; no objective TTS quality benchmark found. Script extraction recovery is not TTS accuracy."),
    "silero_vad": ("Silero VAD (faster-whisper)", "Pretrained speech gate used in the live speech service. No labelled VAD evaluation or fine-tuning found."),
}
ASR = ["asr_small", "asr_small_atc_p1", "asr_medium", "asr_medium_atcosim", "asr_large_atc"]
SHARED = ["trajectory_lstm", "constant_velocity", "tree_reference", "multipath", "conflict_classifier", "resolution", "full_alert_chain", "alert_feed"]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def asr_key(model_id):
    if "flightright-whisper-small-atc-p1" in model_id:
        return "asr_small_atc_p1"
    return {v[0]: k for k, v in MODELS.items() if k in ASR}.get(model_id)


def classify(path):
    s = path.relative_to(ROOT).as_posix()
    n = path.name
    if "path_confidence_experiments/" in s and path.suffix == ".jsonl":
        return ["path_confidence"], True
    if s == "docs/experiments/README.md":
        return ["trajectory_lstm"], True
    if "evaluation-history/" in s and path.suffix == ".png":
        owner = ("multipath" if "multipath" in n else "trajectory_lstm" if "traj_" in n else "resolution" if "model3" in n else "alert_feed" if any(w in n for w in ["feed", "precision_by_band", "runway"]) else "conflict_classifier")
        return [owner], True
    if "reports/logs/" in s:
        if "voice" in n:
            return ASR, True
        if "reevaluation" in n:
            return SHARED, True
        if "multipath" in s or "offsets" in n:
            return ["multipath"], True
        if "conflict" in n or "xgboost" in n or "encounters" in n:
            return ["conflict_classifier"], True
        return ["trajectory_lstm"], True
    if "archived_source/" in s:
        return ["path_confidence"], False
    if "trajectory_tuning" in s or "eval_residual_lstm" in s:
        return ["trajectory_lstm"], True
    if "eval_constant_velocity" in s:
        return ["constant_velocity"], True
    if "eval_tree_reference" in s:
        return ["tree_reference"], True
    if "path_confidence" in s:
        return ["path_confidence"], True
    if "conflict_refinement" in s or "conflict_false_alerts" in s:
        return ["conflict_classifier", "conflict_filter", "full_alert_chain"], True
    if n.startswith("voice_eval"):
        d = json.loads(path.read_text(encoding="utf-8"))
        return sorted({"clearance_extractor", *[asr_key(v["model_id"]) for v in d["models"].values()]} - {None}), True
    if n.startswith("voice_train"):
        return ["asr_small_atc_p1"], True
    if n.startswith(("voice_cache", "voice_corpora")):
        return ASR + ["clearance_extractor"], True
    if n.startswith(("chain_check", "clearance_demo", "oracle_clearance")):
        return ["clearance_extractor", "full_alert_chain"], True
    if n.startswith("mumbai_scripts"):
        return ["indic_parler_tts", "clearance_extractor"], True
    if any(w in s for w in ["multipath", "offsets_ab", "destination_", "context_ablation", "context_features"]):
        return ["multipath", "full_alert_chain"], True
    if n.startswith("classifier_intent") or "xgboost_conflict" in n:
        return ["conflict_classifier"], not s.startswith("server/")
    if n.startswith("alert_prominence"):
        return ["alert_feed"], True
    if n.startswith(("reevaluation", "training_report")) or n in {"metrics.json", "evaluation.md", "ablation.json", "ablation.md"} or "evaluation-history/" in s:
        return SHARED, True
    return [], False


def read_ledger(key):
    p = OUT / f"{key}.md"
    if not p.exists():
        return {"model": key, "records": []}
    return json.loads(p.read_text(encoding="utf-8").split(MARK, 1)[1].split("\n```", 1)[0])


def records_all():
    records = {}
    for key in MODELS:
        for r in read_ledger(key)["records"]:
            if r["path"] in records:
                assert records[r["path"]] == r, f"Conflicting copies: {r['path']}"
            records[r["path"]] = r
    return records


def raw(r):
    return base64.b64decode(r["content"]) if r["encoding"] == "base64" else r["content"].encode("utf-8")


def make_record(p):
    data = p.read_bytes()
    try:
        content, encoding = data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        content, encoding = base64.b64encode(data).decode(), "base64"
    return {"path": p.relative_to(ROOT).as_posix(), "sha256": sha(data), "bytes": len(data), "encoding": encoding, "content": content}


def load(records, path):
    return json.loads(raw(records[path]))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |", *["| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ") for x in row) + " |" for row in rows]])


def historical_links(text, source):
    """Resolve historical prose links without modifying the lossless source record."""
    inventory = json.loads(INDEX.read_text())["sources"] if INDEX.exists() else []
    mapped = {e["path"]: e for e in inventory}
    def replace(match):
        image, label, url = match.groups()
        if re.match(r"[a-zA-Z]+:|#", url):
            return match.group(0)
        target = (ROOT / source).parent.joinpath(url.split("#", 1)[0]).resolve()
        if not target.is_relative_to(ROOT.resolve()):
            return match.group(0)
        e = mapped.get(target.relative_to(ROOT.resolve()).as_posix())
        if e and e["cleanup"]:
            return f"[{label} (archived source)]({e['models'][0]}.md#source-register)"
        if not target.exists():
            relative = target.relative_to(ROOT.resolve()).as_posix()
            archived = next((entry for name, entry in mapped.items() if name.endswith("archived_source/" + relative)), None)
            if archived:
                target = ROOT / archived["path"]
        return f"{image}[{label}]({Path(os.path.relpath(target, OUT)).as_posix()})"
    return re.sub(r"(!?)\[([^\]]*)\]\(([^)]+)\)", replace, text)


def narrative(key, records):
    lines = []
    if "docs/metrics.json" in records:
        current = load(records, "docs/metrics.json")
        if key in {"tree_reference", "trajectory_lstm", "constant_velocity"}:
            rows = current["tree_reference"]["per_horizon"] if key == "tree_reference" else current["model1"]["per_horizon" if key == "trajectory_lstm" else "baseline_per_horizon"]
            lines += ["## Latest served/reference snapshot (30 October 2026)", "", table(["Horizon", "n", "Mean NM", "RMSE NM", "Within 5 NM %", "Altitude MAE ft"], [[r["horizon"], r["n"], r["mean_nm"], r["rmse_nm"], r["within_5_nm"], r["altitude_mae_ft"]] for r in rows]), ""]
        elif key == "alert_feed":
            lines += ["## Latest replay results", "", table(["Session", "Frames", "Before", "After", "Reduction %", "Pairs lost"], [[r["session"], r["frames"], r["interruptions_before"], r["interruptions_after"], r["cut_percent"], r["lost"]] for r in current["alert_feed"]]), ""]
    if key == "multipath":
        lines += ["## Development sequence", "", "Initial pattern-table bundle: September 6; per-mode regressors measured September 23 and served September 24; archive-augmented training and four-seed studies September 25, served September 26; destination inputs measured September 26 and served September 27. November 1 compares continue_600, continue_800 and rejected regularized31; only continue_800 is the validation-selected packaged candidate, not deployed. Context, altitude/3-D, runtime and seed ablations below preserve all costs alongside gains.", ""]
        seed_rows = []
        for path, r in sorted(records.items()):
            if not path.endswith(".json") or not Path(path).name.startswith(("multipath_seeds_", "multipath_archive_seeds_")):
                continue
            d = json.loads(raw(r))
            for seed, run in d.get("runs", {}).items():
                for variant, scores in run.get("best_of_k", {}).items():
                    for k, groups in scores.items():
                        for group, value in groups.items():
                            seed_rows.append([Path(path).stem, seed, variant, k, group, value])
        lines += ["### Multi-seed route coverage history", "", "Rates are percentages; the whole route bundle varies by seed. Top-k coverage is not single-guess accuracy. Offset-only continuation is a different, deterministic experiment.", "", table(["Report", "Seed", "Variant", "k", "Group", "Within 5 NM %"], seed_rows), ""]
    snapshots = []
    for path, record in sorted(records.items()):
        if not Path(path).name.startswith("reevaluation_") or not path.endswith(".json"):
            continue
        d = json.loads(raw(record))
        if key in {"trajectory_lstm", "constant_velocity"}:
            field = "per_horizon" if key == "trajectory_lstm" else "baseline_per_horizon"
            for row in d.get("model1", {}).get(field, []):
                snapshots.append([Path(path).stem, row["horizon"], row["n"], row["mean_nm"], row["rmse_nm"], row["within_5_nm"], row["altitude_mae_ft"]])
        elif key == "conflict_classifier":
            row = d.get("model2", {}).get("test", {})
            h = row.get("headline", {})
            snapshots.append([Path(path).stem, row.get("threshold"), row.get("precision"), row.get("recall"), row.get("f1"), f"{h.get('caught')}/{h.get('total')}"])
        elif key == "resolution":
            row = d.get("model3", {})
            snapshots.append([Path(path).stem, row.get("alarms"), row.get("candidates_evaluated"), row.get("instructions_offered"), row.get("instructions_for_real"), row.get("instructions_for_false")])
    if snapshots:
        headers = (["Report", "Horizon", "n", "Mean NM", "RMSE NM", "Within 5 NM %", "Altitude MAE ft"] if key in {"trajectory_lstm", "constant_velocity"} else ["Report", "Raw threshold", "Precision", "Recall", "F1", "Early catches"] if key == "conflict_classifier" else ["Report", "Encounters", "Manoeuvres simulated", "Instructions", "On real conflicts", "On false alarms"])
        lines += ["## Historical re-evaluations", "", "These snapshots score the artifacts present on each date. A re-score is not necessarily a new training iteration; tiny floating-point differences are preserved. The exact configuration, dataset and all other metrics are in each source record.", "", table(headers, snapshots), ""]
    if key in ASR or key == "clearance_extractor":
        rows = []
        for path, r in sorted(records.items()):
            if not Path(path).name.startswith("voice_eval"):
                continue
            d = json.loads(raw(r))
            for v in d["models"].values():
                if (key in ASR and asr_key(v["model_id"]) != key) or (key == "clearance_extractor" and "human transcript" not in v["model_id"]):
                    continue
                for corpus, metrics in v["corpora"].items():
                    rows.append([Path(path).stem.removeprefix("voice_eval_"), corpus, metrics.get("clips", ""), metrics.get("wer", "n/a"), metrics.get("wer_numerals_spoken", "n/a"), metrics.get("clearance_accuracy", "n/a"), metrics.get("callsign_accuracy_with_list", "n/a"), metrics.get("held_out", "human transcript; extractor upper bound")])
        lines += ["## Recorded speech/extraction iterations", "", "WER and accuracies are percentages. Different corpora and raw/numeral-normalized WER must not be ranked together. `NaN` means unavailable, never zero. Rejected number-rule results remain history only.", "", table(["Report", "Corpus", "Clips", "WER %", "Spoken-numeral WER %", "Clearance %", "Callsign with list %", "Evaluation basis"], rows), ""]
    if key == "asr_small_atc_p1":
        d = load(records, "ml_pipeline/reports/voice_train_p1_main.json")
        lines += ["## LoRA training checkpoints", "", "r=32, 12,976,128 trainable parameters; 7,330 ATCOSIM and 10,172 UWB clips, learning rate 0.0005, batch 8 with accumulation 2; validation uses 200 clips per corpus. Training-validation scores below differ from the exported CTranslate2 test decoder.", "", table(["Step", "ATCOSIM val WER %", "UWB val WER %", "Mean val WER %"], [[x["step"], x["wer"]["atcosim"], x["wer"]["uwb"], x["wer"]["mean"]] for x in d["evals"]]), ""]
    for path, r in sorted(records.items()):
        if path.startswith("docs/experiments/") and path.endswith(".md") and Path(path).name != "README.md":
            lines += [f"## Study: {Path(path).stem}", "", "Historical narrative below retains the recorded results; statements about being uncommitted describe the study date. All studies are now preserved in the checkpoint commit. Links to removed originals now lead to their ledger source register; the evidence appendix retains the exact original prose and links.", "", historical_links(r["content"], path), ""]
    if key in ["trajectory_lstm", "multipath", "conflict_classifier", "conflict_filter", "path_confidence"]:
        rows = []
        for path, r in sorted(records.items()):
            if path.endswith("/summary.json") or path.endswith("/results.json") or ("trajectory_tuning" in path and re.search(r"_seed\d+\.json$", path)):
                d = json.loads(raw(r))
                rows.append([path, ", ".join(d.keys()), "Exact configuration, validation/test numbers, guards and rejected trials in evidence record below"])
        lines += ["## Complete iteration register", "", table(["Recorded run", "Recorded sections", "Details"], rows), ""]
    return "\n".join(lines)


def maintenance_narrative(payload):
    entries = payload.get("artifact_retirements", [])
    if not entries:
        return ""
    lines = ["## Model artifact cleanup (9 November 2026)", "", "These are storage changes, not new evaluations or model deployment. Original reports below retain every measured value. Retiring a trial's weight file does not erase its configuration or results; rerunning a retired trial requires retraining.", ""]
    for entry in entries:
        lines += [f"### {entry['name']}", "", entry["decision"], "", f"Status: **{entry['status']}**. Original artifact: `{entry['artifact']}`; SHA-256: `{entry['artifact_sha256']}`.", ""]
        if "configuration" in entry:
            lines += ["Configuration: `" + json.dumps(entry["configuration"], sort_keys=True) + f"`; seed {entry['seed']}. Validation objective: {entry['comparison']['objective']:.10f}; trajectory guards passed: {entry['comparison']['passes_guardrails']}.", "", "Fitted trees (along/cross/altitude): " + "/".join(str(entry["fit"][k]["iterations"]) for k in ("0", "1", "2")) + ". Test outcome: " + entry["test_outcome"] + ".", "", table(["Validation group", "n", "Top-1 mean NM", "Top-1 RMSE NM", "Top-1 5 NM %", "Best-5 5 NM %", "Top-1 3-D %", "Best-5 3-D %", "Altitude MAE ft"], [[group, r["n"], r["top1_mean_nm"], r["top1_rmse_nm"], r["top1_within_5nm"], r["best5_within_5nm"], r["top1_both"], r["best5_both"], r["top1_altitude_mae_ft"]] for group, r in entry["validation"]["groups"].items()]), "", "Full configuration, training/validation split protocol, every regime metric and guard failure remain in the machine-readable retirement entry and original source records. Source: `" + entry["source_report"] + "`.", ""]
        if "retained_artifact" in entry:
            lines += ["Retained canonical artifact: `" + entry["retained_artifact"] + "`. " + entry["equivalence_note"], ""]
    return "\n".join(lines)


def write_ledger(key, payload):
    title, desc = MODELS[key]
    content = [f"# {title}: evaluation and testing", "", desc, "", "[Latest comparison](../evaluation.md) · [Every original source and cleanup status](source_inventory.json)", "", "This is the single maintained history for this model/component. Records preserve the original bytes, including every numeric field, trial, seed, protocol, selection and caveat. Shared reports are included in each relevant ledger. No fresh inference is implied by consolidation.", "", narrative(key, {r["path"]: r for r in payload["records"]}), "## Source register", "", table(["Original path", "SHA-256", "Bytes"], [[r["path"], r["sha256"], r["bytes"]] for r in payload["records"]]), "", "## Lossless evidence", "", "Machine-readable JSON envelope. `content` is exact UTF-8 text or base64 bytes; numeric payloads remain unchanged, including historical JSON NaN. Use the maintenance script to verify or restore a source.", "", MARK + json.dumps(payload, indent=2, ensure_ascii=True) + "\n```\n"]
    OUT.mkdir(parents=True, exist_ok=True)
    content.insert(content.index("## Source register"), maintenance_narrative(payload))
    (OUT / f"{key}.md").write_text("\n".join(content), encoding="utf-8", newline="\n")


def build(checkpoint):
    assert not INDEX.exists(), "Migration already exists; use --ingest / --refresh."
    checkpoint = git("rev-parse", checkpoint)
    assert git("rev-parse", "origin/fine-tuning") == checkpoint, "Checkpoint must be pushed to origin/fine-tuning."
    nested = [p for p in (ROOT / "ml_pipeline/data/processed/seed_runs").glob("*") if p.name.endswith((".summary.json", ".log", "model_card.json")) or p.name == "destination_alerts.json"]
    nested += list((ROOT / "ml_pipeline/data/processed/path_confidence_experiments").rglob("*.jsonl"))
    sources = sorted({* (ROOT / "ml_pipeline/reports").rglob("*"), *(ROOT / "docs/experiments").rglob("*"), *(ROOT / "docs/evaluation-history").rglob("*"), *(ROOT / "ml_pipeline/data/processed").glob("eval_*"), *nested, ROOT / "docs/evaluation.md", ROOT / "docs/metrics.json", ROOT / "docs/ablation.md", ROOT / "docs/ablation.json", *(ROOT / "server/app/ml/saved_models").glob("*model_card.json")})
    payloads = {k: {"model": k, "records": []} for k in MODELS}
    entries = []
    for p in sources:
        if not p.is_file():
            continue
        owners, cleanup = classify(p)
        # Experiment images are assets, not duplicate evaluation reports.
        if p.suffix == ".png" and "docs/experiments/" in p.as_posix():
            cleanup = False
        rel = p.relative_to(ROOT).as_posix()
        if not owners:
            entries.append({"path": rel, "status": "retained_supporting_data_report", "models": [], "cleanup": False, "sha256": sha(p.read_bytes())})
            continue
        blob = git("rev-parse", f"{checkpoint}:{rel}")
        assert git("hash-object", "--path", rel, rel) == blob, f"Not preserved at checkpoint: {rel}"
        r = make_record(p)
        for key in owners:
            payloads[key]["records"].append(r)
        # evaluation.md is replaced with the latest comparison, not deleted.
        cleanup = cleanup and rel != "docs/evaluation.md"
        entries.append({"path": rel, "models": owners, "sha256": r["sha256"], "bytes": r["bytes"], "checkpoint_blob": blob, "cleanup": cleanup, "status": "pending_cleanup" if cleanup else "retained_or_replaced"})
    for key, payload in payloads.items():
        write_ledger(key, payload)
    INDEX.write_text(json.dumps({"schema": 1, "checkpoint": checkpoint, "checkpoint_remote": "origin/fine-tuning", "created_utc": datetime.now(timezone.utc).isoformat(), "sources": entries, "retained_context": ["docs/CLAUDE.md", "docs/claims.md", "README.md", "ml_pipeline/README_TRAINING.md"], "context_note": "Mixed project/design documents retained; their historical claims do not override docs/evaluation.md. Model weights, data splits, predictions, tests, training sources and archived experiment code are retained."}, indent=2) + "\n", encoding="utf-8")
    refresh()
    verify()


def verify():
    index = json.loads(INDEX.read_text())
    records = records_all()
    for key in MODELS:
        for entry in read_ledger(key).get("artifact_retirements", []):
            source = records[entry["source_report"]]
            assert source["sha256"] == entry["source_report_sha256"]
            report = json.loads(raw(source))
            for field, original in (("configuration", "config"), ("seed", "seed"), ("fit", "fit"), ("validation", "validation"), ("comparison", "comparison"), ("artifact_sha256", "sha256")):
                assert entry[field] == report[original], f"Retirement provenance mismatch: {entry['name']}/{field}"
    for r in records.values():
        assert len(raw(r)) == r["bytes"] and sha(raw(r)) == r["sha256"], r["path"]
        if r["path"].endswith(".json"):
            json.loads(raw(r))  # Includes legacy NaN, which Python's JSON reader supports.
    for e in index["sources"]:
        for key in e["models"]:
            r = next(r for r in read_ledger(key)["records"] if r["path"] == e["path"])
            assert r["sha256"] == e["sha256"], e["path"]
        p = ROOT / e["path"]
        if e["cleanup"] and p.exists():
            assert sha(p.read_bytes()) == e["sha256"], f"Changed source; refusing cleanup: {p}"
    # Recompute binary metrics from counts for every historical report and trial.
    checks = 0
    def walk(x):
        nonlocal checks
        if isinstance(x, dict):
            names = ("tp", "fp", "fn") if all(k in x for k in ("tp", "fp", "fn")) else ("true_positive", "false_positive", "false_negative")
            if all(k in x for k in names) and all(isinstance(x[k], (int, float)) for k in names):
                tp, fp, fn = [x[k] for k in names]
                expected = {"precision": tp / (tp + fp) if tp + fp else 0, "recall": tp / (tp + fn) if tp + fn else 0, "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0}
                for k, v in expected.items():
                    if k in x and isinstance(x[k], (float, int)):
                        assert abs(x[k] - v) < 0.0001, f"Inconsistent {k}: {x[k]} != {v}"
                        checks += 1
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for r in records.values():
        if r["path"].endswith(".json"):
            walk(json.loads(raw(r)))
    metrics = load(records, "docs/metrics.json")
    artifact_checks = []
    for path, expected in metrics["artifact_sha256"].items():
        p = ROOT / path.replace("\\", "/")
        actual = sha(p.read_bytes()) if p.exists() else None
        artifact_checks.append({"path": path, "recorded_sha256": expected, "current_sha256": actual, "matches_recorded": actual == expected})
    for path, record in records.items():
        if path.endswith("candidate_model_card.json"):
            card = json.loads(raw(record))
            if "artifact" in card and "sha256" in card:
                artifact = ROOT / card["artifact"].replace("\\", "/")
                actual = sha(artifact.read_bytes()) if artifact.exists() else None
                artifact_checks.append({"path": card["artifact"], "recorded_sha256": card["sha256"], "current_sha256": actual, "matches_recorded": actual == card["sha256"]})
    index["current_artifact_checks"] = artifact_checks
    index["verification"] = {"unique_evidence_files": len(records), "binary_metric_identities_checked": checks, "ledger_count": len(MODELS), "sha256_round_trip": "passed", "verified_utc": datetime.now(timezone.utc).isoformat()}
    INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(MODELS)} ledgers; {len(records)} unique evidence files; {checks} precision/recall/F1 identities; all archived bytes match SHA-256. Current artifacts matching recorded fingerprints: {sum(x['matches_recorded'] for x in artifact_checks)}/{len(artifact_checks)}.")


def refresh():
    records = records_all()
    m = load(records, "docs/metrics.json")
    head = load(records, "ml_pipeline/reports/trajectory_tuning_20261101_horizon_head/summary.json")
    mp = load(records, "ml_pipeline/reports/multipath_tuning_20261101/summary.json")
    cf = load(records, "ml_pipeline/reports/conflict_refinement_20261101/candidate_model_card.json")
    lines = ["# Flight Right: latest evaluation", "", "Classifier headline: **95.07% (270/284)** caught with at least three minutes of warning. Full served alert chain: **95.42% (271/284)**. Consolidated from preserved measurements; no retraining or fresh inference was performed.", "", "## Model inventory and best supported configuration", "", "Best means the recorded validation-selected configuration that passed its stated checks, not the largest isolated test score. Served and candidate numbers are separated below. Different tasks, corpora and metrics cannot be ranked together.", ""]
    inventory = []
    notes = {
        "trajectory_lstm": "Served baseline; selected ten-minute-head candidate remains undeployed",
        "multipath": "Archive + destination served; continue_800 candidate undeployed",
        "conflict_classifier": "27-input selected-altitude classifier served; raw threshold 0.07465646415948868",
        "conflict_filter": "refit_unweighted + raw threshold 0.07932812720537186 + veto floor 0.00928506813943386; undeployed",
    }
    for k, (title, desc) in MODELS.items():
        inventory.append([f"[{title}](evaluations/{k}.md)", notes.get(k, desc)])
    lines += [table(["Model / evaluated component", "Status / how achieved"], inventory), "", "## Trajectory: historical test split", "", "39,614 test windows; ten-minute targets available for 18,662. Rates are percentages. RMSE/mean are horizontal NM, altitude MAE is ft. Earlier horizons and every slice/seed remain in the corresponding model ledger.", ""]
    traj_rows = []
    for label, rows in [("Constant velocity", m["model1"]["baseline_per_horizon"]), ("Served residual LSTM", m["model1"]["per_horizon"]), ("Tree reference (saved predictions)", m["tree_reference"]["per_horizon"]), ("Undeployed last_head_adam_lr1e4, seed 42, epoch 4", head["finalist_test"][0]["metrics"]["per_horizon"])]:
        for r in rows:
            traj_rows.append([label, r["horizon"], r["n"], f'{r["mean_nm"]:.5f}', f'{r["rmse_nm"]:.5f}', f'{r["within_5_nm"]:.5f}', f'{r["altitude_mae_ft"]:.2f}'])
    lines += [table(["Configuration", "Horizon", "n", "Mean NM", "RMSE NM", "Within 5 NM %", "Altitude MAE ft"], traj_rows), "", "The LSTM candidate freezes the encoder, shared layers and one-/three-/five-minute heads; Adam learning rate 1e-4, SmoothL1 beta .05, validation-selected seed 42 epoch 4, confirmed at seeds 43/44. It is not a simultaneous improvement of every metric or regime. See all three LSTM studies and guards in its ledger.", "", "## Multi-path: ten-minute coverage", "", "Best-of-five is coverage of alternatives. A joint 3-D hit requires the same candidate within 5 NM and 1,000 ft. Arrivals is the existing <40 NM VABB bucket, not independent arrival labels.", ""]
    rows = []
    for label, d in [("Served archive + destination", mp["baseline_test"]), ("Undeployed continue_800 seed 0", mp["test_audits"][0]["metrics"])]:
        for group, r in d["groups"].items():
            rows.append([label, group, r["n"], f'{r["top1_mean_nm"]:.5f}', f'{r["top1_within_5nm"]:.5f}', f'{r["best5_within_5nm"]:.5f}', f'{r["top1_both"]:.5f}', f'{r["best5_both"]:.5f}'])
    cluster = m["model1b"]["route_classification"]
    lines += [table(["Configuration", "Group", "n", "Top-1 mean NM", "Top-1 5 NM %", "Best-5 5 NM %", "Top-1 3-D %", "Best-5 3-D %"], rows), "", "continue_800 extends only the ten-minute per-mode regressors: 800 along-track / 800 cross-track / 468 altitude trees. Validation-frozen, seed 0; no independent multi-seed claim. Route classifier and temperature stay fixed. Route classification and its full 40-class confusion matrix/calibration are preserved in the multi-path ledger.", "", "## Conflict: 4,690 historical test pairs, 303 positives", ""]
    def binary(label, r):
        return [label, f'{r["precision"]:.8f}', f'{r["recall"]:.8f}', f'{r["f1"]:.8f}', r.get("tn", r.get("true_negative")), r.get("fp", r.get("false_positive")), r.get("fn", r.get("false_negative")), r.get("tp", r.get("true_positive"))]
    rows = [binary("Served classifier", m["model2"]["test"]), binary("Served full chain", m["full_alert_chain"]), binary("Undeployed filtered classifier", cf["historical_test"]["classifier"]), binary("Undeployed filtered full chain", cf["historical_test"]["system"])]
    lines += [table(["Decision", "Precision", "Recall", "F1", "TN", "FP", "FN", "TP"], rows), "", "The served classifier adds selected-altitude inputs with validation threshold matched to the prior false-alarm rate. The refined proposal uses a new unweighted 400-tree depth-3 XGBoost filter (learning rate .04, minimum child weight 20, L2 20, subsample .9, seed 42) after the threshold change; the independent straight-line safety net bypasses it. Classifier early catches remain 270/284; full-chain early catches remain 271/284. The proposal retains the same detected true pairs, cuts full-chain FP 478 to 459, and changes false tier-1 alerts 20 to 19 while preserving 28 real tier-1 alerts. Existing full-chain FN remain 13. This is repeated historical-benchmark exploration, not a guarantee on future traffic.", "", "## Speech: latest accepted result per checkpoint and corpus", "", "WER is percent; lower is better. Columns distinguish raw and spoken-numeral-normalized WER. Corpus contamination limits comparison. Latest here means the latest accepted record for that model/corpus, even when another model has a more recent report.", ""]
    latest = {}
    for path, r in sorted(records.items()):
        if not Path(path).name.startswith("voice_eval") or "rejected" in path:
            continue
        d = json.loads(raw(r))
        for v in d["models"].values():
            key = asr_key(v["model_id"])
            if key:
                for corpus, metrics in v["corpora"].items():
                    latest[key, corpus] = (d["measured_at_utc"], metrics)
    rows = []
    for (key, corpus), (date, r) in sorted(latest.items()):
        rows.append([MODELS[key][0], corpus, date[:10], r.get("clips"), r.get("wer", "n/a"), r.get("wer_numerals_spoken", "n/a"), r.get("held_out", "see ledger")])
    lines += [table(["Checkpoint", "Corpus", "Measured", "Clips", "WER %", "Spoken-numeral WER %", "Basis / limitation"], rows), "", "Own P1 model: LoRA rank 32 on Whisper-small, real ATCOSIM/UWB training, exported to CTranslate2 int8_float16; common English beam-5 decoder (`fw1-beam5-v1`). Full training checkpoint history is in its ledger. Svarah measures general Indian English, not ATC. Cached transcription re-scoring does not constitute fresh latency benchmarking. No completed P2/accent model with test scores was found.", "", "## Other evaluated components", "", "Resolution: 45 classifier-triggered tier-1 encounters (27 real / 18 false), 1,170 simulated manoeuvres; 1 unsafe and 923 ineffective rejected, 0 secondary-conflict rejections; 46 instructions across 21 encounters, 24 without options. 35 instructions on real conflicts, 11 on false alarms. The harness lacks surrounding traffic; zero secondary rejections does not validate runtime domino checks. Classification F1 is inapplicable.", "", "Extractor with human transcripts on ATCO2 clean: 77.42% clearance accuracy (31 eligible), 93.9% callsign accuracy with proxy aircraft lists (328 eligible). These are upper-bound parser results, not ASR scores. The rejected number rule is excluded from latest accepted results. Latest November 2 chain check is an oracle-text replay demonstration, not measured microphone/ASR accuracy.", "", "Alert feed: replay interruptions 680 to 179 (73.7%) and 909 to 235 (74.1%), zero pairs lost in both. This measures display suppression. Path-confidence all-pairs policy was rolled back; its trials, replay and source remain in its ledger. Indic Parler TTS and Silero VAD have no recorded objective model-quality evaluation; no numbers are invented for them.", "", "## Provenance and maintenance", "", "Original served-model refresh: 2026-10-30. Candidate studies: 2026-11-01. Latest chain demonstration: 2026-11-02. Consolidation: 2026-11-09. Model fingerprints are checked against recorded sources; consolidation does not make old measurements newly measured results.", "", "[Source inventory and cleanup audit](evaluations/source_inventory.json) contains every discovered evaluation source, model mapping, checksum, preservation commit and deletion status. Each model ledger includes full original evidence. Current served models, selected candidate packages, original data and canonical evaluation inputs are retained. Retired trial weights and regenerable intermediates may be removed after recording their provenance and results in the model ledger.", "", "```powershell", "venv\\Scripts\\python.exe scripts/consolidate_evaluations.py --verify", "# Add a newly generated evaluation (choose all affected model keys from the inventory):", "venv\\Scripts\\python.exe scripts/consolidate_evaluations.py --ingest PATH --models MODEL_KEY", "# Restore archived inputs needed by an older report script (does not overwrite):", "venv\\Scripts\\python.exe scripts/consolidate_evaluations.py --restore ORIGINAL_PATH", "```", "", "When ingesting new work, update the latest-result selection in `refresh()` for newly selected trajectory/conflict configurations. Speech latest results update automatically per checkpoint/corpus. Never promote a candidate by maximizing its historical test score.", ""]
    (ROOT / "docs/evaluation.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def cleanup():
    verify()
    index = json.loads(INDEX.read_text())
    assert git("merge-base", "--is-ancestor", index["checkpoint"], "origin/fine-tuning") == ""
    count = 0
    for e in index["sources"]:
        if e["cleanup"]:
            p = (ROOT / e["path"]).resolve()
            assert p.is_relative_to(ROOT.resolve()), p
            if p.exists():
                p.unlink()  # individual verified files only; never recursive deletion
                count += 1
            e["status"] = "consolidated_original_removed"
    index["cleanup_verified_utc"] = datetime.now(timezone.utc).isoformat()
    INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Removed {count} individually verified history files; exact originals remain in model ledgers and pushed checkpoint.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    for arg in ["build", "verify", "cleanup", "refresh"]:
        group.add_argument("--" + arg, action="store_true")
    group.add_argument("--restore")
    group.add_argument("--ingest", type=Path)
    p.add_argument("--checkpoint")
    p.add_argument("--models", nargs="+", choices=MODELS)
    a = p.parse_args()
    if a.build:
        assert a.checkpoint, "--checkpoint required"
        build(a.checkpoint)
    elif a.verify:
        verify()
    elif a.cleanup:
        cleanup()
    elif a.refresh:
        refresh()
    elif a.restore:
        r = records_all()[a.restore]
        assert sha(raw(r)) == r["sha256"], "Corrupt archived source"
        target = (ROOT / a.restore).resolve()
        assert target.is_relative_to(ROOT.resolve()) and not target.exists(), "Unsafe path or existing file"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw(r))
        print(f"Restored {a.restore}")
    elif a.ingest:
        assert a.models, "--models required"
        r = make_record(a.ingest.resolve())
        for key in a.models:
            payload = read_ledger(key)
            assert all(x["path"] != r["path"] for x in payload["records"]), "Use a new run path; do not overwrite history"
            payload["records"].append(r)
            payload["records"].sort(key=lambda x: x["path"])
            write_ledger(key, payload)
        index = json.loads(INDEX.read_text())
        index["sources"].append({"path": r["path"], "models": a.models, "sha256": r["sha256"], "bytes": r["bytes"], "cleanup": False, "status": "ingested_new_run"})
        INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        refresh()
        verify()


if __name__ == "__main__":
    main()
