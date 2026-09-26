---
name: drawthings
description: Render prompts through the Draw Things app's API server (gRPC) from the terminal instead of pasting them into the app. Picks a model recipe (Krea 2 Turbo and Ideogram 4 through Draw Things+ cloud compute, or any model the app has locally), runs a seed set one job at a time, retries the cloud's random aborts, saves PNGs with the exact prompt, a run log and a contact sheet, and looks at the results. Use this skill whenever the user wants to generate, render, batch, retry, compare seeds or log image experiments with Draw Things, mentions its API server, gRPC, Bridge Mode or cloud compute, or asks to run a Krea or Ideogram prompt "in Draw Things", even if they only say "render it" or "try a few seeds".
---

# Draw Things API server

The Draw Things app can expose its generation pipeline as a gRPC service, and with **Bridge
Mode** on (Draw Things+ subscribers) every job sent to that service runs on Draw Things'
cloud compute, including cloud-only models that never touch the Mac. This skill drives that
service through the maintained `drawthings-py` SDK (PyPI, GPL-3.0, used as a dependency), adding
the one thing the SDK lacks: the model spec (`override.models`) that cloud-only models need
because the app does not list them. Files, relative to this skill's folder:

- `scripts/dt_render.py` — the renderer: recipe or custom spec, prompt file, seed set, retries, PNGs, `run.json`, `runs.jsonl` line per image, contact sheet.
- `scripts/setup.sh` — one-time virtualenv with the SDK (`~/.cache/drawthings-skill/venv`).
- `scripts/compute_units.py` — the app's compute-unit formula, ported from `ComputeUnits.swift`; the renderer runs it before every job.
- `scripts/png_config.py` — prints the settings and prompt stored in any Draw Things PNG (the app's exports or this renderer's) and the command that reproduces it.
- `recipes.json` — verified model specs and their default settings.
- `references/server.md` — protocol facts, timings, how to derive a spec for a new cloud model, SDK notes.

## 1. Before the first render

The app must be running with, in Settings, Advanced, API Server: protocol gRPC, port 7859,
Transport Layer Security on, Response Compression on, Model Browsing on, and Bridge Mode on
for the cloud recipes. Cloud Compute must also be selected in the app's project. Then, once
per machine:

```bash
bash scripts/setup.sh          # creates the venv, needs Python 3.11+ or uv
python3 scripts/dt_render.py --check
```

`--check` connects over TLS, lists the models the app has locally, and says which recipes
need the cloud. If it cannot connect, the API server is off or another port is set; if a
recipe's file is "not local" and Bridge Mode is off, the job will ask for a download instead
of rendering. The script re-executes itself under the venv, so any `python3` can launch it;
`DRAWTHINGS_PYTHON` overrides the interpreter, `DRAWTHINGS_HOST` and `DRAWTHINGS_PORT` the
server.

## 2. Run a round

Write the prompt with the model's prompting skill first (`krea-prompt` for Krea 2 Turbo,
`ideogram-prompt` for Ideogram 4, which produces a JSON caption), lint or validate it, save it
to a file, then:

```bash
python3 scripts/dt_render.py --recipe krea-2-turbo --prompt-file prompts/krea-2-turbo.txt \
  --seeds 4 --out renders/observer/r12 --log projects/observer/runs.jsonl --note "haze as a surface"
```

- `--seeds 4` draws four random seeds (printed and logged); `--seeds 12345,777` reuses known ones. Seeds run one after another because the server takes one job at a time.
- `--size WxH` overrides the recipe's default (multiples of 64, at most 2048 on a side; `size.py` in the krea-prompt skill gives the size for a ratio). `--steps`, `--cfg`, `--shift`, `--sampler` override the recipe; leave them alone while iterating on a prompt.
- A `.json` prompt file is validated and minified before sending; a `.txt` file is sent as is. `--negative-file` adds a negative prompt where the model uses one (Turbo ignores it).
- `--out` gets `<name>-s<seed>.png` (with Draw Things metadata inside the PNG), a copy of the exact prompt, `run.json` with everything, and `<name>-sheet.jpg` when at least two images succeeded. `--name` sets the base name (default: the prompt file's stem).
- `--log` appends one JSON line per image: settings, seed, timing, prompt hash and file, status, your `--note`. Keep one `runs.jsonl` per project so a whole project's history is one file.
- Expect 15 to 60 s before the first sampling step and 90 to 200 s per 2K image on the cloud (Ideogram at 32 steps is the slow end). A round of four seeds is six to twelve minutes; run it in the background and poll the output.

Change one thing per round, say what in `--note`, and keep the note in the project's
`notes.md` when the round taught something.

## 2b. Compute units (the cloud's per-image budget)

The cloud measures each request in compute units and refuses anything above the tier limit
(10,000 for community, 40,000 for Draw Things+) rather than charging for it. The app shows the
number next to the rocket icon; `dt_render.py` computes the same number before sending, from
the app's own formula (`scripts/compute_units.py`, ported from `ComputeUnits.swift`), prints it,
and stops with exit code 3 when it is over the limit unless `--force` is given. The units grow
with the pixel count (attention is quadratic in the image tokens), the steps, and double when
CFG is on (guidance above 1). Reference points for the recipes:

| Recipe | Size | Steps | Units |
|---|---|---|---|
| krea-2-turbo | 2048x1344 | 8 | about 7,300 |
| ideogram-4 | 1920x1280 | 32 | about 39,500: the recipe default, just under |
| ideogram-4 | 2048x1344 | 20 | about 28,300 (28 steps: about 39,700) |
| ideogram-4 | 2048x1344 | 32 | about 45,300: over the limit |
| ideogram-4 | 2048x2048 | 20 | about 48,700: over the limit |

`--estimate-only` prints the number without connecting; `--tier community` applies the lower
limit; `DRAWTHINGS_TIER` sets the default. The formula is upstream's, with a calibration
constant they tuned on FLUX; treat a result within a few percent of the limit as over it. Checked against the app once: for 1920x1280 at 32 steps with guidance 7 the app showed about 39,000 and the formula gives 39,477.

## 3. Recipes

`--list-recipes` prints them. Verified through Bridge Mode on 2026-09-26:

| Recipe | Model file | Defaults | Prompt |
|---|---|---|---|
| `krea-2-turbo` | `krea_2_turbo_i8x.ckpt` (cloud) | 8 steps, CFG 1.0, shift 3.16, DDIM Trailing, 2048x1344 | plain text from `krea-prompt` |
| `ideogram-4` | `ideogram_4_q8p.ckpt` (cloud) | 32 steps, CFG 7, shift 2.99, DPM++ 2M Trailing, zero negative prompt on, 1920x1280: the app's own settings for "Ideogram 4 remote" | JSON caption from `ideogram-prompt`, up to 2,000 tokens |

A model the app already has locally needs no recipe: `--spec` with a file holding the entry
from `--check`'s list (name, file, version, text encoder, autoencoder, default scale) works,
or add it to `recipes.json` with a `defaults` block and a `notes` line saying what was
verified. For a new cloud-only model, derive the spec as described in `references/server.md`
(the version string, the text encoder and the autoencoder come from the app's open-source
model zoo) and test it at a small size first. Every spec for sizes above 1024 px on a side
needs `default_scale` 32.

## 4. Look, then iterate

After the run, read the contact sheet (or the single PNG) with the image-reading tool and
judge it against the brief before saying anything to the user: composition, the elements the
prompt placed, rendered text, the light, the style label. Then:

- Prefer the prompting skill's iteration section for what to change; the settings stay fixed.
- Pick keepers by seed and say which; the lab convention is a JPEG copy in `keepers/` and the PNG left in `renders/`.
- When two seeds disagree on a detail the prompt specified, the prompt is ambiguous there; when all seeds agree on a wrong detail, the wording is wrong.
- Re-render a known seed after a prompt change to see the change itself, then draw fresh seeds.

## 5. Errors and limits

- **The cloud aborts jobs at random, mostly before the first sampling step**, with `INTERNAL: unknown error processing request` after 20 to 30 s. The script retries any failure that happens before sampling (three extra attempts, 20 s apart, `--retries`/`--retry-wait`). Never conclude a spec, size or prompt is wrong from one failure: repeat it first, bisect only after two failures in a row.
- The same error at the first step on every attempt, for sizes above 1024 px, means `default_scale` 16 in the spec; use 32.
- With Bridge Mode on, every job goes to the cloud: local community checkpoints fail through it. Turn Bridge Mode off to render local models, on for the cloud recipes.
- One job at a time. Do not run two `dt_render.py` at once against one server.
- A cloud model that is `not local` with Bridge Mode off returns a download request instead of an image; the script reports it as an error.
- **Ideogram 4 needs the `q8p` model file.** With `ideogram_4_i8x.ckpt` in the spec, guidance above 1 breaks down as the caption grows: at CFG 7 captions up to about 500 Qwen tokens render, 800 come out blown out, 1,000 and more are noise, while CFG 1 stays clean. With `ideogram_4_q8p.ckpt`, the file behind the app's "Ideogram 4 remote", a 1,309-token caption renders cleanly at CFG 7 with or without zero negative prompt, and the app's own image is reproduced pixel for pixel from its seed and settings. The recipe carries the q8p file; if a render ever shows that pattern again (short captions fine, long ones noise), check the model file before anything else.
- `--timeout` (900 s per image) covers 48-step 2K jobs; raise it for video or larger batches.
- Local LoRAs (`--lora file.ckpt:0.8`) are passed through the configuration and work for local models; the cloud has no access to local LoRA files, so do not expect them on cloud recipes.

## 6. Reproducing an image

Every `runs.jsonl` line has the recipe, model file, size, steps, CFG, shift, sampler, seed,
and the prompt file with its SHA-256; `run.json` in the run folder holds the prompt text
itself. To reproduce: same recipe, `--prompt-file` at the commit whose hash matches,
`--seeds <seed>`. The cloud is deterministic for a given seed and settings in practice, but
the model files behind a recipe can be updated upstream, so keep the keeper.

The app stores the same information in every PNG it exports: an XMP block with the prompt,
the negative prompt, the model file, size, steps, guidance, shift, sampler, seed and every
configuration flag. `python3 scripts/png_config.py image.png` prints it, `--prompt-out
caption.json` saves the prompt, and the last line is the `dt_render.py` command that
reproduces the image. That is how the app's own settings for a cloud model are read, since
macOS keeps other processes out of the app's container and its database; a render made this
way from the app's seed matched the app's image pixel for pixel.
