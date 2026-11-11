"""Fine-tune Whisper on air-traffic speech with LoRA (plan 9.3 / revised speech plan, step 5).

    python ml_pipeline/voice/train_whisper.py --stage p1 --run radio_run
    python ml_pipeline/voice/train_whisper.py --stage p2 --init <p1 adapter dir> --run accent_run
    python ml_pipeline/voice/train_whisper.py --stage p1 --run radio_run --resume

Reads the cache and split written by build_audio_cache.py; never decides a split itself.

WHY LoRA ON whisper-small. The laptop GPU has 6 GB. Measured on 25 Sep: LoRA (r=32 on every
attention and feed-forward projection, 13.0 M trainable of 254.7 M) with gradient
checkpointing runs at 1.58 s per batch of 8 in 2.64 GB; without checkpointing it needed
8.85 GB, spilled into shared system memory and took 15.5 s per batch. whisper-small is
the model plan 9.3 names; the published number to beat is 15.1 % WER.

WHAT IS PRINTED BESIDE WHAT (plan rule 2). The starting checkpoint is scored on the same fixed
validation subset before the first step, so every later figure has its baseline next to it.
Validation WER is reported per corpus, never averaged into one number (rule 4); the
checkpoint kept is the one with the lowest MEAN of the real per-corpus WERs, so the larger corpus
cannot outvote the other.

Test data is never read here. Scoring on test is evaluate_voice.py's job, once, at the end.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import jiwer
import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE, SR  # noqa: E402
from ml_pipeline.voice.text_norm import normalise  # noqa: E402

REPORTS = ROOT / "ml_pipeline/reports"
BASE_MODEL = os.environ.get("FLIGHT_RIGHT_ASR_BASE", "openai/whisper-small")
STAGES = {
    # corpus -> weight. p2 keeps European audio in the mix so the accent pass cannot make the
    # model forget real radio (catastrophic forgetting is the standard failure of a second
    # fine-tuning pass on a narrow set).
    "p1": {"atcosim": 1.0, "uwb": 1.0},
    "p2": {"tts_indian": 1.0, "atcosim": 0.25, "uwb": 0.25},
}
VAL_PER_CORPUS = int(os.environ.get("FLIGHT_RIGHT_VOICE_VAL_PER_CORPUS", 200))
SEED = 42


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=sorted(STAGES), default="p1")
    p.add_argument("--init", help="adapter directory to start from (p2 starts from p1's best)")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--accum", type=int, default=2)
    p.add_argument("--lr", type=float, default=5e-4)
    p.add_argument("--warmup", type=int, default=300)
    p.add_argument("--eval-every", type=int, default=500, help="optimizer steps")
    p.add_argument("--patience", type=int, default=3)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--run", default=None)
    p.add_argument("--output-root", type=Path, default=CACHE / "runs")
    p.add_argument("--max-steps", type=int, default=None)
    p.add_argument("--val-per-corpus", type=int, default=VAL_PER_CORPUS)
    return p.parse_args()


class Audio:
    """Random access into the int16 caches without loading gigabytes into memory.

    Real corpora live in audio_int16.bin; generated speech in tts/audio_int16.bin. Each row's
    ``bin`` column says which (missing = the real-corpus file)."""

    def __init__(self):
        self.files: dict[str, np.memmap] = {}

    def __call__(self, row) -> np.ndarray:
        name = getattr(row, "bin", None)
        name = name if isinstance(name, str) and name else "audio_int16.bin"
        if name not in self.files:
            self.files[name] = np.memmap(CACHE / name, dtype=np.int16, mode="r")
        data = self.files[name]
        return data[int(row.offset): int(row.offset) + int(row.n_samples)].astype(np.float32) / 32768.0


def all_rows() -> pd.DataFrame:
    """The real-corpus manifest plus, when it exists, the generated-speech manifest."""
    frames = [pd.read_parquet(CACHE / "manifest.parquet")]
    # One manifest per synthesis shard (synthesize.py --shard i/n, e.g. one per GPU); each row
    # names its own audio file in "bin".
    for path in sorted((CACHE / "tts").glob("manifest*.parquet")):
        frames.append(pd.read_parquet(path))
    return pd.concat(frames, ignore_index=True)


def load_rows(stage: str, split: str) -> pd.DataFrame:
    manifest = all_rows()
    rows = manifest[(manifest.split == split) & manifest.corpus.isin(STAGES[stage])]
    missing = set(STAGES[stage]) - set(rows.corpus)
    if missing:
        raise SystemExit(f"stage {stage} needs corpora not in the cache: {sorted(missing)}")
    return rows.reset_index(drop=True)


def epoch_order(rows: pd.DataFrame, stage: str, rng: random.Random) -> list[int]:
    """Indices for one epoch, with each corpus subsampled to its stage weight."""
    order = []
    for corpus, weight in STAGES[stage].items():
        idx = rows.index[rows.corpus == corpus].tolist()
        rng.shuffle(idx)
        order += idx[: max(1, int(round(len(idx) * weight)))]
    rng.shuffle(order)
    return order


def label_ids(tokenizer, text: str) -> list[int]:
    ids = tokenizer(text).input_ids
    # The model prepends decoder_start_token_id itself when it shifts labels right.
    if ids and ids[0] == tokenizer.convert_tokens_to_ids("<|startoftranscript|>"):
        ids = ids[1:]
    return ids[:440]


def accumulation_group_size(batch_index: int, batch_count: int, accumulation: int) -> int:
    """Number of microbatches contributing to this optimizer update, including the tail."""
    return min(accumulation, batch_count - (batch_index // accumulation) * accumulation)


def update_boundary(batch_index: int, batch_count: int, accumulation: int) -> bool:
    return (batch_index + 1) % accumulation == 0 or batch_index + 1 == batch_count


def batches(rows, order, audio, processor, batch_size):
    """Feature extraction on a background thread so the GPU never waits on the CPU."""
    q: queue.Queue = queue.Queue(maxsize=6)

    def produce():
        for start in range(0, len(order), batch_size):
            chunk = rows.loc[order[start: start + batch_size]]
            feats = processor.feature_extractor([audio(r) for r in chunk.itertuples()],
                                                sampling_rate=SR, return_tensors="np").input_features
            labels = [label_ids(processor.tokenizer, t) for t in chunk.text]
            width = max(len(x) for x in labels)
            lab = np.full((len(labels), width), -100, dtype=np.int64)
            for i, x in enumerate(labels):
                lab[i, : len(x)] = x
            q.put((torch.from_numpy(feats), torch.from_numpy(lab)))

    def work():
        try:
            produce()
        except Exception as exc:
            q.put(exc)
        finally:
            q.put(None)

    threading.Thread(target=work, daemon=True).start()
    while (item := q.get()) is not None:
        if isinstance(item, Exception):
            raise item
        yield item


@torch.no_grad()
def evaluate(model, processor, rows, audio) -> dict:
    model.eval()
    out = {}
    for corpus, frame in rows.groupby("corpus"):
        hyps = []
        for start in range(0, len(frame), 16):
            chunk = frame.iloc[start: start + 16]
            feats = processor.feature_extractor([audio(r) for r in chunk.itertuples()],
                                                sampling_rate=SR, return_tensors="pt").input_features
            with torch.autocast("cuda", dtype=torch.float16):
                ids = model.generate(input_features=feats.cuda(), language="en", task="transcribe",
                                     max_new_tokens=160, use_cache=True)
            hyps += processor.tokenizer.batch_decode(ids, skip_special_tokens=True)
        refs = list(frame.text)
        hyps = [normalise(h) for h in hyps]
        pairs = [(r, h) for r, h in zip(refs, hyps) if r]
        out[corpus] = round(100 * jiwer.wer([r for r, _ in pairs], [h for _, h in pairs]), 2)
    model.train()
    # Synthetic voices are a diagnostic, not evidence of real-radio improvement.
    out["mean"] = round(float(np.mean([v for k, v in out.items() if k != "tts_indian"])), 2)
    return out


def main():
    args = parse_args()
    if args.resume and not args.run:
        raise SystemExit("--resume requires --run to identify the saved run")
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    torch.manual_seed(SEED)
    run = args.run or f"{args.stage}_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir = args.output_root / run
    if run_dir.exists() and not args.resume:
        raise SystemExit(f"Refusing to overwrite existing run: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "state.json"
    if args.resume and not (state_path.exists() and (run_dir / "last_adapter").exists()):
        raise SystemExit(f"No complete resumable checkpoint in {run_dir}")

    processor = WhisperProcessor.from_pretrained(BASE_MODEL)
    processor.tokenizer.set_prefix_tokens(language="english", task="transcribe")
    audio = Audio()
    train = load_rows(args.stage, "train")
    val_all = load_rows(args.stage, "val")
    val = pd.concat([f.sample(min(len(f), args.val_per_corpus), random_state=SEED)
                     for _, f in val_all.groupby("corpus")]).reset_index(drop=True)

    model = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL)
    model.config.use_cache = False
    model.generation_config.forced_decoder_ids = None
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    resume = args.resume and (run_dir / "last_adapter").exists()
    start_from = run_dir / "last_adapter" if resume else (Path(args.init) if args.init else None)
    if start_from:
        model = PeftModel.from_pretrained(model, str(start_from), is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(
            r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "out_proj", "fc1", "fc2"]))
    model.cuda()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    epoch_indices = epoch_order(train, args.stage, random.Random(0))
    steps_per_epoch = math.ceil(len(epoch_indices) / (args.batch * args.accum))
    total_steps = int(steps_per_epoch * args.epochs)
    if args.max_steps is not None:
        total_steps = min(total_steps, args.max_steps)
    if min(args.batch, args.accum, args.warmup, args.eval_every, total_steps) < 1:
        raise SystemExit("Batch, accumulation, warmup, evaluation interval and steps must be positive")
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / args.warmup) * max(0.0, (total_steps - s) / max(1, total_steps - args.warmup)))
    scaler = torch.amp.GradScaler()

    state = {"run": run, "stage": args.stage, "base_model": BASE_MODEL, "init": args.init,
             "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}, "trainable_params": trainable,
             "train_clips": train.corpus.value_counts().to_dict(),
             "weighted_epoch_clips": train.loc[epoch_indices].corpus.value_counts().to_dict(),
             "val_clips_scored": val.corpus.value_counts().to_dict(),
             "steps_per_epoch": steps_per_epoch, "total_steps": total_steps,
             "step": 0, "epoch": 0, "epoch_clips": 0, "evals": [], "best": None, "stale": 0, "started_utc": datetime.now(timezone.utc).isoformat()}
    if resume and state_path.exists():
        saved = json.loads(state_path.read_text())
        if saved["base_model"] != BASE_MODEL:
            raise SystemExit("Cannot resume with a different base model")
        for key in ("stage", "batch", "accum", "lr", "warmup", "epochs", "max_steps", "val_per_corpus"):
            if saved["args"].get(key) != state["args"].get(key):
                raise SystemExit(f"Cannot resume with changed setting: {key}; start a new continuation instead")
        state = saved
        opt.load_state_dict(torch.load(run_dir / "last_optimizer.pt"))
        sched.load_state_dict(torch.load(run_dir / "last_scheduler.pt"))
        if "epoch_clips" not in state:
            raise SystemExit("Legacy run lacks an exact data cursor; use --init for a new continuation run")
        scaler.load_state_dict(torch.load(run_dir / "last_scaler.pt"))
        torch.set_rng_state(torch.load(run_dir / "last_rng.pt")["cpu"])
        torch.cuda.set_rng_state_all(torch.load(run_dir / "last_rng.pt")["cuda"])
        print(f"resumed {run} at optimizer step {state['step']}")
    print(f"run {run}: {len(train):,} train clips {state['train_clips']}, {trainable/1e6:.1f} M trainable, "
          f"{steps_per_epoch} optimizer steps per epoch, {total_steps} total", flush=True)

    def checkpoint(tag: str):
        model.save_pretrained(run_dir / tag)
        if tag == "last_adapter":
            torch.save(opt.state_dict(), run_dir / "last_optimizer.pt")
            torch.save(sched.state_dict(), run_dir / "last_scheduler.pt")
            torch.save(scaler.state_dict(), run_dir / "last_scaler.pt")
            torch.save({"cpu": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}, run_dir / "last_rng.pt")

    def record_eval():
        t0 = time.time()
        wer = evaluate(model, processor, val, audio)
        entry = {"step": state["step"], "wer": wer, "seconds": round(time.time() - t0, 1),
                 "utc": datetime.now(timezone.utc).isoformat()}
        state["evals"].append(entry)
        improved = state["best"] is None or wer["mean"] < state["best"]["wer"]["mean"]
        if improved:
            state["best"], state["stale"] = entry, 0
            checkpoint("best_adapter")
        elif state["step"] > 0:
            state["stale"] += 1
        checkpoint("last_adapter")
        state_path.write_text(json.dumps(state, indent=2))
        base = state["evals"][0]["wer"]
        print(f"[eval] step {state['step']:5d}  WER {wer}  (starting checkpoint: {base})"
              f"{'  <- best' if improved and state['step'] else ''}", flush=True)

    if not state["evals"]:
        record_eval()  # the starting model's baseline on the same subset

    model.train()
    epoch = state["epoch"]
    t_last = time.time()
    while state["step"] < total_steps and state["stale"] < args.patience:
        order = epoch_order(train, args.stage, random.Random(SEED + epoch))
        skip = state["epoch_clips"]
        losses = []
        remaining_batches = math.ceil((len(order) - skip) / args.batch)
        for batch_index, (feats, lab) in enumerate(batches(train, order[skip:], audio, processor, args.batch)):
            # The final, shorter accumulation group must also produce an update.
            group_size = accumulation_group_size(batch_index, remaining_batches, args.accum)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = model(input_features=feats.cuda(), labels=lab.cuda()).loss / group_size
            scaler.scale(loss).backward()
            losses.append(loss.item() * group_size)
            state["epoch_clips"] += len(lab)
            if not update_boundary(batch_index, remaining_batches, args.accum):
                continue
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
            scaler.step(opt); scaler.update(); opt.zero_grad(set_to_none=True); sched.step()
            state["step"] += 1
            if state["step"] % 50 == 0:
                rate = (time.time() - t_last) / 50
                t_last = time.time()
                print(f"step {state['step']:5d}/{total_steps}  loss {np.mean(losses[-100:]):.3f}  "
                      f"lr {sched.get_last_lr()[0]:.2e}  {rate:.2f} s/step  "
                      f"eta {(total_steps - state['step']) * rate / 3600:.1f} h", flush=True)
            if state["step"] % args.eval_every == 0:
                record_eval()
                if state["stale"] >= args.patience:
                    print("validation WER stopped improving; stopping early")
                    break
            if state["step"] >= total_steps:
                break
        epoch += 1
        if state["epoch_clips"] == len(order):
            state["epoch"], state["epoch_clips"] = epoch, 0

    if state["evals"][-1]["step"] != state["step"]:
        record_eval()
    state["finished_utc"] = datetime.now(timezone.utc).isoformat()
    state_path.write_text(json.dumps(state, indent=2))
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"voice_train_{run}.json").write_text(json.dumps(state, indent=2))
    print(f"done. best {state['best']}\nadapter: {run_dir / 'best_adapter'}")


if __name__ == "__main__":
    main()
