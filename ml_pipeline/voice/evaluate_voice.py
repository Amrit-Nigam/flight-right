"""The speech numbers, measured (plan 4.5 and 6): one command, dated JSON, nothing typed by hand.

    python ml_pipeline/voice/evaluate_voice.py                     # every model in MODELS
    python ml_pipeline/voice/evaluate_voice.py --models human      # extractor on human transcripts only

THE FOUR METRICS, in the order the plan ranks them (plan 4.5):
1. Clearance accuracy (headline): of the transmissions whose annotators tagged a clearance
   our system can use (climb / descend / heading / direct / speed) AND whose aircraft is
   known, how many became completely correct -- right aircraft, right action, right value.
2. Callsign accuracy, twice: list-free (the words alone -> a written callsign) and matched
   against the aircraft list (plan 6.2). The gap is our own measured matching gain.
3. Action and value accuracy.
4. Word error rate -- for comparison with published work only, never the headline.
Plus real-time factor. Reported PER CORPUS, never averaged across clean and noisy.

WHERE THE TRUTH COMES FROM, per corpus, and what may be claimed from it:
- ATCO2 1 h test set: the official ATCO2 XML annotations (atco2.org, free). They are the
  corpus authors' annotations; only 2 of 877 are flagged as tag-verified, so they are
  "annotations", not "gold" (docs/claims.md). The aircraft identity is the annotators'
  speaker label on the pilot's transmission; a controller's transmission inherits it when
  its tagged callsign matches the pilot's in the same recording.
  The AIRCRAFT LIST is a proxy: every identity annotated on the same airport, frequency and
  day. It stands in for a surveillance feed and is labelled so (plan 6.2).
  Scored on the 762 clean clips; the 109 clips that are inside jlvdoorn's training data are
  reported separately and never as held out.
- ATCOSIM held-out speakers and UWB-ATCC held-out recordings: word error rate, plus
  clearance AGREEMENT: the extractor run on the human reference transcript is treated as
  the truth for the extractor run on the recognised text. That isolates what the recogniser
  costs; it is not a labelled accuracy and is never called one.
- Generated (text-to-speech) audio is never scored (revised speech plan: never test on
  generated audio).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import jiwer
import numpy as np
import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE  # noqa: E402
from ml_pipeline.voice.callsigns import match  # noqa: E402
from ml_pipeline.voice.extract import asr_confidence_from_logprob, extract, gold_action  # noqa: E402
from ml_pipeline.voice.text_norm import normalise  # noqa: E402
from ml_pipeline.utils.clearance import Clearance  # noqa: E402

REPORTS = ROOT / "ml_pipeline/reports"
MODELS = {
    # role -> model id. The published models, exactly as plan 4.1 lists them.
    "ships_in_demo": "jlvdoorn/whisper-large-v3-atco2-asr-atcosim",
    "held_out_measurement": "jlvdoorn/whisper-medium-atcosim",
    "untouched_baseline": "openai/whisper-medium",
}
# What each model is known to have trained on, so every score says whether it is held out.
# jlvdoorn cards: "fine-tuned on the None/unknown dataset"; the corpus names in the model ids
# and Phase 2.5's waveform check are the evidence. ATCOSIM in the jlvdoorn mirror carries all
# ten speakers, so our held-out ATCOSIM speakers are NOT held out for those two models.
HELD_OUT = {
    "jlvdoorn/whisper-large-v3-atco2-asr-atcosim": {
        "atco2_clean": "clip-held-out (same airports and days as its ATCO2 training clips)",
        "atco2_contaminated": "NOT held out: these exact recordings are in its training data (Phase 2.5)",
        "atcosim_heldout_speakers": "NOT held out: trained on all ten ATCOSIM speakers",
        "uwb_heldout_recordings": "held out (UWB-ATCC not in its training corpus)",
        "svarah_indian_english": "held out"},
    "jlvdoorn/whisper-medium-atcosim": {
        "atco2_clean": "held out (never trained on ATCO2)", "atco2_contaminated": "held out (never trained on ATCO2)",
        "atcosim_heldout_speakers": "NOT held out: trained on ATCOSIM", "uwb_heldout_recordings": "held out",
        "svarah_indian_english": "held out"},
    "openai/whisper-medium": {c: "held out as far as is known (web-scale training data, undisclosed)" for c in
                              ["atco2_clean", "atco2_contaminated", "atcosim_heldout_speakers",
                               "uwb_heldout_recordings", "svarah_indian_english"]},
}
# Our model's own starting point, untouched: the fair baseline for "what did ATC fine-tuning do to
# Indian-accented English" (Svarah was released in 2023, after Whisper's 2022 training data).
HELD_OUT["openai/whisper-small"] = dict(HELD_OUT["openai/whisper-medium"])
OWN_MODEL = {"atco2_clean": "held out (no ATCO2 audio in training)",
             "atco2_contaminated": "held out (no ATCO2 audio in training)",
             "atcosim_heldout_speakers": "held out by speaker (sm3, zf3, gm2 never trained on)",
             "uwb_heldout_recordings": "held out by recording", "svarah_indian_english": "held out"}
ID = re.compile(r"atco2/atco2_test-set-1h_(.+)-([A-Z]+)__(\d{6})-(\d{6})$")
DIGIT_WORDS = "zero one two three four five six seven eight nine".split()


def spoken_digits(text: str) -> str:
    """Digits written as numerals, spoken digit by digit ("350" -> "three five zero").

    A second, gentler WER for models that were never taught ATC transcription conventions,
    so the untouched baseline is not scored as wrong merely for writing numerals."""
    return " ".join(" ".join(DIGIT_WORDS[int(c)] for c in w) if w.isdigit() else w for w in text.split())


def wer(refs: list[str], hyps: list[str]) -> float:
    pairs = [(r, h or "<empty>") for r, h in zip(refs, hyps) if r]
    return round(100 * jiwer.wer([r for r, _ in pairs], [h for _, h in pairs]), 2) if pairs else float("nan")


def gold_atco2() -> pd.DataFrame:
    """The 871 ATCO2 test clips joined to their official annotations."""
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    notes = pd.read_parquet(CACHE / "atco2_annotations.parquet")
    clips = manifest[manifest.corpus == "atco2"].copy()
    parts = clips.uid.str.extract(ID)
    clips["recording"], clips["end"] = parts[0], parts[3].astype(float) / 100
    notes["end_r"], clips["end_r"] = notes.end.round(2), clips.end.round(2)
    frame = clips.merge(notes.drop(columns=["text", "end"]), left_on=["recording", "end_r"],
                        right_on=["recording", "end_r"], how="left")
    assert len(frame) == len(clips), "an ATCO2 clip joined to more than one annotation"

    def code_of(label):
        label = str(label or "")
        if label.startswith(("ATCO", "UNK")) or not re.fullmatch(r"[A-Z0-9\-]{3,}", label):
            return None
        return label.replace("-", "")

    frame["gold_callsign"] = frame.callsign.map(lambda s: normalise(s) or None)
    frame["truth_code"] = [code_of(l) if s == "B" else None for s, l in zip(frame.speaker, frame.speaker_label)]
    pilots = frame.dropna(subset=["truth_code", "gold_callsign"])
    for i, row in frame[frame.truth_code.isna() & frame.gold_callsign.notna()].iterrows():
        same = pilots[pilots.recording == row.recording]
        best = max(((fuzz.ratio(row.gold_callsign, p.gold_callsign), p.truth_code) for p in same.itertuples()),
                   default=(0, None))
        if best[0] >= 80:
            frame.at[i, "truth_code"] = best[1]
    frame["sector_day"] = frame.recording.str.replace(r"_\d{6}$", "", regex=True)
    lists = frame.dropna(subset=["truth_code"]).groupby("sector_day").truth_code.agg(lambda s: sorted(set(s)))
    frame["candidates"] = frame.sector_day.map(lists).map(lambda v: v if isinstance(v, list) else [])
    gold = [gold_action(c, v) for c, v in zip(frame.command, frame.value)]
    frame["gold_action"] = [g[0] for g in gold]
    frame["gold_value"] = [g[1] for g in gold]
    frame["gold_fix"] = [g[2] for g in gold]
    # Annotation tags the project's own Clearance contract rejects as physically impossible
    # (a 6-knot "speed instruction" is the wind report; a level of 3002 ft read off a
    # squawk code passes, so this catches only the impossible ones). Scored both ways.
    frame["gold_plausible"] = [
        pd.notna(a) and not Clearance(icao24="x", action=a, value=(None if pd.isna(v) else float(v)),
                                      fix=(f if isinstance(f, str) else None)).problems()
        for a, v, f in zip(frame.gold_action, frame.gold_value, frame.gold_fix)]
    return frame


def _action_right(ex, action, value, fix) -> tuple[bool, bool]:
    for a in ex.all_actions or []:
        if a["action"] == action:
            if action == "DIRECT":
                return True, bool(fix) and bool(a["fix"]) and fuzz.ratio(a["fix"], fix) >= 85
            return True, value is not None and a["value"] is not None and abs(a["value"] - value) < 1e-6
    return False, False


def score_atco2(frame: pd.DataFrame, hyps: pd.Series, logprobs: pd.Series | None) -> dict:
    rows = []
    for (_, g), hyp, lp in zip(frame.iterrows(), hyps, logprobs if logprobs is not None else [None] * len(frame)):
        has_code, has_action = pd.notna(g.truth_code), pd.notna(g.gold_action)
        ex = extract(hyp if isinstance(hyp, str) else "", asr_confidence_from_logprob(lp))
        matched = match(ex.text, g.candidates)["code"] if g.candidates else None
        value = g.gold_value if pd.notna(g.gold_value) else None
        fix = g.gold_fix if isinstance(g.gold_fix, str) else None
        act_ok, val_ok = _action_right(ex, g.gold_action, value, fix) if has_action else (False, False)
        rows.append(dict(has_code=has_code, has_action=has_action, plausible=bool(g.gold_plausible),
                         listfree=ex.callsign_code == g.truth_code, listed=matched == g.truth_code,
                         act=act_ok, val=val_ok, conf=ex.confidence, n_candidates=len(g.candidates)))
    r = pd.DataFrame(rows)
    coded, acted = r[r.has_code], r[r.has_action]
    both = r[r.has_code & r.has_action]
    full = both.listed & both.act & both.val

    def pct(s):
        return round(100 * float(s.mean()), 2) if len(s) else float("nan")

    plausible = both[both.plausible]
    full_plausible = plausible.listed & plausible.act & plausible.val
    conf_right = both.conf[full].mean() if full.any() else float("nan")
    conf_wrong = both.conf[~full].mean() if (~full).any() else float("nan")
    return {
        "clearance_accuracy": pct(full), "clearance_n": int(len(both)),
        "clearance_accuracy_plausible_tags": pct(full_plausible), "clearance_n_plausible_tags": int(len(plausible)),
        "callsign_accuracy_list_free": pct(coded.listfree), "callsign_accuracy_with_list": pct(coded.listed),
        "callsign_n": int(len(coded)), "mean_aircraft_list_size": round(float(coded.n_candidates.mean()), 1) if len(coded) else None,
        "action_accuracy": pct(acted.act), "value_accuracy": pct(acted.act & acted.val), "action_n": int(len(acted)),
        "confidence_when_right": round(float(conf_right), 3), "confidence_when_wrong": round(float(conf_wrong), 3),
    }


def agreement(refs: list[str], hyps: list[str]) -> dict:
    """Extractor on the recognised text vs extractor on the human transcript."""
    n = right = 0
    for ref, hyp in zip(refs, hyps):
        truth = extract(ref)
        if not truth.action:
            continue
        got = extract(hyp or "")
        n += 1
        right += (got.action == truth.action and got.value == truth.value and got.fix == truth.fix
                  and got.callsign_code == truth.callsign_code)
    return {"clearance_agreement": round(100 * right / n, 2) if n else float("nan"), "clearances_in_reference": n}


def evaluate_model(model_id: str, manifest: pd.DataFrame, gold: pd.DataFrame, device: str) -> dict:
    from ml_pipeline.voice.transcribe import transcribe_rows
    rows = manifest[(manifest.split == "test") & manifest.corpus.isin(["atco2", "atcosim", "uwb", "svarah"])]
    got = transcribe_rows(model_id, rows, device=device).set_index("uid")
    out = {"model_id": model_id, "quantisation": got.quantisation.dropna().iloc[0],
           "asr_version": got.asr_version.dropna().iloc[0], "corpora": {}}
    corpora = ["atco2_clean", "atco2_contaminated", "atcosim_heldout_speakers", "uwb_heldout_recordings"]
    if (rows.corpus == "svarah").any():
        corpora.append("svarah_indian_english")   # real Indian voices; general English, not ATC
    for corpus in corpora:
        if corpus.startswith("atco2"):
            sub = gold[gold.contaminated == (corpus == "atco2_contaminated")]
        else:
            sub = rows[rows.corpus == corpus.split("_")[0]]
        hyp = got.loc[sub.uid]
        norm = [normalise(h) for h in hyp.hyp.fillna("")]
        if corpus.startswith("svarah"):
            norm = [normalise(h) for h in hyp.hyp.fillna("")]
            out["corpora"][corpus] = {"clips": int(len(sub)), "wer": wer(list(sub.text), norm),
                                      "wer_numerals_spoken": wer([spoken_digits(t) for t in sub.text],
                                                                 [spoken_digits(h) for h in norm]),
                                      "real_time_factor": round(float(hyp.seconds.sum() / hyp.audio_seconds.sum()), 4),
                                      "held_out": HELD_OUT.get(model_id, OWN_MODEL).get(corpus, "unknown"),
                                      "note": "general Indian English, not ATC: accent and vocabulary are confounded",
                                      # Svarah has no speaker id; the speaker's first language is the grouping
                                      # (Marathi is Mumbai's language).
                                      "wer_by_first_language": {
                                          str(g): {"clips": int((sub.group == g).sum()),
                                                   "wer": wer(list(sub.text[sub.group == g]),
                                                              [n for n, keep in zip(norm, sub.group == g) if keep])}
                                          for g in sorted(sub.group.dropna().unique())}}
            print(f"  {model_id} {corpus}: {out['corpora'][corpus]}", flush=True)
            continue
        entry = {"clips": int(len(sub)), "audio_hours": round(float(hyp.audio_seconds.sum()) / 3600, 3),
                 "wer": wer(list(sub.text), norm),
                 "wer_numerals_spoken": wer(list(sub.text), [spoken_digits(h) for h in norm]),
                 "real_time_factor": round(float(hyp.seconds.sum() / hyp.audio_seconds.sum()), 4)}
        entry["held_out"] = HELD_OUT.get(model_id, OWN_MODEL).get(corpus, "unknown")
        if corpus.startswith("atco2"):
            entry.update(score_atco2(sub, hyp.hyp.fillna(""), hyp.avg_logprob))
        else:
            entry.update(agreement(list(sub.text), norm))
        out["corpora"][corpus] = entry
        print(f"  {model_id} {corpus}: {entry}", flush=True)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", default="human,all", help="comma list of ids, 'human', 'all'")
    p.add_argument("--extra", default="", help="more model ids or local model dirs, comma separated")
    p.add_argument("--device", default="auto")
    args = p.parse_args()
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    gold = gold_atco2()
    report = {"measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "truth": {"atco2": "official ATCO2 XML annotations (authors' annotations; 2/877 tag-verified)",
                        "aircraft_list": "proxy: identities annotated on the same airport, frequency and day",
                        "atcosim_uwb": "agreement with the extractor on the human transcript, not labelled accuracy"},
              "atco2_clips": {"clean": int((~gold.contaminated).sum()), "contaminated": int(gold.contaminated.sum()),
                              "with_aircraft_identity": int(gold.truth_code.notna().sum()),
                              "with_usable_clearance": int(gold.gold_action.notna().sum()),
                              "clearance_types": gold.gold_action.value_counts().to_dict()},
              "models": {}}
    wanted = [m for m in args.models.split(",") if m]
    if "all" in wanted:
        wanted = [w for w in wanted if w != "all"] + list(MODELS.values())
    wanted += [m for m in args.extra.split(",") if m]
    for model in dict.fromkeys(wanted):
        if model == "human":
            # The ceiling: the extractor and matcher on the annotators' own transcripts.
            human = {}
            for name, contaminated in [("atco2_clean", False), ("atco2_contaminated", True)]:
                sub = gold[gold.contaminated == contaminated]
                human[name] = {"clips": int(len(sub)), **score_atco2(sub, sub.text_raw, None)}
            report["models"]["human_transcript"] = {"model_id": "human transcript (upper bound for the extractor)",
                                                    "corpora": human}
            print("  human transcripts:", human, flush=True)
            continue
        role = next((r for r, m in MODELS.items() if m == model), "additional")
        report["models"][f"{role}:{model}"] = evaluate_model(model, manifest, gold, args.device)
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"voice_eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(report, indent=2, default=float))
    print("wrote", path)


if __name__ == "__main__":
    main()
