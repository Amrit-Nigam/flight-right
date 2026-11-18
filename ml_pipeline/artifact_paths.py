"""Canonical paths for shared ML artifacts, with pinned checksums for old studies.

Only reference metadata is stored here; models/data remain in their canonical folders.
An old study must fail explicitly if its shared model/data has changed, rather than
quietly score a newly trained artifact. Unregistered paths (including isolated smoke
test roots) retain their original behavior.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "ml_pipeline/artifact_registry.json"
SHARED = ROOT / "ml_pipeline/data/processed/shared"
FUTURE_COHORT = SHARED / "future_holdout_20260910_20260920.npz"
FUTURE_BASELINE = SHARED / "lstm_baseline_future_predictions.npy"


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {"schema": 1, "aliases": {}}


def resolve_artifact(path):
    """Resolve a historical input path to its hash-checked canonical copy."""
    original = Path(path)
    absolute = original.resolve()
    if not absolute.is_relative_to(ROOT.resolve()):
        return original
    entry = _registry()["aliases"].get(absolute.relative_to(ROOT.resolve()).as_posix())
    if entry is None:
        return original
    canonical = (ROOT / entry["canonical"]).resolve()
    if not canonical.is_relative_to(ROOT.resolve()) or canonical == absolute:
        raise ValueError(f"Invalid canonical artifact path for {path}")
    if not canonical.is_file():
        raise FileNotFoundError(f"Shared artifact missing: {canonical} (required by {path})")
    if checksum(canonical) != entry["sha256"]:
        raise ValueError(f"Shared artifact changed: {canonical}. Restore the recorded SHA-256 {entry['sha256']} before reusing this study; do not substitute new model weights/data.")
    return canonical


def register_reference(alias, canonical):
    """Record a baseline/input reference instead of copying its bytes."""
    alias = Path(alias).resolve()
    canonical = resolve_artifact(canonical).resolve()
    if not alias.is_relative_to(ROOT.resolve()) or not canonical.is_relative_to(ROOT.resolve()):
        raise ValueError("Shared artifact references must stay inside the project")
    if alias == canonical:
        return canonical
    entry = {"canonical": canonical.relative_to(ROOT.resolve()).as_posix(), "sha256": checksum(canonical), "bytes": canonical.stat().st_size}
    registry = _registry()
    key = alias.relative_to(ROOT.resolve()).as_posix()
    if key in registry["aliases"] and registry["aliases"][key] != entry:
        raise ValueError(f"Refusing to replace an existing study's baseline: {alias}. Use a new run directory.")
    if alias.exists():
        raise FileExistsError(f"Remove the verified duplicate before registering its reference: {alias}")
    registry["aliases"][key] = entry
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return canonical


def save_shared_array(path, values):
    """Write one shared prediction array; never replace a different recorded result."""
    import numpy as np
    path = Path(path)
    if path.exists():
        if not np.array_equal(np.load(path), values, equal_nan=True):
            raise ValueError(f"Shared predictions differ: {path}; use a new cohort/model-specific path")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, values)


def reuse_identical_output(path):
    """Discard a newly generated export only when it matches a recorded canonical file."""
    path = Path(path).resolve()
    registry = _registry()
    digest = checksum(path)
    key = path.relative_to(ROOT.resolve()).as_posix()
    previous = registry["aliases"].get(key)
    if previous and previous.get("relationship") == "same_bundle_plus_tuning_model_card" and previous.get("source_sha256") == digest:
        # Exact original export regenerated: its equivalence to the packaged file
        # was audited once and both complete-file hashes are pinned.
        target = resolve_artifact(path)
        path.unlink()
        return target
    if previous and previous["sha256"] != digest:
        raise ValueError(f"New output differs from the recorded study at {path}; use a new run path before scoring it")
    for entry in registry["aliases"].values():
        target = (ROOT / entry["canonical"]).resolve()
        if target != path and entry["sha256"] == digest and target.is_file() and checksum(target) == digest:
            if key in registry["aliases"] and registry["aliases"][key] != entry:
                raise ValueError(f"A recorded study already owns {path}; use a new output path")
            registry["aliases"][key] = entry
            REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            path.unlink()
            return target
    return path
