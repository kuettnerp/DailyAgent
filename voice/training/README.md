# Training the "Patriot" wake-word model

This is how `voice/models/patriot.onnx` (already committed -- you don't
need to run any of this to use the daemon) was built, and how to retrain
it, e.g. after adding real recordings of your own voice.

## Honest summary first

This model was trained **entirely on synthetic text-to-speech audio**,
generated and validated in a sandboxed cloud environment with no
microphone. It has never heard a real human voice. Held-out results (on
synthetic speech, different simulated accents than training used):

```
positive clips: 8,  recall = 0.75   (6/8 detected)
negative clips: 70, false_positive_rate = 0.057  (4/70 false-fired)
```

The 4 false positives were concentrated in the *hardest* cases by design
(phonetically-similar words like "patrol"/"petrol", and "Patriot" spoken
but not ending at the clip boundary) -- zero false positives on the
broad set of unrelated words/phrases. That's a reasonable signal that the
model learned the right thing in principle, on synthetic speech. **It says
nothing definitive about real-world accuracy on your actual voice, mic,
and room** -- treat `WAKE_THRESHOLD` and this model itself as a starting
point to tune (see the "Improving it" section below), not a finished
product.

## Why synthetic TTS instead of real recordings or Piper

The original plan was openWakeWord's own recommended approach: synthesize
positives with Piper TTS's neural voices. Piper's voice models are hosted
on Hugging Face, which this environment's network policy blocks (unrelated
to openWakeWord itself -- its own feature-extraction models and pretrained
wake words download fine, since those are GitHub release assets). Piper
was swapped for `espeak-ng` (installed via the OS package manager, fully
local, no downloads): a formant synthesizer, much more robotic-sounding
than Piper, but real phonetic/spectral structure for "Patriot" vs.
everything else, which is what the classifier actually learns from.

## Pipeline

```
build_dataset.py    espeak-ng synthesizes clips -> openWakeWord embeddings -> dataset.npz
train_model.py       dataset.npz -> trains a small classifier -> voice/models/patriot.onnx
validate_streaming.py  loads the .onnx through the SAME inference path wake_daemon.py
                        uses, streams held-out clips through it frame-by-frame
```

### 1. `build_dataset.py`

- Synthesizes "Patriot" (positives) across 5 espeak-ng voices x 3 pitches x
  3 speeds = 45 training clips, all trimmed/padded to exactly 2.0 seconds
  with the word ending right at the clip boundary (openWakeWord's default
  architecture uses a 16-frame / 2.0s context window, so this is exactly
  what the model sees mid-utterance in real time).
- Synthesizes ~540 negative training clips: ~35 common
  words/phrases across the same voices/speeds, 6 "hard negative" words
  phonetically close to "Patriot" (patrol, patriots, patriotic, petrol,
  patron, matter), "Patriot" itself but with 500ms of trailing silence
  (present in the clip, but not *just finished* -- teaches timing, not
  just content), and some pure silence.
- Holds out 2 entirely different espeak-ng accents (`en-gb-scotland`,
  `en-gb-x-gbcwmd`) that never appear in training, and builds a small
  positive/negative test set from those, to at least test generalization
  across *synthetic* voices.
- **Important**: embeddings are extracted using openWakeWord's own
  streaming code path (`AudioFeatures.reset()` + feeding 80ms frames one
  at a time), not the batch `embed_clips()` helper. The two are not
  numerically identical (openWakeWord's own code says so), and training on
  batch features while the daemon predicts via the streaming path
  measurably hurt real accuracy during development here -- matching the
  exact runtime path mattered more than anything else tried.

### 2. `train_model.py`

A plain, from-scratch supervised training loop (400 epochs, batch size 32,
Adam, positive-class upweighted to offset the ~12:1 negative:positive
ratio) over a small feed-forward network that intentionally mirrors
openWakeWord's own default "dnn" architecture (`Linear(16*96->128) ->
LayerNorm -> ReLU`, one residual-style block, `Linear(128->1)` +
sigmoid) so the exported ONNX file is a drop-in `wakeword_models` entry.
Keeps the checkpoint with the best `held-out recall - false positive rate`
score rather than just the last epoch, then exports to ONNX
(`torch.onnx.export(..., dynamo=False)` -- the newer dynamo-based exporter
pulls in `onnxscript`, which isn't otherwise needed here).

### 3. `validate_streaming.py`

Loads the exported model through `openwakeword.model.Model` (the exact
class `wake_daemon.py` uses) and streams each held-out clip through it
frame-by-frame, priming with quiet random noise first (not literal
silence -- zero-padding is specifically called out in openWakeWord's own
code as where the streaming/batch numerical paths diverge most). Reports
recall and false-positive rate the same way the daemon would actually
experience them.

## Re-running it

```bash
cd voice/training
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-training.txt
sudo apt-get install -y espeak-ng   # or: brew install espeak-ng

python3 build_dataset.py
python3 train_model.py
python3 validate_streaming.py
```

`build_dataset.py` and `train_model.py` both run in well under two minutes
on a plain CPU.

## Improving it (recommended before relying on this day to day)

The single highest-value thing you can do is add **real recordings of your
own voice** as additional positives, and real background/room audio as
additional negatives, then retrain:

1. Record yourself saying "Patriot" ~20-30 times (varying tone/distance/
   background noise) as 16kHz mono WAV files, plus some clips of yourself
   saying other things and just ambient room noise.
2. In `build_dataset.py`, add a step that loads those WAVs (via `wave` or
   `scipy.io.wavfile`), runs them through `fit_to_clip()` to normalize to
   2.0s the same way synthetic clips are, and mixes them into
   `pos_train`/`neg_train` before the embedding-extraction step.
3. Re-run `train_model.py` and `validate_streaming.py`.

Real audio in the mix, even a modest amount, should close most of the gap
between "measured well on synthetic held-out data" and "actually reliable
on your voice."
