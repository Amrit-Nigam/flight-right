"""Uniform full-weight average of aligned fine-tunes; validation must justify use."""
from contextlib import ExitStack
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def average_into(model, readers):
    import torch
    preserved = changed = 0
    pointers = set()
    with torch.no_grad():
        for key, destination in model.state_dict().items():
            if destination.data_ptr() in pointers:
                continue
            pointers.add(destination.data_ptr())
            tensors = [r.get_tensor(key) for r in readers]
            if any(t.shape != destination.shape for t in tensors):
                raise ValueError(f"Unaligned source tensor: {key}")
            if all(torch.equal(tensors[0], t) for t in tensors[1:]):
                destination.copy_(tensors[0])
                preserved += 1
            else:
                average = torch.zeros_like(destination)
                for tensor in tensors:
                    average.add_(tensor, alpha=1 / len(tensors))
                destination.copy_(average)
                changed += 1
    return preserved, changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ct2-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite {args.output}")
    import torch
    from safetensors import safe_open
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    from ml_pipeline.voice import transcribe
    source_hashes = [hashlib.sha256((p / "model.safetensors").read_bytes()).hexdigest() for p in args.sources]
    model = WhisperForConditionalGeneration.from_pretrained(str(args.sources[0]))
    # Own writable storage, even if the loader used memory-mapped source tensors.
    for tensor in list(model.parameters()) + list(model.buffers()):
        tensor.data = tensor.data.clone()
    with ExitStack() as stack, torch.no_grad():
        readers = [stack.enter_context(safe_open(str(p / "model.safetensors"), framework="pt", device="cpu"))
                   for p in args.sources]
        preserved, changed = average_into(model, readers)
    model.generation_config.forced_decoder_ids = None
    model.save_pretrained(args.output)
    processor = WhisperProcessor.from_pretrained(str(args.sources[0]))
    processor.save_pretrained(args.output)
    processor.feature_extractor.save_pretrained(args.output)
    provenance = {"method": "uniform full-weight average; unchanged tensors preserved exactly",
                  "sources": [{"path": str(p.resolve()), "weight": 1 / len(args.sources), "sha256": digest}
                              for p, digest in zip(args.sources, source_hashes)],
                  "unchanged_tensors": preserved, "averaged_tensors": changed,
                  "source": "https://proceedings.mlr.press/v162/wortsman22a.html",
                  "scope": "Paper is not evidence of ASR improvement; our validation determines eligibility"}
    (args.output / "flightright_provenance.json").write_text(json.dumps(provenance, indent=2))
    for path, digest in zip(args.sources, source_hashes):
        if hashlib.sha256((path / "model.safetensors").read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Source weights changed: {path}")
    transcribe.CT2_DIR = args.ct2_root
    print("runtime:", transcribe.ct2_path(str(args.output), "int8_float16"), flush=True)


if __name__ == "__main__":
    main()
