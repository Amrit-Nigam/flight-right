"""Transcript -> callsign | action | value (plan Phase 6.1). Rules, not a model.

ATC phraseology is a small, rigid vocabulary (ICAO Doc 4444 Chapter 12 and Doc 9432,
Manual of Radiotelephony), so the plan's instruction is rules first and a classifier only
if the rules measurably fall short. Everything here is a regular pattern over the
normalised word sequence, and every pattern is listed in this file.

Output actions are exactly the ones ``ml_pipeline.utils.clearance.Clearance`` accepts:
CLIMB / DESCEND (value in feet), TURN (absolute heading, degrees), SPEED (knots), DIRECT
(``fix``). Anything else a controller says ("contact tower", "cleared to land") is not a
clearance the trajectory model can use, and yields no action -- it is not an error.

Units, stated because they are the difference between safe and not:
- "flight level one two zero" -> 12,000 ft (level x 100)
- "five thousand (feet)" / "altitude five thousand" -> 5,000 ft
- a bare number after climb/descend under 600 is read as a flight level ("descend three
  three zero" is FL330); 600 or more is read as feet. Our own design, from the ICAO rule
  that levels are spoken as flight levels above the transition altitude (Doc 4444 12.3.1).

CONFIDENCE, computable without knowing the right answer (plan 6.1): the product of the
recogniser's own confidence (exp of the mean token log-probability, when the recogniser
reports it) and how completely the phrase parsed (callsign found, value found, value
plausible). It is a ranking signal for greying out a transcript, not a probability; its
relation to real accuracy is measured in evaluate_voice.py, not assumed.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

from ml_pipeline.voice.callsigns import DIGIT_OF, callsign_vocabulary, spoken_to_code
from ml_pipeline.voice.text_norm import normalise

TENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
        "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
        "ninety": 90}
NUMBER_WORDS = set(DIGIT_OF) | set(TENS) | {"hundred", "thousand"}
GREETINGS = {"good", "morning", "afternoon", "evening", "day", "hello", "hi", "servus",
             "ahoj", "dobry", "den", "bonjour", "gruezi", "namaste", "and", "roger", "okay", "ok"}
LEVEL_UP = {"climb", "climbing"}
LEVEL_DOWN = {"descend", "descending"}
# Words a controller puts between the verb and the level ("climb straight ahead four
# thousand feet", "descend to traffic altitude ..."). An explicit list, not "skip anything",
# so a later clause ("squawk two seven six zero") can never be read as the level.
LEVEL_FILLER = {"to", "and", "maintain", "now", "further", "please", "straight", "ahead",
                "initially", "initial", "maximum", "traffic", "immediately", "expedite"}


@dataclass
class Extracted:
    callsign_spoken: str | None
    callsign_code: str | None       # list-free guess; matching against real aircraft is separate
    action: str | None
    value: float | None
    fix: str | None
    confidence: float
    text: str
    all_actions: list | None = None   # every instruction found, in spoken order

    def to_dict(self) -> dict:
        return asdict(self)


def read_number(words: list[str], i: int) -> tuple[float | None, int]:
    """Read a spoken number starting at words[i]. Returns (value, index after it)."""
    total, digits, j, seen = 0, "", i, False
    while j < len(words):
        w = words[j]
        if w in DIGIT_OF:
            digits += DIGIT_OF[w]
        elif w.isdigit():
            digits += w
        elif w in TENS:
            nxt = words[j + 1] if j + 1 < len(words) else ""
            unit = int(DIGIT_OF[nxt]) if nxt in DIGIT_OF and TENS[w] >= 20 else 0
            digits += str(TENS[w] + unit)
            j += 1 if unit else 0
        elif w == "hundred":
            total += int(digits or 1) * 100
            digits = ""
        elif w == "thousand":
            total += int(digits or 1) * 1000
            digits = ""
        else:
            break
        seen = True
        j += 1
    if not seen:
        return None, i
    return float(total + int(digits) if digits else total), j


def _level(words: list[str], i: int) -> tuple[float | None, int]:
    """A level after a climb/descend verb: feet, whatever way it was spoken."""
    j = i
    while j < len(words) and words[j] in LEVEL_FILLER:
        j += 1
    if j < len(words) and words[j] == "flight":
        j += 1
    if j < len(words) and words[j] == "level":
        value, k = read_number(words, j + 1)
        return (value * 100 if value is not None else None), k
    if j < len(words) and words[j] == "altitude":
        j += 1
    value, k = read_number(words, j)
    if value is None:
        return None, i
    explicit_feet = k < len(words) and words[k] in {"feet", "ft"}
    spoke_thousands = "thousand" in words[j:k] or "hundred" in words[j:k]
    if explicit_feet or spoke_thousands or value >= 600:
        return value, k + (1 if explicit_feet else 0)
    return value * 100, k


def _level_before(words: list[str], i: int) -> float | None:
    """A level spoken just before the verb, as pilots read back: "<level> feet climbing".

    Not after "passing": "passing two thousand climbing" reports where the aircraft is, not
    where it is going."""
    j = i
    if j > 0 and words[j - 1] in {"feet", "ft"}:
        j -= 1
    end = j
    while j > 0 and words[j - 1] in NUMBER_WORDS:
        j -= 1
    if j == end or (j > 0 and words[j - 1] == "passing"):
        return None
    if j >= 2 and words[j - 2: j] == ["flight", "level"] or (j >= 1 and words[j - 1] == "level"):
        value, _ = read_number(words, j)
        return value * 100 if value is not None else None
    value, _ = read_number(words, j)
    if value is None:
        return None
    return value if (end < i or "thousand" in words[j:end] or value >= 600) else value * 100


def _actions(words: list[str]) -> list[tuple[int, str, float | None, str | None]]:
    """Every clearance in the transcript as (position, action, value, fix)."""
    found = []
    for i, w in enumerate(words):
        if w in LEVEL_UP | LEVEL_DOWN:
            value, _ = _level(words, i + 1)
            if value is None:
                value = _level_before(words, i)   # readback: "five thousand feet climbing"
            if value is not None:
                found.append((i, "CLIMB" if w in LEVEL_UP else "DESCEND", value, None))
        elif w == "heading":
            value, _ = read_number(words, i + 1)
            if value is not None:
                found.append((i, "TURN", value % 360 if value != 360 else 360.0, None))
        elif w == "direct":
            j = i + 1
            while j < len(words) and words[j] in {"to", "for"}:
                j += 1
            if j < len(words) and words[j] not in NUMBER_WORDS and words[j] not in GREETINGS:
                found.append((i, "DIRECT", None, words[j]))
        elif w == "speed" or (w == "knots" and i > 0):
            if w == "knots":
                start = i - 1
                while start > 0 and words[start - 1] in NUMBER_WORDS:
                    start -= 1
                value, _ = read_number(words, start)
                # "wind two five zero degrees nine knots" is weather, not a speed instruction.
                is_wind = "wind" in words[max(0, start - 6): start] or (start > 0 and words[start - 1] == "degrees")
                if value is not None and not is_wind and not any(a[1] == "SPEED" and abs(a[0] - i) < 8 for a in found):
                    found.append((start, "SPEED", value, None))
                continue
            j = i + 1
            while j < len(words) and words[j] in {"to", "maximum", "minimum", "not", "below", "above",
                                                  "of", "reduce", "increase", "at", "own", "is"}:
                j += 1
            value, _ = read_number(words, j)
            if value is None and i > 0 and words[i - 1] in NUMBER_WORDS:
                start = i - 1                      # "maximum one six zero speed"
                while start > 0 and words[start - 1] in NUMBER_WORDS:
                    start -= 1
                value, _ = read_number(words, start)
            if value is not None and value >= 100:
                found.append((i, "SPEED", value, None))
    return sorted(found)


def _callsign_span(words: list[str]) -> str | None:
    """The run of callsign words at the start (controller) or, failing that, the end (readback)."""
    vocab = callsign_vocabulary()
    start = 0
    while start < len(words) and words[start] in GREETINGS:
        start += 1
    lead = []
    for w in words[start:]:
        if w not in vocab:
            break
        lead.append(w)
    tail = []
    for w in reversed(words):
        if w not in vocab:
            break
        tail.insert(0, w)
    # A readback ends "... heading two two five klm eight seven seven": the digits in front
    # of the airline word belong to the value, not the callsign.
    while tail and tail[0] in DIGIT_OF:
        tail.pop(0)
    for span in (lead, tail):
        if len(span) >= 2 and any(w not in DIGIT_OF for w in span):
            return " ".join(span)
    return None


def extract(text: str, asr_confidence: float | None = None) -> Extracted:
    """Parse one transmission. ``asr_confidence`` is exp(mean token log-prob), if known."""
    norm = normalise(text)
    words = norm.split()
    actions = _actions(words)
    spoken = _callsign_span(words)
    code = spoken_to_code(spoken) if spoken else None
    action = actions[0] if actions else None
    completeness = 0.4 + 0.3 * (spoken is not None) + 0.3 * (action is not None and
                                                              (action[2] is not None or action[3] is not None))
    confidence = completeness * (asr_confidence if asr_confidence is not None else 1.0)
    return Extracted(callsign_spoken=spoken, callsign_code=code,
                     action=action[1] if action else None,
                     value=action[2] if action else None,
                     fix=action[3] if action else None,
                     confidence=round(float(confidence), 3), text=norm,
                     all_actions=[{"action": a, "value": v, "fix": f} for _, a, v, f in actions])


def asr_confidence_from_logprob(mean_logprob: float | None) -> float | None:
    return None if mean_logprob is None or math.isnan(mean_logprob) else float(math.exp(mean_logprob))


def gold_action(command: str | None, value: str | None) -> tuple[str | None, float | None, str | None]:
    """Map an ATCO2 annotation (command tag, value tag) onto our action set.

    Uses the same number reader as the extractor, applied to the ANNOTATORS' tags, never to
    our own output, so scoring cannot agree with itself by construction."""
    cmd = normalise(command)
    val_words = normalise(value).split()
    if not cmd:
        return None, None, None
    words = cmd.split()
    if set(words) & (LEVEL_UP | LEVEL_DOWN):
        level, _ = _level(val_words, 0)
        return ("CLIMB" if set(words) & LEVEL_UP else "DESCEND"), level, None
    if "heading" in words:
        heading, _ = read_number([w for w in val_words if w not in {"degrees"}], 0)
        return "TURN", heading, None
    if "direct" in words:
        fix = next((w for w in val_words if w not in {"to", "for"}), None)
        return "DIRECT", None, fix
    if "speed" in words or "knots" in val_words:
        speed, _ = read_number([w for w in val_words if w not in {"maximum", "minimum", "not", "below", "above"}], 0)
        return "SPEED", speed, None
    return None, None, None
