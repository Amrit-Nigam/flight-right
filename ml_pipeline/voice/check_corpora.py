"""Phase 2.4 and 2.5 — what the speech corpora actually contain, measured.

Two questions, both of which decide what Phase 4 and Phase 6 are allowed to claim:

**2.4 — does the ATCO2 test set carry the labels Phase 6 needs?**
Phase 6 turns a transcript into `callsign | action | value` and has to be scored against
something. This checks whether `Jzuluaga/atco2_corpus_1h` carries those fields.

**2.5 — was `whisper-large-v3-atco2-asr-atcosim` trained on its own test set?**
Its training corpus is `jlvdoorn/atco2-asr-atcosim`. If the 871 evaluation clips are
inside that corpus, the model card's 22.27 WER is not a held-out measurement and may not
be quoted as one.

**Why the audio is compared and not only the transcript.** Matching transcripts overstates
the overlap: short generic phrases ("roger", "good bye") recur across corpora by
coincidence, spoken by different people. Matching decoded waveforms settles it - a
correlation of 1.0 means literally the same recording, re-encoded. Both numbers are
reported, because the gap between them is the point.

**No `datasets` dependency, deliberately.** `datasets` pins `fsspec<=2026.6.0` while this
environment runs 2026.7.0, and **torch depends on fsspec** - installing it would downgrade
a package underneath the training stack. `huggingface_hub` plus pandas reads the same
parquet files with nothing new installed.

Run:  python ml_pipeline/voice/check_corpora.py
Writes a dated JSON beside the other reports; no number is ever typed into a document.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import ssl
import sys
import tarfile
import urllib.request
import warnings
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import certifi
import numpy as np
import pandas as pd
import soundfile as sf
from huggingface_hub import HfApi, hf_hub_download

warnings.filterwarnings("ignore")

# The official ATCO2 release. Free, no registration - and it carries the callsign,
# command and value annotations the HuggingFace mirror leaves out.
#
# NOTE: this URL fails certificate verification against Windows' default trust store and
# succeeds against certifi's. That is why the context below is explicit: the site was
# originally written off as unreachable when the real fault was our CA bundle.
ANNOTATION_URL = "https://www.atco2.org/data/atco2_1h_xml-tar.gz"

# Tags look like [#callsign]Oscar Kilo Papa Mike Bravo[/#callsign].
TAG_PATTERN = re.compile(r"\[#(\w+)\](.*?)\[/#\1\]", re.S)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORTS = PROJECT_ROOT / "ml_pipeline" / "reports"

TEST_REPO = "Jzuluaga/atco2_corpus_1h"
TRAIN_REPO = "jlvdoorn/atco2-asr-atcosim"

# Above this correlation the two clips are the same recording. In practice the
# distribution is bimodal - genuine matches land at 1.000 and coincidences below 0.25 -
# so the exact cut does not matter.
SAME_RECORDING_CORRELATION = 0.95

# The fields Phase 6 needs in order to score callsign/action/value extraction.
REQUIRED_LABEL_FIELDS = ("callsign", "action", "value")

# id shape: atco2_test-set-1h_<ICAO>_<position>_<freq>MHz_<yyyymmdd>_<hhmmss>-<x>__<start>-<end>
ID_PATTERN = re.compile(r"atco2_test-set-1h_([A-Z]{4})_(.+?)_(\d+_\d+)MHz_(\d{8})_(\d{6})")


def normalise(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace - the standard WER normalisation."""
    lowered = re.sub(r"[^a-z0-9 ]", " ", str(text).lower())
    return re.sub(r"\s+", " ", lowered).strip()


def waveform(raw: bytes) -> np.ndarray:
    """Decode to a mono float waveform, so re-encoding cannot hide a match."""
    samples, _ = sf.read(io.BytesIO(raw), dtype="float32")
    return samples.mean(axis=1) if samples.ndim > 1 else samples


def correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Absolute Pearson correlation over the overlapping prefix of two clips."""
    length = min(len(a), len(b))
    if length < 400:
        return 0.0
    left, right = a[:length], b[:length]
    if left.std() == 0 or right.std() == 0:
        return 0.0
    return abs(float(np.corrcoef(left, right)[0, 1]))


def load_test() -> pd.DataFrame:
    api = HfApi()
    files = [f for f in api.list_repo_files(TEST_REPO, repo_type="dataset") if f.endswith(".parquet")]
    frame = pd.concat([pd.read_parquet(hf_hub_download(TEST_REPO, f, repo_type="dataset")) for f in files],
                      ignore_index=True)
    frame["normalised"] = frame["text"].map(normalise)
    return frame


def load_training() -> dict[str, list[bytes]]:
    """Map normalised transcript -> every training clip carrying it."""
    api = HfApi()
    files = [f for f in api.list_repo_files(TRAIN_REPO, repo_type="dataset") if f.endswith(".parquet")]
    by_text: dict[str, list[bytes]] = {}
    counts = {"train": 0, "validation": 0}
    for name in files:
        frame = pd.read_parquet(hf_hub_download(TRAIN_REPO, name, repo_type="dataset"))
        split = "train" if "/train" in name else "validation"
        counts[split] += len(frame)
        for text, audio in zip(frame["text"], frame["audio"]):
            by_text.setdefault(normalise(text), []).append(audio["bytes"])
    by_text["__counts__"] = counts            # carried out of band; popped by the caller
    return by_text


def official_annotations() -> pd.DataFrame:
    """Fetch and parse the official ATCO2 XML annotations.

    Returns one row per annotated segment, with the callsign / command / value pulled out
    of the inline tags, plus `speaker_label` - which on the pilot side is the REAL aircraft
    identity and is therefore ground truth for callsign matching in Phase 6.
    """
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(ANNOTATION_URL, context=context, timeout=120) as response:
        payload = response.read()

    rows = []
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        for member in tar.getnames():
            if not member.endswith(".xml"):
                continue
            root = ET.fromstring(tar.extractfile(member).read().decode("utf8", "ignore"))
            for segment in root.findall("segment"):
                text = segment.findtext("text") or ""
                fields = {key: value.strip() for key, value in TAG_PATTERN.findall(text)}
                tags = segment.find("tags")
                rows.append({
                    "recording": member.replace(".xml", ""),
                    "start": float(segment.findtext("start") or 0),
                    "end": float(segment.findtext("end") or 0),
                    "speaker": segment.findtext("speaker"),
                    "speaker_label": segment.findtext("speaker_label"),
                    "callsign": fields.get("callsign"),
                    "command": fields.get("command"),
                    "value": fields.get("value"),
                    "text": TAG_PATTERN.sub(r"\2", text).strip(),
                    "correct_transcript": int(tags.findtext("correct_transcript") or 0) if tags is not None else 0,
                    "correct_tagging": int(tags.findtext("correct_tagging") or 0) if tags is not None else 0,
                })
    return pd.DataFrame(rows)


def question_2_4(test: pd.DataFrame) -> dict:
    """Does the test set carry callsign / action / value, and what IS recoverable?"""
    columns = list(test.columns)
    present = [f for f in REQUIRED_LABEL_FIELDS if any(f in c.lower() for c in columns)]

    parsed = [ID_PATTERN.match(str(i)) for i in test["id"]]
    meta = pd.DataFrame(
        [(m.group(1), m.group(2), m.group(3) + "MHz", m.group(4)) if m else (None, None, None, None)
         for m in parsed],
        columns=["icao", "position", "frequency", "date"])

    finding = {
        "rows": int(len(test)),
        "columns": columns,
        "required_label_fields": list(REQUIRED_LABEL_FIELDS),
        "label_fields_present": present,
        "huggingface_mirror_has_labels": len(present) == len(REQUIRED_LABEL_FIELDS),
        "total_audio_minutes": round(float(test["duration"].sum()) / 60.0, 1),
        # Recoverable from the id even though there are no label columns.
        "ids_parsed": int(meta["icao"].notna().sum()),
        "airports": meta["icao"].value_counts().to_dict(),
        "distinct_recordings": int(len(meta.dropna().drop_duplicates())),
    }

    # The mirror has no labels, but the official release does. Hand-labelling is only
    # needed if this fails.
    try:
        annotations = official_annotations()
    except Exception as failure:                                   # noqa: BLE001
        finding["official_annotations"] = {"available": False, "error": type(failure).__name__}
        return finding

    has_all = annotations[["callsign", "command", "value"]].notna().all(axis=1)
    hf_recordings = set(test["id"].str.extract(r"atco2_test-set-1h_(.+?)__\d", expand=False)
                        .dropna().str.rstrip("-AB"))
    finding["official_annotations"] = {
        "available": True,
        "url": ANNOTATION_URL,
        "recordings": int(annotations["recording"].nunique()),
        "segments": int(len(annotations)),
        "with_callsign": int(annotations["callsign"].notna().sum()),
        "with_command": int(annotations["command"].notna().sum()),
        "with_value": int(annotations["value"].notna().sum()),
        "with_all_three": int(has_all.sum()),
        # The pilot's speaker_label is the real aircraft identity -> ground truth for
        # the callsign matching that is Phase 6's actual contribution.
        "pilot_identities": int(annotations.loc[annotations["speaker"] == "B",
                                                "speaker_label"].notna().sum()),
        "recordings_matching_hf_clips": len({r for r in hf_recordings
                                             if r in set(annotations["recording"])}),
        "verified_transcript": int(annotations["correct_transcript"].sum()),
        "verified_tagging": int(annotations["correct_tagging"].sum()),
        "top_commands": dict(Counter(annotations["command"].dropna().str.lower()).most_common(10)),
    }
    return finding


def question_2_5(test: pd.DataFrame, training: dict[str, list[bytes]]) -> dict:
    """How much of the test set is inside the training corpus, by text and by audio."""
    counts = training.pop("__counts__")
    text_match = test["normalised"].isin(training.keys())

    # Byte comparison first: cheap, and a byte match is proof on its own.
    test_hashes = test["audio"].map(lambda a: hashlib.md5(a["bytes"]).hexdigest())
    train_hashes = {hashlib.md5(b).hexdigest() for clips in training.values() for b in clips}

    rows = []
    for _, row in test[text_match].iterrows():
        clip = waveform(row["audio"]["bytes"])
        best = max((correlation(clip, waveform(b)) for b in training[row["normalised"]]), default=0.0)
        rows.append({"id": row["id"],
                     "words": len(row["normalised"].split()),
                     "duration": float(row["duration"]),
                     "correlation": best,
                     "same_recording": bool(best > SAME_RECORDING_CORRELATION)})
    matched = pd.DataFrame(rows)
    same = int(matched["same_recording"].sum()) if len(matched) else 0

    by_length = {}
    if len(matched):
        for low, high, label in [(1, 3, "1-3 words"), (4, 5, "4-5 words"),
                                 (6, 9, "6-9 words"), (10, 999, "10+ words")]:
            slice_ = matched[(matched.words >= low) & (matched.words <= high)]
            if len(slice_):
                by_length[label] = {"text_matched": int(len(slice_)),
                                    "same_recording": int(slice_["same_recording"].sum())}

    contaminated = set(matched.loc[matched["same_recording"], "id"]) if len(matched) else set()
    return {
        "train_rows": counts["train"],
        "validation_rows": counts["validation"],
        "test_clips": int(len(test)),
        "text_matched": int(text_match.sum()),
        "text_matched_percent": round(100.0 * float(text_match.mean()), 1),
        "byte_identical": int(test_hashes.isin(train_hashes).sum()),
        "same_recording": same,
        "same_recording_percent": round(100.0 * same / len(test), 1),
        "clean_clips": int(len(test)) - same,
        "by_transcript_length": by_length,
        "contaminated_ids": sorted(contaminated),
    }


def main() -> int:
    print("=" * 88)
    print("PHASE 2.4 / 2.5 -- what the speech corpora actually contain")
    print("=" * 88)

    test = load_test()
    training = load_training()

    q24 = question_2_4(test)
    print(f"\n2.4  {TEST_REPO}: {q24['rows']} rows, {q24['total_audio_minutes']} minutes")
    print(f"     columns: {q24['columns']}")
    print(f"     label fields present {q24['label_fields_present']} of {q24['required_label_fields']}")
    print(f"     -> HuggingFace mirror carries labels: {q24['huggingface_mirror_has_labels']}")
    print(f"     recoverable from the id: {q24['ids_parsed']}/{q24['rows']} parsed, "
          f"{len(q24['airports'])} airports, {q24['distinct_recordings']} distinct recordings")
    for icao, n in q24["airports"].items():
        print(f"       {icao}  {n}")
    official = q24.get("official_annotations", {})
    if official.get("available"):
        print(f"\n     OFFICIAL ANNOTATIONS: {official['segments']} segments over "
              f"{official['recordings']} recordings")
        print(f"       callsign {official['with_callsign']} | command {official['with_command']} "
              f"| value {official['with_value']} | all three {official['with_all_three']}")
        print(f"       pilot identities (ground truth for matching): {official['pilot_identities']}")
        print(f"       recordings matching the HF clips: {official['recordings_matching_hf_clips']}")
        print(f"       verified transcript {official['verified_transcript']} | "
              f"verified tagging {official['verified_tagging']}  <- read the caveat")
        print(f"       -> HAND-LABELLING NOT REQUIRED")
    else:
        print(f"\n     OFFICIAL ANNOTATIONS UNAVAILABLE ({official.get('error')}) "
              f"-> hand-labelling required")

    q25 = question_2_5(test, training)
    print(f"\n2.5  training corpus {TRAIN_REPO}: "
          f"{q25['train_rows']} train + {q25['validation_rows']} validation (no test split)")
    print(f"     transcript match      : {q25['text_matched']} of {q25['test_clips']} "
          f"({q25['text_matched_percent']}%)  <- OVERSTATES, generic phrases coincide")
    print(f"     byte-identical audio  : {q25['byte_identical']}  <- UNDERSTATES, re-encoding changes bytes")
    print(f"     SAME RECORDING (waveform): {q25['same_recording']} "
          f"({q25['same_recording_percent']}%)  <- the real contamination")
    print(f"     clean clips remaining : {q25['clean_clips']}")
    for label, block in q25["by_transcript_length"].items():
        print(f"       {label:10} text-matched {block['text_matched']:4d}  "
              f"same recording {block['same_recording']:4d}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"voice_corpora_{stamp}.json"
    out.write_text(json.dumps({"measured_at_utc": datetime.now(timezone.utc).isoformat(),
                               "question_2_4": q24, "question_2_5": q25}, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
