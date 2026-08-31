#!/usr/bin/env python3
"""Local voice wake-word daemon for Patriot, the daily-assistant plugin.

Runs entirely on your own machine (needs a microphone) -- this is NOT part
of the Claude Code plugin itself and is never invoked automatically by any
skill or hook. See voice/README.md before running this.

Flow: listen for the wake word "Patriot" (a custom-trained openWakeWord
model, see voice/training/) -> once heard, record until you stop talking
-> transcribe locally (faster-whisper, no cloud API, no account) -> open a
new interactive `claude` session with what you said as the opening prompt.

Everything here is local/offline except the one-time model downloads
(openWakeWord's shared feature-extraction models, faster-whisper's model
weights from Hugging Face) -- no ongoing account or API key is used.
"""
from __future__ import annotations

import argparse
import os
import queue
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80ms at 16kHz, the chunk size openWakeWord expects
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "patriot.onnx"


def env_float(name, default):
    return float(os.environ.get(name, default))


def env_str(name, default):
    return os.environ.get(name, default)


WAKE_MODEL_NAME = env_str("WAKE_MODEL_NAME", "patriot")
WAKE_CUSTOM_MODEL_PATH = env_str("WAKE_CUSTOM_MODEL_PATH", str(DEFAULT_MODEL_PATH))
WAKE_THRESHOLD = env_float("WAKE_THRESHOLD", 0.5)
SILENCE_SECONDS = env_float("WAKE_SILENCE_SECONDS", 1.2)
MIN_RECORD_SECONDS = env_float("WAKE_MIN_RECORD_SECONDS", 0.6)
MAX_RECORD_SECONDS = env_float("WAKE_MAX_RECORD_SECONDS", 15.0)
SILENCE_RMS_THRESHOLD = env_float("WAKE_SILENCE_RMS", 300.0)
COOLDOWN_SECONDS = env_float("WAKE_COOLDOWN_SECONDS", 1.5)
WHISPER_MODEL_SIZE = env_str("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = env_str("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = env_str("WHISPER_COMPUTE_TYPE", "int8")
CLAUDE_BIN = env_str("CLAUDE_BIN", "claude")
PATRIOT_REPO_PATH = os.environ.get("PATRIOT_REPO_PATH")
FALLBACK_PROMPT = env_str("WAKE_FALLBACK_PROMPT", "Let's do the daily check-in.")


def normalize_key(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def frame_rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))


def build_wake_model():
    import openwakeword
    from openwakeword.model import Model

    try:
        openwakeword.utils.download_models()
    except Exception as e:
        print(f"[wake] model download check failed (continuing, may already be cached): {e}",
              file=sys.stderr)

    if WAKE_CUSTOM_MODEL_PATH and os.path.exists(WAKE_CUSTOM_MODEL_PATH):
        return Model(wakeword_models=[WAKE_CUSTOM_MODEL_PATH], inference_framework="onnx")

    print(f"[wake] custom model not found at {WAKE_CUSTOM_MODEL_PATH!r} -- "
          "falling back to openWakeWord's bundled pretrained models "
          "(set WAKE_MODEL_NAME to alexa/hey mycroft/hey rhasspy in that case).",
          file=sys.stderr)
    return Model()


def resolve_wake_key(model, target_name: str) -> str:
    silent_frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    scores = model.predict(silent_frame)
    keys = list(scores.keys())
    target = normalize_key(target_name)
    for k in keys:
        if normalize_key(k) == target:
            return k
    for k in keys:
        if target in normalize_key(k) or normalize_key(k) in target:
            return k
    print(f"[wake] No loaded wake-word model matches WAKE_MODEL_NAME={target_name!r}.",
          file=sys.stderr)
    print(f"[wake] Available models: {keys}", file=sys.stderr)
    sys.exit(1)


def write_wav(path: str, frames: list[np.ndarray]) -> None:
    audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


def transcribe(path: str, whisper_model) -> str:
    segments, _info = whisper_model.transcribe(path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments).strip()


def launch_claude(prompt: str) -> None:
    claude_cmd = [CLAUDE_BIN]
    if PATRIOT_REPO_PATH:
        claude_cmd += ["--plugin-dir", PATRIOT_REPO_PATH]
    claude_cmd += [prompt]
    shell_command = " ".join(shlex.quote(part) for part in claude_cmd)

    if sys.platform == "darwin" and shutil.which("osascript"):
        # AppleScript string literal: escape backslashes then double quotes.
        escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "Terminal" to do script "{escaped}"'
        subprocess.run(["osascript", "-e", script], check=False)
    else:
        print(f"[wake] Don't know how to open a terminal on this platform. "
              f"Run this yourself:\n  {shell_command}")


def list_devices():
    import sounddevice as sd
    print(sd.query_devices())


def run(dry_run: bool, device: int | None):
    import sounddevice as sd

    print(f"[wake] loading wake-word model (target phrase: {WAKE_MODEL_NAME!r})...")
    model = build_wake_model()
    wake_key = resolve_wake_key(model, WAKE_MODEL_NAME)
    print(f"[wake] matched wake-word model key: {wake_key!r} (threshold={WAKE_THRESHOLD})")

    print(f"[wake] loading faster-whisper model '{WHISPER_MODEL_SIZE}' "
          f"({WHISPER_DEVICE}/{WHISPER_COMPUTE_TYPE})... this can take a while the first time")
    from faster_whisper import WhisperModel
    whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE,
                                  compute_type=WHISPER_COMPUTE_TYPE)

    audio_q: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames_count, time_info, status):
        if status:
            print(f"[wake] audio status: {status}", file=sys.stderr)
        audio_q.put(indata[:, 0].copy())

    print("[wake] listening... (Ctrl+C to stop)")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                         blocksize=FRAME_SAMPLES, device=device, callback=callback):
        state = "listening"
        recorded: list[np.ndarray] = []
        elapsed = 0.0
        silence_dur = 0.0
        frame_duration = FRAME_SAMPLES / SAMPLE_RATE

        while True:
            frame = audio_q.get()

            if state == "listening":
                scores = model.predict(frame)
                if scores.get(wake_key, 0.0) >= WAKE_THRESHOLD:
                    print("[wake] wake word detected -- listening for your command...")
                    state = "recording"
                    recorded = []
                    elapsed = 0.0
                    silence_dur = 0.0
                continue

            # state == "recording"
            recorded.append(frame)
            elapsed += frame_duration
            rms = frame_rms(frame)
            silence_dur = silence_dur + frame_duration if rms < SILENCE_RMS_THRESHOLD else 0.0

            done = (silence_dur >= SILENCE_SECONDS and elapsed >= MIN_RECORD_SECONDS) \
                or elapsed >= MAX_RECORD_SECONDS
            if not done:
                continue

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            try:
                write_wav(wav_path, recorded)
                print("[wake] transcribing...")
                text = transcribe(wav_path, whisper_model)
            finally:
                os.unlink(wav_path)

            prompt = text if text else FALLBACK_PROMPT
            print(f"[wake] heard: {prompt!r}")
            if dry_run:
                print("[wake] --dry-run set, not launching claude")
            else:
                launch_claude(prompt)

            # Reload the wake model fresh so its internal buffers can't carry
            # over state from the command we just recorded.
            time.sleep(COOLDOWN_SECONDS)
            model = build_wake_model()
            wake_key = resolve_wake_key(model, WAKE_MODEL_NAME)
            state = "listening"
            print("[wake] listening...")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                    help="Detect and transcribe, but don't launch claude")
    p.add_argument("--list-devices", action="store_true",
                    help="List audio input devices and exit")
    p.add_argument("--device", type=int, default=None,
                    help="Input device index (see --list-devices)")
    args = p.parse_args()

    if args.list_devices:
        list_devices()
        return

    try:
        run(dry_run=args.dry_run, device=args.device)
    except KeyboardInterrupt:
        print("\n[wake] stopped.")


if __name__ == "__main__":
    main()
