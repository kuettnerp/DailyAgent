#!/usr/bin/env python3
"""End-to-end sanity check for voice/models/patriot.onnx: loads it through
the exact same openwakeword.model.Model class and inference_framework
wake_daemon.py uses, and streams the held-out synthetic clips (built by
build_dataset.py, never seen during training) through it frame-by-frame
the way real microphone audio would arrive.

This is the strongest validation possible without a real microphone, but
it is still entirely synthetic (espeak-ng TTS) audio -- see
training/README.md for what that does and doesn't prove.

Run: python3 validate_streaming.py [--threshold 0.5]
"""
from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
HELDOUT_DIR = HERE / "audio" / "heldout"
MODEL_PATH = HERE.parent / "models" / "patriot.onnx"

FRAME_SAMPLES = 1280
PRIME_FRAMES = 30  # >1 embedding window's worth, to flush buffers


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
        return np.frombuffer(raw, dtype=np.int16)


def frames_of(audio: np.ndarray):
    for i in range(0, len(audio), FRAME_SAMPLES):
        chunk = audio[i:i + FRAME_SAMPLES]
        if len(chunk) < FRAME_SAMPLES:
            chunk = np.pad(chunk, (0, FRAME_SAMPLES - len(chunk)))
        yield chunk


def score_clip(model, key: str, audio: np.ndarray, rng: np.random.Generator) -> float:
    # Prime with quiet random noise, not literal zeros -- openwakeword's own
    # AudioFeatures.reset() does the same, and its melspectrogram code notes
    # that zero/near-zero padding is where the streaming-vs-batch numerical
    # path diverges most, which would bias this check unrealistically.
    for _ in range(PRIME_FRAMES):
        noise = rng.integers(-200, 200, size=FRAME_SAMPLES, dtype=np.int16)
        model.predict(noise)
    max_score = 0.0
    for frame in frames_of(audio):
        scores = model.predict(frame)
        max_score = max(max_score, scores.get(key, 0.0))
    return max_score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    if not MODEL_PATH.exists():
        raise SystemExit(f"No model at {MODEL_PATH} -- run train_model.py first")

    from openwakeword.model import Model
    model = Model(wakeword_models=[str(MODEL_PATH)], inference_framework="onnx")
    keys = list(model.predict(np.zeros(FRAME_SAMPLES, dtype=np.int16)).keys())
    key = keys[0]
    print(f"[validate] loaded model, key={key!r}")

    manifest = json.loads((HELDOUT_DIR / "manifest.json").read_text())
    rng = np.random.default_rng(0)

    results = []
    for entry in manifest:
        audio = read_wav(HELDOUT_DIR / entry["path"])
        score = score_clip(model, key, audio, rng)
        results.append({**entry, "score": score, "triggered": score >= args.threshold})

    positives = [r for r in results if r["label"] == 1]
    negatives = [r for r in results if r["label"] == 0]
    recall = sum(r["triggered"] for r in positives) / len(positives) if positives else float("nan")
    fp_rate = sum(r["triggered"] for r in negatives) / len(negatives) if negatives else float("nan")

    print(f"[validate] threshold={args.threshold}")
    print(f"[validate] positive clips: {len(positives)}, recall={recall:.3f}")
    print(f"[validate] negative clips: {len(negatives)}, false_positive_rate={fp_rate:.3f}")

    missed = [r for r in positives if not r["triggered"]]
    false_triggers = [r for r in negatives if r["triggered"]]
    if missed:
        print(f"[validate] missed positives: {[(r['path'], round(r['score'], 3)) for r in missed]}")
    if false_triggers:
        print(f"[validate] false triggers: {[(r['path'], round(r['score'], 3)) for r in false_triggers]}")


if __name__ == "__main__":
    main()
