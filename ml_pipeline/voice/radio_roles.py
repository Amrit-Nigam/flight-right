"""Conservative phrase-based role hints for a mixed radio channel, not speaker diarization.

The same imperative can be a controller instruction or a pilot readback. Such phrases stay
unknown unless a source labels the channel or the controller explicitly reviews the text.
"""
import re


def infer_role(text: str, callsign: str | None = None, spoken_callsign: str | None = None) -> dict:
    if re.search(r"\b(request|requesting|would like|can we|may we|we are|we're|unable)\b", text):
        return {"role": "pilot", "reason": "pilot request, report or unable phrase"}
    if re.search(r"\b(climbing|descending|turning|maintaining|leaving|passing|wilco)\b", text):
        return {"role": "pilot", "reason": "pilot report or readback phrase"}
    # A callsign at the end is typical readback phraseology; it is only a hint.
    if spoken_callsign and text.endswith(spoken_callsign) and text != spoken_callsign:
        return {"role": "pilot", "reason": "callsign at the end of a readback"}
    if callsign and text.endswith(callsign.lower()) and text != callsign.lower():
        return {"role": "pilot", "reason": "callsign at the end of a readback"}
    # Explicit controller self-identification is more specific than an imperative alone.
    if re.search(r"\b(radar identified|radar contact|identified on radar)\b", text):
        return {"role": "atco", "reason": "controller radar-identification phrase"}
    return {"role": "unknown", "reason": "mixed radio: phrase alone does not establish whether this is an instruction or readback"}
