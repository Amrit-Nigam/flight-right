"""Callsigns: code <-> spoken form, and snapping a heard callsign onto real aircraft (plan 6.2).

A radio callsign is spoken, not written. ``IGO5323`` is said "IFLY five three two three";
``VT-ABC`` is said "Victor Tango Alfa Bravo Charlie" and, once contact is established, may
be abbreviated to "Victor Bravo Charlie". To match what was heard against the aircraft the
surveillance feed says are airborne, every candidate is turned into the words a controller
would say, and the heard words are compared against those with rapidfuzz.

SOURCES for the airline telephony designators (the "IFLY" in "IFLY five three two three"):
- Primary: FAA Order JO 7340.2, Chapter 3, Section 3, "ICAO Aircraft Company Three-Letter
  Identifier and/or Telephony Designator Assignments", sorted by designator.
  https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_3.html
  A U.S. government publication of the ICAO Doc 8585 assignments, current and public.
- Fallback for designators the FAA page lacks: OpenFlights airlines.dat (ODbL 1.0),
  https://github.com/jpatokal/openflights. OpenFlights alone is out of date for India: it
  has no entry for Akasa Air (AKJ, 153 aircraft-sessions in our recordings) and gives OMS as
  a defunct Russian carrier, where the FAA list has SalamAir "MAZOON".
Both files are cached under the voice cache on first use.

The phonetic alphabet and the digit words follow ICAO Annex 10, Volume II, 5.2.1.4
(spelling alphabet and transmission of numbers), which is why a spoken "niner" is 9 and
"tree" is 3.

WHY MATCHING IS POST-PROCESSING. Plan 6.2, measured in the literature it cites: putting the
callsign list into Whisper's prompt made overall accuracy worse on 6 of 11 test sets. A
post-hoc snap onto the list cannot make the transcript itself worse.
"""
from __future__ import annotations

import csv
import html
import os
import re
import ssl
import urllib.request
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

CACHE = Path(os.environ.get("FLIGHT_RIGHT_VOICE_CACHE",
                            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight/voice"))
FAA_URL = "https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_3.html"
OPENFLIGHTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"

NATO = {"A": "alfa", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo", "F": "foxtrot",
        "G": "golf", "H": "hotel", "I": "india", "J": "juliett", "K": "kilo", "L": "lima",
        "M": "mike", "N": "november", "O": "oscar", "P": "papa", "Q": "quebec", "R": "romeo",
        "S": "sierra", "T": "tango", "U": "uniform", "V": "victor", "W": "whiskey", "X": "xray",
        "Y": "yankee", "Z": "zulu"}
LETTER_OF = {v: k for k, v in NATO.items()} | {"alpha": "A", "juliet": "J", "whisky": "W", "x": "X"}
DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
DIGIT_OF = {w: str(i) for i, w in enumerate(DIGITS)} | {"niner": "9", "tree": "3", "fife": "5", "oh": "0"}

# Words that are phraseology, never part of a callsign, even when some airline's telephony
# designator happens to contain them ("SPEED", "EXPRESS", "RADAR" ...).
PHRASEOLOGY = set("""
descend descending climb climbing turn turning heading left right proceed direct to speed reduce
increase maintain maintaining contact cleared clear report squawk taxi line up hold holding short
continue radar identified good morning afternoon evening day hello bye goodbye roger wilco affirm
affirmative negative request ready runway approach tower information via for when expect
established vacate cross join confirm say again standby passing with is are we i flight level
altitude feet knots degrees and the a of on at your you thank thanks ils qnh wind frequency
decimal point until after before then now correction monitor ground departure arrival own
navigation resume back behind traffic caution please sir over out
""".split())


def _fetch(url: str, path: Path) -> str:
    if not path.exists():
        import certifi  # Windows' trust store refuses some of these sites; certifi does not
        context = ssl.create_default_context(cafile=certifi.where())
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Flight Right research)"})
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(request, context=context, timeout=90).read())
    return path.read_text(encoding="utf8", errors="ignore")


@lru_cache(maxsize=1)
def telephony() -> dict[str, str]:
    """ICAO three-letter designator -> telephony designator, lower case."""
    table: dict[str, str] = {}
    try:
        for row in csv.reader(_fetch(OPENFLIGHTS_URL, CACHE / "openflights_airlines.dat").splitlines()):
            if len(row) > 5 and re.fullmatch(r"[A-Z]{3}", row[4] or "") and row[5] not in ("", r"\N"):
                table.setdefault(row[4], row[5].lower())
    except OSError:
        pass
    page = _fetch(FAA_URL, CACHE / "faa_7340_chap3_sec3.html")
    for row in re.findall(r"<tr class=\"row\">(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 4 and re.fullmatch(r"[A-Z]{3}", cells[0]) and cells[3]:
            table[cells[0]] = cells[3].lower()          # FAA wins over OpenFlights
    cleaned = {k: " ".join(re.sub(r"[^a-z ]", " ", v).split()) for k, v in table.items()}
    return {k: v for k, v in cleaned.items() if v}


@lru_cache(maxsize=1)
def short_telephony() -> dict[str, str]:
    """First word of a multi-word telephony, when no other airline's telephony starts with it.

    Controllers shorten in practice ("CSA one delta zulu" for CSA LINES). A first word shared
    by two airlines ("sky", "air") is never used, so shortening cannot create a collision."""
    firsts: dict[str, set[str]] = {}
    for code, words in telephony().items():
        firsts.setdefault(words.split()[0], set()).add(code)
    reserved = PHRASEOLOGY | set(NATO.values()) | set(DIGIT_OF)
    return {code: words.split()[0] for code, words in telephony().items()
            if len(words.split()) > 1 and len(firsts[words.split()[0]]) == 1
            and words.split()[0] not in reserved}


@lru_cache(maxsize=1)
def _telephony_by_words() -> dict[tuple[str, ...], str]:
    out: dict[tuple[str, ...], str] = {}
    for code, words in telephony().items():
        key = tuple(words.split())
        if key and not all(w in PHRASEOLOGY for w in key):
            out.setdefault(key, code)
    for code, word in short_telephony().items():
        out.setdefault((word,), code)
    return out


@lru_cache(maxsize=1)
def callsign_vocabulary() -> frozenset[str]:
    """Every word that can appear inside a spoken callsign."""
    words = set(NATO.values()) | set(LETTER_OF) | set(DIGIT_OF) | {"heavy", "super"}
    for key in _telephony_by_words():
        words.update(key)
    # Telephony written as one word but spoken as two (AIRINDIA -> "air india",
    # AIRFRANS -> "air frans"): both halves can appear in a heard callsign.
    for key in list(_telephony_by_words()):
        if len(key) == 1 and key[0].startswith("air") and len(key[0]) > 6:
            words.update({"air", key[0][3:]})
    return frozenset(words - PHRASEOLOGY)


def _spell(chars: str) -> list[str]:
    return [DIGITS[int(c)] if c.isdigit() else NATO[c] for c in chars if c.isalnum()]


def spoken_forms(code: str) -> list[str]:
    """How a controller would say this callsign, most formal first.

    ``IGO5323`` -> ["ifly five three two three"]; a registration such as ``OKPMB`` ->
    ["oscar kilo papa mike bravo", "oscar mike bravo"] (ICAO abbreviated form: first
    character and the last two)."""
    code = re.sub(r"[^A-Z0-9]", "", code.upper())
    if not code:
        return []
    match = re.fullmatch(r"([A-Z]{3})(\d[A-Z0-9]*)", code)
    if match and match.group(1) in telephony():
        tail = " ".join(_spell(match.group(2)))
        forms = [f"{telephony()[match.group(1)]} {tail}"]
        if match.group(1) in short_telephony():
            forms.append(f"{short_telephony()[match.group(1)]} {tail}")
        return forms
    full = _spell(code)
    forms = [" ".join(full)]
    if len(full) > 3:
        forms.append(" ".join([full[0]] + full[-2:]))
    return forms


def spoken_to_code(spoken: str) -> str | None:
    """Best-effort written callsign from heard words, with no candidate list."""
    words = spoken.split()
    by_words = _telephony_by_words()
    # "air india" is spoken as two words and written AIRINDIA; compare with spaces removed too.
    compact = {"".join(k): v for k, v in by_words.items()}
    for size in (3, 2, 1):
        if len(words) <= size:
            continue
        code = by_words.get(tuple(words[:size])) or compact.get("".join(words[:size]))
        if code:
            tail = "".join(DIGIT_OF.get(w) or LETTER_OF.get(w, "") for w in words[size:])
            return code + tail if tail else None
    letters = "".join(DIGIT_OF.get(w) or LETTER_OF.get(w, "") for w in words)
    return letters or None


def match(heard: str, candidates: list[str], minimum: float = 70.0) -> dict:
    """Snap a heard callsign (or a whole transcript) onto the closest real aircraft.

    Scores every candidate's spoken forms against every window of the heard words of about
    the same length and keeps the best; so it works on a clean extracted callsign and on a
    whole noisy transcript alike. Returns the code, the score (0-100), and the margin over
    the runner-up -- a small margin means two aircraft sound alike, which the dashboard
    should show rather than hide.
    """
    words = heard.split()
    scored = []
    for code in dict.fromkeys(candidates):
        best = 0.0
        for form in spoken_forms(code):
            n = len(form.split())
            if not words:
                continue
            for size in {max(1, n - 1), n, n + 1}:
                for start in range(0, max(1, len(words) - size + 1)):
                    best = max(best, fuzz.ratio(" ".join(words[start: start + size]), form))
        scored.append((best, code))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < minimum:
        return {"code": None, "score": scored[0][0] if scored else 0.0, "margin": 0.0}
    margin = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0.0)
    return {"code": scored[0][1], "score": round(scored[0][0], 1), "margin": round(margin, 1)}
