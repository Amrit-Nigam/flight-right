"""One transcript normaliser for every speech number in the project.

Three corpora write the same words three ways: ATCOSIM (through the jlvdoorn mirror) is
Title Case with non-breaking spaces and the odd Czech farewell, UWB-ATCC is lower case, and
the ATCO2 test set is lower case with the ICAO spellings "alfa" and "juliett". The published
models were trained on some mix of these. Word error rate is only comparable across models
if every hypothesis and every reference goes through the same function, so this is the only
place that decides what counts as "the same word".

The rules are deliberately few and every one is stated:
- lower case; accents stripped (``deň`` -> ``den``); non-breaking space -> space
- a hyphen splits words (``re-`` becomes ``re``); every other non-letter, non-digit,
  non-apostrophe character is removed
- ICAO spellings win where two spellings of one letter word exist: alpha -> alfa,
  juliet -> juliett
- whitespace collapsed

Nothing here changes numbers into digits or digits into numbers: ATC references spell
numbers out ("one two three"), so a model that writes "123" is genuinely wrong three times.
"""
from __future__ import annotations

import re
import unicodedata

_SPELLINGS = {"alpha": "alfa", "juliet": "juliett"}
_DROP = re.compile(r"[^a-z0-9' ]+")
_SPACE = re.compile(r"\s+")


def normalise(text: str | None) -> str:
    """The canonical form of a transcript, for training targets and for scoring."""
    if not isinstance(text, str) or not text:
        return ""   # None and pandas' NaN both mean "nothing was said"
    text = unicodedata.normalize("NFKD", text.replace("\xa0", " "))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("-", " ").replace("_", " ")
    text = _DROP.sub(" ", text)
    words = [_SPELLINGS.get(w, w) for w in text.split()]
    return _SPACE.sub(" ", " ".join(w.strip("'") for w in words if w.strip("'"))).strip()
