#!/usr/bin/env python3
"""Builds a synthetic training/held-out dataset for the "Patriot" wake word.

Uses espeak-ng (local, offline, no account, no model download -- installed
via the OS package manager) to synthesize the word "Patriot" across several
voices/pitches/speeds as positives, and a wide range of other words/phrases
as negatives, including phonetically-similar "hard negative" words and
mistimed utterances of "Patriot" itself (present but not ending at the
clip boundary, which is how real streaming detection tells "just said it"
apart from "said it a while ago").

Every clip is fit to exactly 2.0 seconds of 16kHz mono audio, because that
is the amount of context openWakeWord's default model architecture uses
(get_embedding_shape(2.0) == (16, 96), matching input_shape=(16, 96)).

Outputs (all under voice/training/, all gitignored -- see build outputs):
    audio/heldout/*.wav      held-out clips kept as raw audio, used later
                              for an end-to-end streaming sanity check
    dataset.npz               extracted embeddings + labels for training

Run: python3 build_dataset.py
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample

from openwakeword.utils import AudioFeatures

HERE = Path(__file__).resolve().parent
AUDIO_DIR = HERE / "audio"
HELDOUT_DIR = AUDIO_DIR / "heldout"
DATASET_PATH = HERE / "dataset.npz"

WAKE_WORD = "Patriot"
SAMPLE_RATE = 16000
CLIP_SECONDS = 2.0
CLIP_SAMPLES = int(SAMPLE_RATE * CLIP_SECONDS)  # 32000

# Voices used for TRAINING data.
TRAIN_VOICES = ["en-us", "en-gb", "en-gb-x-rp", "en-gb-x-gbclan", "en-029"]
# Voices/accents held out entirely from training -- used only to build the
# held-out set, so it actually tests generalization to unseen accents
# (still all synthetic espeak-ng speech, see README.md limitations).
TEST_VOICES = ["en-gb-scotland", "en-gb-x-gbcwmd"]

PITCHES = [30, 50, 70]     # espeak-ng -p (0-99)
SPEEDS = [140, 170, 200]   # espeak-ng -s (words per minute)

NEG_WORDS = [
    "hello", "computer", "morning", "calendar", "schedule", "weather",
    "please", "cancel", "yesterday", "meeting", "grocery", "birthday",
    "notebook", "windows", "coffee", "sandwich", "elephant", "banana",
    "mountain", "history", "science", "purple", "guitar", "octopus",
    "dinosaur", "umbrella", "chocolate", "bicycle", "hospital", "library",
    "yes", "no", "stop", "go", "okay", "tomorrow",
    "what's on my plate today", "good morning", "how are you",
    "turn off the lights", "set a timer", "play some music",
]
# Phonetically close to "Patriot" -- the examples that matter most for
# teaching the model the difference.
HARD_NEG_WORDS = ["patrol", "patriots", "patriotic", "petrol", "patron", "matter"]


def espeak_synth(text: str, voice: str, pitch: int, speed: int, amplitude: int = 100) -> tuple[np.ndarray, int]:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    try:
        subprocess.run(
            ["espeak-ng", "-v", voice, "-p", str(pitch), "-s", str(speed),
             "-a", str(amplitude), "-w", path, text],
            check=True, capture_output=True,
        )
        with wave.open(path, "rb") as wf:
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            audio = np.frombuffer(raw, dtype=np.int16)
    finally:
        Path(path).unlink(missing_ok=True)
    return audio, rate


def resample_to_16k(audio: np.ndarray, orig_rate: int) -> np.ndarray:
    if orig_rate == SAMPLE_RATE:
        return audio.astype(np.int16)
    n_target = int(round(len(audio) * SAMPLE_RATE / orig_rate))
    resampled = resample(audio.astype(np.float64), n_target)
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def fit_to_clip(audio: np.ndarray, trailing_silence_ms: float) -> np.ndarray:
    """Pad/trim to exactly CLIP_SAMPLES, with `trailing_silence_ms` of
    silence after the audio content (0 = content ends right at the clip
    boundary, as it does the instant a real wake word finishes)."""
    trailing = int(SAMPLE_RATE * trailing_silence_ms / 1000)
    content = audio[: max(0, CLIP_SAMPLES - trailing)]
    pad_end = np.zeros(trailing, dtype=np.int16)
    combined = np.concatenate([content, pad_end])
    if len(combined) >= CLIP_SAMPLES:
        return combined[-CLIP_SAMPLES:]
    pad_start = np.zeros(CLIP_SAMPLES - len(combined), dtype=np.int16)
    return np.concatenate([pad_start, combined])


def synth_clip(text: str, voice: str, pitch: int, speed: int, trailing_silence_ms: float = 0.0) -> np.ndarray:
    audio, rate = espeak_synth(text, voice, pitch, speed)
    audio16k = resample_to_16k(audio, rate)
    return fit_to_clip(audio16k, trailing_silence_ms)


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


def build_train_positive() -> list[np.ndarray]:
    clips = []
    for voice in TRAIN_VOICES:
        for pitch in PITCHES:
            for speed in SPEEDS:
                clips.append(synth_clip(WAKE_WORD, voice, pitch, speed, trailing_silence_ms=0))
    return clips


def build_train_negative() -> list[np.ndarray]:
    clips = []
    for word in NEG_WORDS:
        for voice in TRAIN_VOICES:
            for speed in (SPEEDS[0], SPEEDS[-1]):
                clips.append(synth_clip(word, voice, 50, speed, trailing_silence_ms=0))
    for word in HARD_NEG_WORDS:
        for voice in TRAIN_VOICES:
            for pitch in PITCHES:
                clips.append(synth_clip(word, voice, pitch, 170, trailing_silence_ms=0))
    # Mistimed "Patriot": present in the clip, but not ending at the
    # boundary -- teaches the model that *timing* matters, not just content.
    for voice in TRAIN_VOICES:
        for pitch in PITCHES:
            clips.append(synth_clip(WAKE_WORD, voice, pitch, 170, trailing_silence_ms=500))
    # Silence.
    for _ in range(15):
        clips.append(np.zeros(CLIP_SAMPLES, dtype=np.int16))
    return clips


def build_test_positive() -> list[np.ndarray]:
    clips = []
    for voice in TEST_VOICES:
        for pitch in (40, 60):
            for speed in (150, 190):
                clips.append(synth_clip(WAKE_WORD, voice, pitch, speed, trailing_silence_ms=0))
    return clips


def build_test_negative() -> list[np.ndarray]:
    clips = []
    sample_words = NEG_WORDS[::3]  # a spread, not the exact training subset
    for word in sample_words:
        for voice in TEST_VOICES:
            for speed in (150, 190):
                clips.append(synth_clip(word, voice, 50, speed, trailing_silence_ms=0))
    for word in HARD_NEG_WORDS:
        for voice in TEST_VOICES:
            clips.append(synth_clip(word, voice, 50, 170, trailing_silence_ms=0))
    for voice in TEST_VOICES:
        clips.append(synth_clip(WAKE_WORD, voice, 50, 170, trailing_silence_ms=500))
    return clips


def main():
    print("[build_dataset] synthesizing training positives...")
    pos_train = build_train_positive()
    print(f"[build_dataset] {len(pos_train)} positive training clips")

    print("[build_dataset] synthesizing training negatives...")
    neg_train = build_train_negative()
    print(f"[build_dataset] {len(neg_train)} negative training clips")

    print("[build_dataset] synthesizing held-out test positives...")
    pos_test = build_test_positive()
    print(f"[build_dataset] {len(pos_test)} positive test clips")

    print("[build_dataset] synthesizing held-out test negatives...")
    neg_test = build_test_negative()
    print(f"[build_dataset] {len(neg_test)} negative test clips")

    # Save held-out raw audio for the later end-to-end streaming check.
    manifest = []
    for i, clip in enumerate(pos_test):
        p = HELDOUT_DIR / f"pos_{i:03d}.wav"
        write_wav(p, clip)
        manifest.append({"path": p.name, "label": 1})
    for i, clip in enumerate(neg_test):
        p = HELDOUT_DIR / f"neg_{i:03d}.wav"
        write_wav(p, clip)
        manifest.append({"path": p.name, "label": 0})
    (HELDOUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print("[build_dataset] extracting openWakeWord embeddings (streaming path)...")
    features = AudioFeatures(inference_framework="onnx")

    def streaming_embed_one(clip: np.ndarray) -> np.ndarray:
        # Use the SAME frame-by-frame streaming path (and the library's own
        # noise-based reset()) that real-time inference uses, rather than
        # embed_clips()'s whole-clip batch computation -- the two are not
        # numerically identical (see AudioFeatures._streaming_melspectrogram's
        # own docstring), and training on batch features while predicting
        # with the streaming path measurably hurt accuracy in practice.
        features.reset()
        for i in range(0, len(clip), 1280):
            frame = clip[i:i + 1280]
            features(frame)
        return features.get_features(16)[0]

    def embed(clips: list[np.ndarray]) -> np.ndarray:
        if not clips:
            return np.zeros((0, 16, 96), dtype=np.float32)
        return np.stack([streaming_embed_one(c) for c in clips]).astype(np.float32)

    X_pos_train = embed(pos_train)
    X_neg_train = embed(neg_train)
    X_pos_test = embed(pos_test)
    X_neg_test = embed(neg_test)

    np.savez(
        DATASET_PATH,
        X_pos_train=X_pos_train, X_neg_train=X_neg_train,
        X_pos_test=X_pos_test, X_neg_test=X_neg_test,
    )
    print(f"[build_dataset] wrote {DATASET_PATH} "
          f"(pos_train={X_pos_train.shape}, neg_train={X_neg_train.shape}, "
          f"pos_test={X_pos_test.shape}, neg_test={X_neg_test.shape})")


if __name__ == "__main__":
    main()
