# Voice wake word: "Patriot" (local, macOS)

A real spoken wake word — **"Patriot"** — that starts a conversation with
this plugin, without typing anything. Same name as the plugin itself.

**This cannot run in the cloud/CI environment this plugin was built in --
it needs a real microphone on your own Mac.** The wake-word model was
trained and validated entirely on synthetic (text-to-speech) audio in that
same environment -- see `training/README.md` for exactly how, and its
"Known limitations" section for what that does and doesn't prove. Treat
first real-world run as a tuning session, not a sure thing.

## How it works

```
mic audio --> openWakeWord, using a custom-trained "Patriot" model
           --> [wake word heard] --> record until you stop talking
           --> faster-whisper (local speech-to-text)
           --> opens a new Terminal window running:  claude "<what you said>"
```

Everything runs locally:
- **openWakeWord** — open-source, no account, no API key. The detector
  here is `models/patriot.onnx`, a small classifier trained specifically
  on the word "Patriot" (see `training/`) rather than one of
  openWakeWord's built-in phrases.
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

The first run also downloads openWakeWord's shared feature-extraction
models and the faster-whisper model weights (a couple hundred MB total) --
this needs network access once, then works fully offline. The
`patriot.onnx` wake-word model itself is already committed in this repo
under `voice/models/` -- nothing to train or download for that part.

## Try it manually first

```bash
python3 wake_daemon.py --list-devices     # find your mic if the default is wrong
python3 wake_daemon.py --dry-run --device <N>
```

`--dry-run` detects the wake word and prints the transcribed text, but
doesn't launch `claude` -- use it to tune things before it starts opening
terminal windows on you. Say "Patriot" (pause briefly), then say a command
like "what's on my plate today."

Things you'll likely need to tune (all via env vars, see the table below):
- **False triggers or missed triggers**: adjust `WAKE_THRESHOLD` (lower =
  more sensitive/more false positives, default `0.5`). Since this model was
  trained on synthetic voices only, expect to need to retune this against
  your real voice/room more than you would with an off-the-shelf phrase --
  see `training/README.md` for how to add real recordings and retrain.
- **Recording cuts you off too early/late**: adjust `WAKE_SILENCE_RMS`
  (your room's noise floor) and `WAKE_SILENCE_SECONDS` (how much silence
  = "done talking").
- **Want a different phrase after all**: set `WAKE_MODEL_NAME` to one of
  openWakeWord's bundled presets (`alexa` / `hey mycroft` / `hey rhasspy`)
  and leave `WAKE_CUSTOM_MODEL_PATH` unset/pointed at a missing file --
  the daemon falls back to the bundled pretrained models automatically.

## Running for real

```bash
python3 wake_daemon.py
```

This runs in the foreground and opens a Terminal window each time it hears
the wake word + a command. Ctrl+C to stop.

## Config (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `WAKE_MODEL_NAME` | `patriot` | Which wake-word model key to match/trigger on |
| `WAKE_CUSTOM_MODEL_PATH` | `voice/models/patriot.onnx` | Path to the custom model; if missing, falls back to openWakeWord's bundled pretrained models |
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
| `PATRIOT_REPO_PATH` | (unset) | Path to this repo checkout; if set, launches `claude --plugin-dir <path>` so the plugin loads regardless of install scope |
| `WAKE_FALLBACK_PROMPT` | `Let's do the daily check-in.` | Used if nothing intelligible was transcribed |

If you installed the plugin at **user scope** (persists across
directories -- see the main README), you can leave `PATRIOT_REPO_PATH`
unset. If you only ever ran it via `--plugin-dir` manually, set this so the
launched session actually has the plugin available.

## Auto-start at login (optional)

A LaunchAgent template is in `voice/launchd/com.patriot.wakedaemon.plist.template`.
It is a template on purpose -- copy it, fill in the placeholders, then load it:

```bash
cp voice/launchd/com.patriot.wakedaemon.plist.template \
   ~/Library/LaunchAgents/com.patriot.wakedaemon.plist

# Edit the copy and replace:
#   __PYTHON_BIN__  -> full path to the venv's python, e.g.
#                       /Users/you/DailyAgent/voice/.venv/bin/python3
#   __REPO_PATH__   -> full path to this repo checkout
#   __HOME__        -> your home directory, e.g. /Users/you

launchctl load ~/Library/LaunchAgents/com.patriot.wakedaemon.plist
```

Logs land at `~/Library/Logs/patriot-wake.log`. To stop it:

```bash
launchctl unload ~/Library/LaunchAgents/com.patriot.wakedaemon.plist
```

Get the manual `--dry-run` flow working well first -- don't jump straight
to always-on background listening.

## Known limitations

- macOS only right now (uses `osascript`/Terminal.app to open the session).
  On another platform, the script will just print the command to run
  yourself instead of failing silently.
- The wake-word model (`training/README.md` has full details) was trained
  and validated only on synthetic TTS voices, never a real human ear or
  microphone -- real-world accuracy (both missed wake-ups and false
  triggers on unrelated speech) is unverified until you actually try it.
- No wake-word-to-wake-word overlap handling beyond a fixed cooldown; if
  you say the wake word again immediately after a command, it should still
  work, just not mid-cooldown.
- One command per wake word -- it's not a continuous conversation; each
  utterance opens (or would need to be sent to) a session on its own. If
  you want to add to an *existing* running Claude Code session instead of
  always opening a new one, that's a reasonable next step but isn't built
  here.
