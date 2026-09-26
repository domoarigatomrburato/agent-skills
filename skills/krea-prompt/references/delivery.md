# Delivering a Krea 2 prompt

Settings, request shapes and size tables for every place Krea 2 Turbo runs. Sources are named per
section; where a value is inferred rather than documented, it says so.

## 1. Which Krea 2 is which

| Model | Where | Steps / guidance | Resolution | Expansion, sliders, references |
|---|---|---|---|---|
| Krea 2 Turbo (open weights) | Draw Things, ComfyUI, fal, reference CLI, Diffusers | 8 steps, guidance off, fixed `mu = 1.15` | 1K to 2K | none (LoRAs only) |
| Krea 2 Raw (open weights) | same | 52 steps, `cfg 3.5` (Krea convention) | up to 1K | none; the checkpoint for training LoRAs |
| Krea 2 Turbo (hosted, API name `medium-turbo`) | Krea app, API, MCP | managed | 1K | creativity, sliders, style refs, moodboards, styles |
| Krea 2 Medium / Large (hosted) | Krea app, API, MCP | managed | 1K | same as hosted Turbo |

Krea's own guidance on the pair: "Train LoRAs on Krea 2 RAW, then apply them on Krea 2 Turbo. LoRAs
trained on RAW are designed to express strongly on Turbo." And on the hosted tiers: start with
Medium, go to Large for photorealism and raw texture, use Turbo to explore.

## 2. Guidance conventions, so numbers do not get mistranslated

Krea's code computes `v = cond + g * (cond - uncond)` and enables guidance whenever `g > 0`. That
equals the usual classifier-free guidance with scale `1 + g`. So:

| Krea value | Standard CFG (ComfyUI, Draw Things "Text Guidance") |
|---|---|
| Turbo `--cfg 0.0` | 1.0 (guidance off) |
| Raw `--cfg 3.5` (README recommendation) | 4.5 |
| Raw `--cfg 4.5` (CLI and Diffusers default) | 5.5 |

Turbo takes no negative prompt at all; the Diffusers Turbo pipeline has no guider and no
`negative_prompt` input.

## 3. Timestep shift

`sampling.py` interpolates `mu` between 0.5 at the smallest training resolution and 1.15 at the
largest, and pins `mu = 1.15` for the distilled checkpoint. The schedule is
`t' = exp(mu) / (exp(mu) + (1/t - 1))`, which is the FLUX-style shift with multiplier `exp(mu)`.

| Form | Turbo | Raw at 1K |
|---|---|---|
| `mu` (Krea CLI `--mu`, Diffusers `max_shift`) | 1.15 | resolution-derived, about 1.15 at 1024 x 1024 |
| multiplier `exp(mu)` (apps that expose "Shift") | 3.16 | about 3.16 |

Draw Things exposes the multiplier form (its FLUX presets show `mu = 1.15` as 3.16), so 3.16 is the
value to type by hand. A community issue reporter used 1.15 literally; if the app pre-fills the
field when you select the model, keep the app's value. Turn any resolution-dependent shift option
off for Turbo, since the distilled schedule is fixed.

## 4. Draw Things

Supported since v1.20260716.0 (Krea 2 Turbo and Raw, 8-bit, 6-bit, 6-bit S and 8-bit S variants),
with `qwen_3_vl_4b` as the text encoder download.

| Setting | Turbo | Raw |
|---|---|---|
| Steps | 8 | 52 (28 to 52 is the documented range) |
| Text Guidance | 1.0 | 4.5 |
| Negative prompt | leave empty | optional, works only with guidance on |
| Shift | 3.16 | 3.16 at 1K |
| Sampler | DDIM Trailing (closest to the reference plain Euler), DPM++ 2M Trailing for a second opinion; no ancestral, Karras, SDE or LCM samplers | same |
| Size | multiples of 64 in the UI; 1K to 2K | up to 1K |
| Tiled decode | on above about 2.9 MP with the 8-bit model: 640 x 640 tiles, 128 overlap (community issue 105) | not needed at 1K |
| Prompt expansion | none; paste the full prompt | none |
| Seed | any; Scale Alike keeps composition across sizes | same |

No creativity, sliders, style references or moodboards exist in Draw Things. Style comes from the
prompt, or from a LoRA trained on Raw and applied to Turbo.

Draw Things sizes for the open-weights Turbo (all multiples of 64, under the 2.9 MP decode limit
unless marked):

| Ratio | 1K | 2K (or the largest under the width cap) |
|---|---|---|
| 1:1 | 1024 x 1024 | 2048 x 2048 (4.19 MP, tiled decode); 1664 x 1664 (2.77 MP) without |
| 4:3 | 1152 x 896 | 2048 x 1536 (3.15 MP, tiled decode); 1792 x 1344 (2.41 MP) without |
| 3:2 | 1216 x 832 | 2048 x 1344 (2.75 MP) |
| 16:9 | 1344 x 768 | 2048 x 1152 (2.36 MP) |
| 2.35:1 | 1536 x 640 | 2048 x 896 (1.84 MP) |
| 4:5 | 896 x 1088 | 1664 x 2048 (3.41 MP, tiled decode); 1408 x 1792 (2.52 MP) without |
| 2:3 | 832 x 1216 | 1344 x 2048 (2.75 MP) |
| 9:16 | 768 x 1344 | 1152 x 2048 (2.36 MP) |

`scripts/size.py` computes any other case, in multiples of 16 or 64.

## 5. Krea app (krea.ai/image)

Pick Krea 2 Turbo in the model picker. Controls: prompt, aspect ratio (1:1, 4:3, 3:2, 16:9,
2.35:1, 4:5, 2:3, 9:16 at 1K), creativity (Raw, Low, Medium, High; Medium is the app default), up
to 4 style references with per-image strength, one moodboard, Krea styles (LoRAs), the Intensity,
Complexity and Movement sliders, seed, batch of up to 4. Two credits per generation, about 4 seconds.

Set creativity to Raw when pasting a full description from this skill, and always when the prompt
contains quoted text. Set it to High with a short prompt, and no text to render, when the user wants
exploration. Use a style reference or moodboard instead of paragraphs of style prose whenever the
user has an image of the look; a reference contributes look, not content, so objects the user wants
in the frame still go in the prompt.

## 6. Krea API

Endpoints (all `POST https://api.krea.ai` + path, JSON body, `Authorization: Bearer $KREA_API_TOKEN`):

| Model | Path | Price per image (text-to-image / with style refs / with moodboard) |
|---|---|---|
| Krea 2 Turbo | `/generate/image/krea/krea-2/medium-turbo` | $0.015 / $0.0175 / $0.02 |
| Krea 2 Medium | `/generate/image/krea/krea-2/medium` | $0.030 / $0.035 / $0.040 |
| Krea 2 Large | `/generate/image/krea/krea-2/large` | $0.060 / $0.065 / $0.070 |

Request body for Turbo, from the OpenAPI schema (`additionalProperties: false`, so unknown keys are rejected):

| Field | Type | Values | Default | Required |
|---|---|---|---|---|
| `prompt` | string | | | yes |
| `aspect_ratio` | string | `1:1`, `4:3`, `3:2`, `16:9`, `2.35:1`, `4:5`, `3:4`, `2:3`, `9:16` | | yes |
| `resolution` | string | `1K` | | yes |
| `seed` | number or null | | | no |
| `creativity` | string | `raw`, `low`, `medium`, `high` | `low` | no |
| `intensity`, `complexity`, `movement` | integer | -100 to 100 | 0 | no |
| `image_style_references` | array, max 10 | `{url, strength 0..1}` | strength 0.5 | no |
| `moodboards` | array, max 1 | `{id (uuid), strength 0..1}` | strength 0.23 | no |
| `styles` | array | `{id, strength -2..2}` | | no |
| `image_url` | uri or null | source image for image-to-image | | no |
| `strength` | number | 0 keeps the input, 1 ignores it | 0.99 | no |

Optional headers: `X-Webhook-URL` for completion callbacks, `X-Api-Zero-Data-Retention: 1`.

The response is a job: `{"job_id": ..., "status": "queued" | "processing" | "sampling" | "completed" | "failed" | ...}`.
Poll `GET /jobs/{job_id}` until `status` is `completed`, then read `result.urls`.

```bash
curl -s -X POST https://api.krea.ai/generate/image/krea/krea-2/medium-turbo \
  -H "Authorization: Bearer $KREA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{"prompt": "<prompt>", "aspect_ratio": "3:2", "resolution": "1K", "creativity": "raw", "seed": 7}
JSON
```

```python
import os, time, requests
API = "https://api.krea.ai"
H = {"Authorization": f"Bearer {os.environ['KREA_API_TOKEN']}"}
job = requests.post(f"{API}/generate/image/krea/krea-2/medium-turbo", headers=H,
                    json={"prompt": PROMPT, "aspect_ratio": "3:2", "resolution": "1K",
                          "creativity": "raw"}).json()
while True:
    j = requests.get(f"{API}/jobs/{job['job_id']}", headers=H).json()
    if j["status"] == "completed":
        print(j["result"]["urls"]); break
    if j["status"] in ("failed", "cancelled"):
        raise SystemExit(j.get("error"))
    time.sleep(3)
```

Read the token from the environment. Never echo it, log it, or place it in a prompt.

## 7. Krea MCP server

URL `https://api.krea.ai/mcp`, streamable HTTP, OAuth sign-in (no API key needed; billing goes to
the workspace chosen at consent), or an API token billed to the API balance. Tools cover model
discovery, schema inspection, asset upload and generation. Read the generate tool's schema in the
session before calling it; the fields mirror the API table above. Generation spends the user's
compute units, so generate only when they asked for an image.

## 8. ComfyUI

Krea's official template (docs.comfy.org, "Krea-2 ComfyUI Workflow Example") uses
`krea2_turbo_fp8_scaled.safetensors` (diffusion model), `qwen3vl_4b_fp8_scaled.safetensors` (text
encoder) and `qwen_image_vae.safetensors` (VAE). Defaults: 8 steps, "prompt enhancement enabled",
no LoRA. Turn the LLM expansion node off when pasting a full description. CFG 1.0 in ComfyUI terms.
Set megapixels to 2.0 for 2K. Nine style LoRAs ship with recommended strength 1.0, and a
`krea2_style_reference.safetensors` LoRA enables image style reference conditioning with the
`krea2_turbo_int8_convrot.safetensors` checkpoint.

## 9. fal

`fal-ai/krea-2/turbo`: `prompt`, `seed` (image *i* uses `seed + i`), `image_size` (`square_hd`,
`square`, `portrait_4_3`, `portrait_16_9`, `landscape_4_3`, `landscape_16_9`, or custom
`{width, height}`), `num_images`, `acceleration` (`none`, `regular`), `enable_prompt_expansion`,
`enable_safety_checker`, `output_format` (`png`, `jpeg`), `sync_mode`. The response includes
`actual_prompt` when expansion ran. Set `enable_prompt_expansion: false` for a full description. A
LoRA endpoint exists at `fal-ai/krea-2/turbo/lora`, and training at `fal-ai/krea-2-trainer`.

## 10. Reference CLI and Diffusers

Reference repository (`uv sync`, checkpoints from Hugging Face, `OSS_TURBO` and `OSS_RAW` env vars):

```bash
uv run inference.py "<prompt>" --checkpoint oss_turbo --steps 8 --cfg 0.0 --mu 1.15 --width 2048 --height 1344
uv run inference.py "<prompt>" --checkpoint oss_raw --steps 52 --cfg 3.5
```

Flags: `--steps` (default 28), `--cfg` (default 4.5, 0 disables), `--y1` 0.5 and `--y2` 1.15 (mu at
min and max resolution), `--mu` (pin a constant shift; 1.15 for Turbo), `--width`/`--height`
(padded up to a multiple of 16), `--num-images`, `--seed` (image *i* uses `seed + i`), `--output`.

Diffusers (`Krea2Pipeline`): Turbo `num_inference_steps=8, guidance_scale=0.0`; Raw
`num_inference_steps=28, guidance_scale=4.5` in Krea's convention. `max_sequence_length=512`.
The scheduler uses `base_shift=0.5`, `max_shift=1.15`, `base_image_seq_len=256`,
`max_image_seq_len=6400`; the Turbo pipeline (`is_distilled=True`) pins `mu = 1.15`.

## 11. LoRAs and styles

Train on Raw, run on Turbo. Krea recommends Diffusers, Ostris AI Toolkit, fal's trainer and Kohya's
musubi tuner for training. In the hosted API, `styles` takes `{id, strength}` with strength -2 to 2;
in the app they are "Krea styles". A trained style replaces paragraphs of style description, so when
one is in play keep the prompt to subject, composition and light.

## 12. License and safety, in one paragraph

Open weights are under the Krea 2 Community License with an Acceptable Use Policy and a commercial
revenue threshold; above it, a commercial license from opensource@krea.ai. The license requires
deployers to run content filtering or equivalent review. The hosted API is under the standard API
terms and runs Krea's own input and output classifiers.
