"""Write Mumbai ATC transmissions from our own recordings, with the answer already known.

    python ml_pipeline/voice/mumbai_scripts.py

Step 2 of the revised speech plan. Text-to-speech (synthesize.py) will read these aloud in
Indian-accented English. Because this script writes the words, every clip's correct
transcript and correct clearance are known exactly: no transcription work, ever.

WHAT IS REAL AND WHAT IS NOT, per field (plan rule 7: derived is fine, invented is banned
from any number -- and generated audio is never used as a test set):
- callsign: REAL. Every callsign is an aircraft in our 35 OpenSky sessions over Mumbai.
- CLIMB / DESCEND level: DERIVED from what that aircraft actually did. It is the level the
  aircraft later held for at least 60 s, rounded to 1,000 ft, issued while it was still at
  least 2,000 ft away from it -- the same "read the clearance out of the truth" rule as the
  plan 7.1 oracle.
- TURN heading: DERIVED. The track the aircraft settled on (steady within 5 deg for 60 s)
  after a change of at least 20 deg, rounded to 5 deg.
- SPEED value: NOT OBSERVABLE. ADS-B carries ground speed, not the indicated airspeed a
  controller assigns, so speed instructions use standard terminal values (160-280 kt) and
  are marked value_source = "standard phraseology value".
- DIRECT: not generated. The only Mumbai fix names in the repository are mock map markers
  with no source (FlightRadarMap.tsx), and inventing fix names is exactly what rule 7 bans.
- distractors (contact / squawk / QNH / traffic information): phraseology with no clearance
  in it, so the extractor is also trained to say "nothing here".

Phraseology follows ICAO Doc 4444 Chapter 12 and Doc 9432 (numbers digit by digit, levels
as "flight level" and altitudes in thousands of feet). Levels at or above 10,000 ft are
spoken as flight levels and below it in feet: a simplification, stated -- Mumbai's actual
transition altitude is not in the repository.

Output: <voice cache>/tts/mumbai_scripts.parquet, one row per transmission, with the text to
speak (``tts_text``, spelling some telephony for pronunciation) and the label text
(``text``, what the recogniser should write), split by AIRCRAFT so no callsign's voice
appears in both training and validation.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE  # noqa: E402
from ml_pipeline.voice.callsigns import DIGITS, spoken_forms, telephony  # noqa: E402
from ml_pipeline.voice.text_norm import normalise  # noqa: E402

RAW = ROOT / "ml_pipeline/data/raw"
OUT = CACHE / "tts"
REPORTS = ROOT / "ml_pipeline/reports"
VABB = (19.0887, 72.8679)
MAX_NM = 120.0
FT_PER_M = 3.28084
SEED = 42
# How some telephony designators are said aloud, where reading the spelling would be wrong.
# IndiGo's "IFLY" is pronounced "eye-fly". The LABEL keeps the official spelling.
PRONOUNCE = {"ifly": "eye fly"}


def spoken_words(word: str) -> str:
    """Telephony written as one word but said as two: AIRINDIA -> "air india". Applied to
    the label too, because that is how a person transcribing the radio would write it."""
    return f"air {word[3:]}" if word.startswith("air") and len(word) > 6 else word
MAX_TURNS = 1300
SPEEDS = [160, 170, 180, 190, 200, 210, 220, 230, 240, 250, 260, 280]


def digits(n: int, width: int = 0) -> str:
    return " ".join(DIGITS[int(c)] for c in str(int(n)).zfill(width))


def level_words(feet: float) -> str:
    feet = int(round(feet / 100.0) * 100)
    if feet >= 10_000:
        return "flight level " + digits(feet // 100, 3)
    thousands, hundreds = divmod(feet, 1000)
    words = (digits(thousands) + " thousand") if thousands else ""
    if hundreds:
        words += (" " if words else "") + DIGITS[hundreds // 100] + " hundred"
    return words + " feet"


def _nm(lat, lon):
    dlat = np.radians(lat - VABB[0])
    dlon = np.radians(lon - VABB[1]) * math.cos(math.radians(VABB[0]))
    return 3440.065 * np.hypot(dlat, dlon)


def load_tracks() -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(str(RAW / "*.parquet"))):
        d = pd.read_parquet(path, columns=["icao24", "callsign", "latitude", "longitude", "baro_altitude",
                                           "on_ground", "true_track", "vertical_rate", "fetch_timestamp_utc"])
        d = d[~d.on_ground.fillna(True)].dropna(subset=["latitude", "longitude", "baro_altitude", "true_track"])
        d["session"] = Path(path).stem
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["callsign"] = d.callsign.fillna("").str.strip()
    d = d[d.callsign.str.fullmatch(r"[A-Z]{3}\d[A-Z0-9]{0,3}") & d.callsign.str[:3].isin(telephony())]
    d = d[_nm(d.latitude.to_numpy(), d.longitude.to_numpy()) <= MAX_NM]
    d["t"] = d.fetch_timestamp_utc.astype("int64") // 10**6
    d["alt_ft"] = d.baro_altitude * FT_PER_M
    return d.sort_values(["session", "icao24", "t"]).drop_duplicates(["session", "icao24", "t"])


def observed_clearances(track: pd.DataFrame) -> list[dict]:
    """Levels and headings this one aircraft actually flew to, with when to issue them."""
    t, alt, trk, vr = (track[c].to_numpy() for c in ("t", "alt_ft", "true_track", "vertical_rate"))
    out, n = [], len(t)
    i = 0
    while i < n:                                      # held levels
        j = i
        while j + 1 < n and abs(alt[j + 1] - alt[i]) < 150 and abs(vr[j + 1] if not np.isnan(vr[j + 1]) else 0) < 1.5:
            j += 1
        if t[j] - t[i] >= 60:
            level = round(float(np.median(alt[i: j + 1])) / 1000.0) * 1000.0
            before = np.where((t < t[i]) & (t >= t[i] - 600) & (np.abs(alt - level) >= 2000))[0]
            if len(before) and level >= 3000:
                k = before[-1]
                out.append({"t": int(t[k]), "action": "DESCEND" if alt[k] > level else "CLIMB", "value": level,
                            "value_source": "observed held level"})
        i = j + 1
    unwrapped = np.degrees(np.unwrap(np.radians(trk)))
    i = 0
    while i < n:                                      # settled headings after a turn
        j = i
        while j + 1 < n and abs(unwrapped[j + 1] - unwrapped[i]) < 5:
            j += 1
        if t[j] - t[i] >= 60 and i > 0:
            before = np.where((t < t[i]) & (t >= t[i] - 240) & (np.abs(unwrapped - unwrapped[i]) >= 20))[0]
            if len(before):
                k = before[-1]
                heading = (round((trk[i] % 360) / 5.0) * 5) % 360 or 360
                out.append({"t": int(t[k]), "action": "TURN", "value": float(heading),
                            "direction": "right" if unwrapped[i] > unwrapped[k] else "left",
                            "value_source": "observed settled track"})
        i = j + 1
    return out


def phrase(callsign_words: str, c: dict, rng: random.Random) -> tuple[str, str]:
    """(controller transmission, pilot readback) for one clearance."""
    if c["action"] in ("CLIMB", "DESCEND"):
        verb = "climb" if c["action"] == "CLIMB" else "descend"
        lw = level_words(c["value"])
        body = rng.choice([f"{verb} {lw}", f"{verb} to {lw}", f"{verb} and maintain {lw}"])
        back = f"{verb}ing {lw}"
    elif c["action"] == "TURN":
        hw = digits(c["value"], 3)
        body = rng.choice([f"turn {c['direction']} heading {hw}", f"turn {c['direction']} heading {hw} vectors for approach"])
        back = f"{c['direction']} heading {hw}"
    else:
        sw = digits(c["value"])
        body = rng.choice([f"reduce speed {sw} knots", f"speed {sw} knots", f"maintain {sw} knots"])
        back = f"speed {sw} knots"
    # Two in three transmissions are the bare form; the rest add the station name or "roger".
    atco = f"{callsign_words} mumbai approach {body}" if rng.random() < 1 / 3 else f"{callsign_words} {body}"
    pilot = f"roger {back} {callsign_words}" if rng.random() < 1 / 3 else f"{back} {callsign_words}"
    return atco, pilot


def distractor(callsign_words: str, rng: random.Random) -> str:
    return rng.choice([
        f"{callsign_words} contact mumbai tower one one eight decimal one goodbye",
        f"{callsign_words} squawk {digits(rng.randint(1000, 7677), 4)}",
        f"{callsign_words} qnh one zero {digits(rng.randint(0, 15), 2)}",
        f"{callsign_words} traffic information one o'clock five miles opposite direction",
        f"{callsign_words} report established on the localiser runway two seven",
        f"{callsign_words} cleared ils approach runway two seven",
        f"{callsign_words} number {DIGITS[rng.randint(2, 6)]} in sequence",
    ])


def tts_form(text: str) -> str:
    words = text.split()
    return " ".join(PRONOUNCE.get(w, w) for w in words)


def main():
    rng = random.Random(SEED)
    tracks = load_tracks()
    rows = []
    for (session, icao24), track in tracks.groupby(["session", "icao24"], sort=False):
        code = track.callsign.mode().iloc[0]
        words = " ".join(spoken_words(w) for w in spoken_forms(code)[0].split())
        found = observed_clearances(track)
        # At most one level and one heading clearance per aircraft per session: a long track
        # otherwise yields a "turn" for every wiggle and swamps the set with headings.
        chosen = []
        for kind in (("CLIMB", "DESCEND"), ("TURN",)):
            options = [c for c in found if c["action"] in kind]
            if options:
                chosen.append(rng.choice(options))
        for c in chosen:
            atco, pilot = phrase(words, c, rng)
            base = {"icao24": icao24, "callsign": code, "session": session, "t": c["t"], "action": c["action"],
                    "value": c["value"], "fix": None, "value_source": c["value_source"]}
            rows.append({**base, "role": "ATCO", "text": atco})
            if rng.random() < 0.5:
                rows.append({**base, "role": "PILOT", "text": pilot})
        if rng.random() < 0.35:                    # speed instructions: standard values, stated
            c = {"action": "SPEED", "value": float(rng.choice(SPEEDS))}
            atco, _ = phrase(words, c, rng)
            rows.append({"icao24": icao24, "callsign": code, "session": session, "t": int(track.t.iloc[len(track) // 2]),
                         "action": "SPEED", "value": c["value"], "fix": None,
                         "value_source": "standard phraseology value", "role": "ATCO", "text": atco})
        if rng.random() < 0.25:
            rows.append({"icao24": icao24, "callsign": code, "session": session, "t": int(track.t.iloc[0]),
                         "action": None, "value": None, "fix": None, "value_source": "no clearance (distractor)",
                         "role": "ATCO", "text": distractor(words, rng)})
    frame = pd.DataFrame(rows)
    # Turns are the easiest clearance to observe, so they outnumber levels about 4:1; cap
    # them so the accent pass does not mostly learn headings.
    turns = frame[frame.action == "TURN"]
    if len(turns) > MAX_TURNS:
        frame = frame.drop(turns.sample(len(turns) - MAX_TURNS, random_state=SEED).index).reset_index(drop=True)
    frame["text"] = frame.text.map(normalise)
    frame["tts_text"] = frame.text.map(tts_form)
    frame["split"] = frame.icao24.map(lambda h: "val" if int(hashlib.sha1(h.encode()).hexdigest(), 16) % 10 == 0 else "train")
    frame.insert(0, "script_id", [f"mum{i:06d}" for i in range(len(frame))])
    # Consistency: the extractor, run on each script's own label text, must recover the
    # clearance the script was written from. A miss means the phrasing or the rules are wrong.
    from ml_pipeline.voice.extract import extract
    recovered = []
    for r in frame.itertuples():
        e = extract(r.text)
        has = isinstance(r.action, str)
        recovered.append((e.action == r.action and e.value == r.value if has else e.action is None)
                         and e.callsign_code == r.callsign)
    frame["extractor_recovers"] = recovered
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(OUT / "mumbai_scripts.parquet", index=False)
    report = {"measured_at_utc": datetime.now(timezone.utc).isoformat(), "transmissions": int(len(frame)),
              "extractor_recovers_script_pct": round(100 * float(np.mean(recovered)), 2),
              "aircraft": int(frame.icao24.nunique()), "callsign_prefixes": frame.callsign.str[:3].value_counts().head(15).to_dict(),
              "by_action": frame.action.fillna("none").value_counts().to_dict(),
              "by_value_source": frame.value_source.value_counts().to_dict(),
              "by_role": frame.role.value_counts().to_dict(), "by_split": frame.split.value_counts().to_dict(),
              "examples": frame.sample(8, random_state=SEED)[["callsign", "action", "value", "value_source", "text", "tts_text"]].to_dict(orient="records")}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"mumbai_scripts_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=1))
    for e in report["examples"]:
        print(" ", e["text"], "|", e["action"], e["value"], "|", e["value_source"])


if __name__ == "__main__":
    main()
