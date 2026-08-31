# Voice wake word (local, macOS)

A real spoken wake word ("Hey Jarvis", by default) that starts a
conversation with this plugin's daily-assistant, without typing anything.

**This cannot run in the cloud/CI environment this plugin was built in --
it needs a real microphone on your own Mac.** Nothing here has been
smoke-tested against actual audio hardware; treat first run as a
debugging session, not a sure thing, and tune the settings below.

## How it works

```
mic audio --> openWakeWord (wake-word detection)
           --> [wake word heard] --> record until you stop talking
           --> faster-whisper (local speech-to-text)
           --> opens a new Terminal window running:  claude "<what you said>"
```

Everything runs locally:
- **openWakeWord** — open-source, no account, no API key. Ships a few
  pretrained wake phrases (`alexa`, `hey mycroft`, `hey jarvis`,
  `hey rhasspy`, plus `weather`/`timers`). Default here is `hey jarvis`.
- **faster-whisper** — local Whisper inference, no API key, no audio ever
  leaves your machine.

Nothing here is wired into the Claude Code plugin itself (no skill or hook
calls this) -- it's a standalone script you run yourself.

## Setup

```bash
cd voice
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

macOS will prompt for microphone access the first time you run it --
approve it (System Settings → Privacy & Security → Microphone).

The first run also downloads openWakeWord's pretrained models and the
faster-whisper model weights (a few hundred MB total) — this needs network
access once, then works fully offline.

## Try it manually first

```bash
python3 wake_daemon.py --list-devices     # find your mic if the default is wrong
python3 wake_daemon.py --dry-run --device <N>
```

`--dry-run` detects the wake word and prints the transcribed text, but
doesn't launch `claude` -- use it to tune things before it starts opening
terminal windows on you. Say "hey jarvis" (pause briefly), then say a
command like "what's on my plate today."

Things you'll likely need to tune (all via env vars, see the table below):
- **False triggers or missed triggers**: adjust `WAKE_THRESHOLD` (lower =
  more sensitive/more false positives, default `0.5`).
- **Recording cuts you off too early/late**: adjust `WAKE_SILENCE_RMS`
  (your room's noise floor) and `WAKE_SILENCE_SECONDS` (how much silence
  = "done talking").
- **Want a different phrase**: set `WAKE_MODEL_NAME` to one of
  `alexa` / `hey mycroft` / `hey rhasspy`. A truly custom phrase isn't
  supported out of the box -- openWakeWord supports training one via its
  own notebook (`notebooks/training_models.ipynb` in the openWakeWord
  repo), which is a separate, heavier undertaking left for later if you
  want it.

## Running for real

```bash
python3 wake_daemon.py
```

This runs in the foreground and opens a Terminal window each time it hears
the wake word + a command. Ctrl+C to stop.

## Config (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `WAKE_MODEL_NAME` | `hey jarvis` | Which bundled wake phrase to listen for |
| `WAKE_THRESHOLD` | `0.5` | Confidence to trigger (0-1) |
| `WAKE_SILENCE_SECONDS` | `1.2` | Trailing silence that ends your command |
| `WAKE_MIN_RECORD_SECONDS` | `0.6` | Won't stop recording before this even if silent |
| `WAKE_MAX_RECORD_SECONDS` | `15` | Hard cap per command |
| `WAKE_SILENCE_RMS` | `300` | Noise floor below which audio counts as silence |
| `WAKE_COOLDOWN_SECONDS` | `1.5` | Pause after handling one command before listening again |
| `WHISPER_MODEL_SIZE` | `base` | `tiny`/`base`/`small`/`medium`/`large-v3` -- bigger = more accurate, slower |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Quantization; `int8` is the fast CPU option |
| `CLAUDE_BIN` | `claude` | Path to the Claude Code CLI if not on PATH |
| `DAILY_ASSISTANT_REPO_PATH` | (unset) | Path to this repo checkout; if set, launches `claude --plugin-dir <path>` so the plugin loads regardless of install scope |
| `WAKE_FALLBACK_PROMPT` | `Let's do the daily check-in.` | Used if nothing intelligible was transcribed |

If you installed the plugin at **user scope** (persists across
directories -- see the main README), you can leave
`DAILY_ASSISTANT_REPO_PATH` unset. If you only ever ran it via
`--plugin-dir` manually, set this so the launched session actually has the
plugin available.

## Auto-start at login (optional)

A LaunchAgent template is in `voice/launchd/com.dailyagent.wakedaemon.plist.template`.
It is a template on purpose -- copy it, fill in the placeholders, then load it:

```bash
cp voice/launchd/com.dailyagent.wakedaemon.plist.template \
   ~/Library/LaunchAgents/com.dailyagent.wakedaemon.plist

# Edit the copy and replace:
#   __PYTHON_BIN__  -> full path to the venv's python, e.g.
#                       /Users/you/DailyAgent/voice/.venv/bin/python3
#   __REPO_PATH__   -> full path to this repo checkout
#   __HOME__        -> your home directory, e.g. /Users/you

launchctl load ~/Library/LaunchAgents/com.dailyagent.wakedaemon.plist
```

Logs land at `~/Library/Logs/dailyagent-wake.log`. To stop it:

```bash
launchctl unload ~/Library/LaunchAgents/com.dailyagent.wakedaemon.plist
```

Get the manual `--dry-run` flow working well first -- don't jump straight
to always-on background listening.

## Known limitations

- macOS only right now (uses `osascript`/Terminal.app to open the session).
  On another platform, the script will just print the command to run
  yourself instead of failing silently.
- No wake-word-to-wake-word overlap handling beyond a fixed cooldown; if
  you say the wake word again immediately after a command, it should still
  work, just not mid-cooldown.
- One command per wake word -- it's not a continuous conversation; each
  utterance opens (or would need to be sent to) a session on its own. If
  you want to add to an *existing* running Claude Code session instead of
  always opening a new one, that's a reasonable next step but isn't built
  here.
- Pretrained openWakeWord models are licensed CC-BY-NC-SA (non-commercial),
  which is fine for personal use like this.
