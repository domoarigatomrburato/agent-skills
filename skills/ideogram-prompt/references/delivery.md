# Delivering prompts to Ideogram 4

Sources: developer.ideogram.ai API reference (`generate-v4`, `generate-transparent-v4`,
`magic-prompt-v4`, `describe-v4`, OpenAPI spec), ideogram.ai/features/mcp, the "Ideogram 4.0
prompt guide" blog post, docs.ideogram.ai generation settings, and `ideogram-oss/ideogram4`
(README, `docs/inference.md`, `run_inference.py`, `magic_prompt.py`).

## Contents

1. Ideogram MCP (agents)
2. REST API
3. Web app
4. Open weights
5. Resolutions and aspect ratios
6. Describe → style recipe → apply
7. Safety and errors

## 1. Ideogram MCP

- Endpoint: `https://mcp.ideogram.ai/mcp`, streamable HTTP, OAuth through the user's Ideogram
  account (a browser window opens on first connect). Usage draws from the user's Ideogram
  subscription credits.
- Claude Code: `claude mcp add ideogram --transport http https://mcp.ideogram.ai/mcp`
- Claude Desktop `claude_desktop_config.json`:
  `{"mcpServers":{"ideogram":{"transport":"http","url":"https://mcp.ideogram.ai/mcp"}}}`
- Tools advertised officially: `generate_image`, `generate_images_bulk` (`num_images`),
  `describe_image`, `remix_image`, `edit_image`, `remove_background`, `reframe_image`
  (`aspect` or `resolution`), `upscale_image`, `upload_image`, `create_collection`,
  `get_images_by_collection_id`, `create_dataset`, `upload_dataset_assets`, `train_model`.
  The blog's example call shows `generate_image` taking a `prompt` string, a `model_uri` such as
  `model/V_4_0/version/0`, and a `resolution` such as `736x1312`.

How to use it from this skill:

1. **Read the live tool schema** before the first call; the exact parameter names and enums can
   change, and only the schema in your session is authoritative.
2. **JSON mode**: put the minified caption string in the prompt parameter. If the tool exposes a
   magic-prompt switch (`magic_prompt`, `magic_prompt_option`, or similar), turn it **off**; the
   whole point is that the caption is used as written. If it exposes a dedicated `json_prompt`
   parameter, prefer that. Select the 4.0 model (`model_uri` with `V_4_0`) if the tool asks.
3. **Plain mode**: pass the prose prompt and leave magic prompt on (or `AUTO`).
4. Pass resolution or aspect ratio from section 5. Pick 2K only for finals.
5. After generating, look at the returned image (open the URL or file) before declaring success,
   then iterate per `SKILL.md` section 5.
6. Save keepers into a collection when the user is producing a set.

The Ideogram *docs* MCP (`https://developer.ideogram.ai/_mcp/server`) is a documentation server,
not a generation server; use it to look up API details.

## 2. REST API

Authentication: `Api-Key: <key>` header. Read the key from an environment variable (the repo's
convention is `IDEOGRAM_API_KEY`); never echo it into prompts, logs or files. Keys are created at
ideogram.ai/platform (API dashboard) and need credits. Default rate limit: 10 in-flight requests.

### Generate (synchronous)

`POST https://api.ideogram.ai/v1/ideogram-v4/generate` — **multipart/form-data**

| Field | Notes |
|---|---|
| `text_prompt` | Plain mode. Magic prompt is enabled automatically. Mutually exclusive with `json_prompt`. |
| `json_prompt` | JSON mode. The V4 caption object (sent as a JSON string form field). Magic prompt is disabled and the diffusion model consumes it directly. Mutually exclusive with `text_prompt`. The API requires `high_level_description` and `compositional_deconstruction`. |
| `resolution` | One of the enum values in section 5. |
| `rendering_speed` | `TURBO`, `DEFAULT` (default), `QUALITY`. `FLASH` is listed but returns 400 on V4 for now. |
| `enable_copyright_detection` | Optional boolean; opts into post-generation likeness and logo checks. |

Response: `{"created": ..., "data": [{"prompt": "...", "resolution": "WxH", "is_image_safe": true, "seed": 123, "url": "https://..."}]}`.
`prompt` is the caption actually used (after magic prompt in plain mode, so it shows you what the
expander did). Image URLs expire; download what you want to keep. Errors: 400 invalid input,
401 unauthorized, 422 prompt failed the safety check, 429 rate limit.

```bash
# JSON mode (script path relative to the skill folder)
curl -s -X POST https://api.ideogram.ai/v1/ideogram-v4/generate \
  -H "Api-Key: $IDEOGRAM_API_KEY" \
  -F "json_prompt=$(python3 scripts/validate_caption.py caption.json --fix --minify --quiet)" \
  -F "resolution=1248x832" \
  -F "rendering_speed=DEFAULT"

# Plain mode
curl -s -X POST https://api.ideogram.ai/v1/ideogram-v4/generate \
  -H "Api-Key: $IDEOGRAM_API_KEY" \
  -F "text_prompt=A watercolor painting of a fox curled up in snow under a pine tree, with soft blue shadows and falling snowflakes." \
  -F "resolution=1024x1024"
```

```python
import json, os, requests
caption = json.load(open("caption.json"))
r = requests.post(
    "https://api.ideogram.ai/v1/ideogram-v4/generate",
    headers={"Api-Key": os.environ["IDEOGRAM_API_KEY"]},
    data={
        "json_prompt": json.dumps(caption, separators=(",", ":"), ensure_ascii=False),
        "resolution": "1248x832",
        "rendering_speed": "DEFAULT",
    },
)
r.raise_for_status()
url = r.json()["data"][0]["url"]
```

Variants: `POST /v1/ideogram-v4/async/generate` returns a `generation_id` to poll at
`GET /v1/generations/{generation_id}` or deliver by `webhook_url`;
`POST /v1/ideogram-v4/generate-transparent` (and its `/async/` twin) returns images with an alpha
channel for logos, stickers and compositing; `POST /v1/ideogram-v4/remix` remixes an image.

### Magic prompt as a service

`POST https://api.ideogram.ai/v1/ideogram-v4/magic-prompt` — JSON body
`{"text_prompt": "...", "aspect_ratio": "AUTO"}`. Returns `{"json_prompt": {...}, "aspect_ratio": "16x9"}`.
`aspect_ratio` buckets: `AUTO`, `1x4`, `1x3`, `1x2`, `9x16`, `10x16`, `2x3`, `3x4`, `4x5`, `1x1`, `5x4`,
`4x3`, `3x2`, `16x10`, `16x9`, `2x1`, `3x1`, `4x1`. `AUTO` lets the model choose and tells you what it
chose. The returned caption can be passed straight back as `json_prompt`. Useful when you want to
see Ideogram's own expansion of a plain prompt and then edit it (the "plain first, JSON final"
workflow). The hosted magic prompt may return keys out of order; run the validator with `--fix`
before reusing its output.

### Describe

`POST https://api.ideogram.ai/v1/ideogram-v4/describe` — multipart with `image_file` (JPEG, PNG,
WebP, ≤25 MB) and optional `include_bbox` (default true). Returns a `json_prompt` that reproduces the
image's layout when bboxes are kept; set `include_bbox=false` to let the sampler compose freely.

## 3. Web app (ideogram.ai)

- Choose model **4.0** in the prompt box.
- JSON mode: paste the caption (pretty-printed is fine). Magic Prompt turns **off automatically**
  when the prompt is JSON for 4.0. Pick the aspect ratio in the settings row.
- Plain mode: type the prose prompt; Magic Prompt `Auto` or `On`.
- Describe on any image with 4.0 selected returns a JSON caption (the same as the API's describe).
- Color Palette, Negative Prompt, Style Reference, Seed and Render Speed are settings, not caption
  fields; availability varies by model and plan.

## 4. Open weights (`ideogram-oss/ideogram4`)

- Weights are gated on Hugging Face (`ideogram-ai/ideogram-4-nf4` for CUDA, `ideogram-ai/ideogram-4-fp8`
  for any device); accept the license and `hf auth login` first. 9.3B-parameter single-stream DiT
  with a Qwen3-VL-8B text encoder. Non-commercial license.
- The pipeline runs `CaptionVerifier` on every prompt and **raises** on issues by default
  (`--warn-on-caption-issues` downgrades to warnings). Text is capped at 2048 tokens.
- Plain text does not work and has a high false-positive safety rate; always send JSON, or let the
  built-in magic prompt do it (`--magic-prompt` is on by default and needs a key: `ideogram-4-v1`
  uses the free hosted API with `IDEOGRAM_API_KEY`; `claude-opus-v1` / `claude-sonnet-v1` use
  OpenRouter with `MAGIC_PROMPT_API_KEY`). The shipped configs strip bboxes from magic-prompt
  output by default (`strip_bboxes=True`).

```bash
# validate_caption.py path relative to the skill folder
python run_inference.py \
  --no-magic-prompt \
  --prompt "$(python3 scripts/validate_caption.py caption.json --fix --minify --quiet)" \
  --height 1024 --width 1536 \
  --sampler-preset V4_QUALITY_48 \
  --seed 0 --output out.png
```

- Any `height`/`width` that are multiples of 16 in 256–2048, aspect up to 6:1. For best quality
  `--height 2048 --width 2048 --sampler-preset V4_QUALITY_48`.
- Presets: `V4_QUALITY_48` (48 steps, default), `V4_DEFAULT_20`, `V4_TURBO_12`. Guidance 7 with a
  few gw=3 polish steps.
- Safety screening through Hive (`HIVE_TEXT_MODERATION_KEY`, `HIVE_VISUAL_MODERATION_KEY`) is
  strongly recommended by Ideogram; a blocked result is a gray image reading "Image blocked by
  safety filter".

## 5. Resolutions and aspect ratios

V4 API `resolution` enum, grouped (1K, then 2K):

| Ratio | Portrait | Landscape |
|---|---|---|
| 1:1 | `1024x1024`, `2048x2048` | same |
| 4:5 / 5:4 | `896x1120`, `1792x2240` | `1120x896`, `2240x1792` |
| 3:4 / 4:3 | `864x1152`, `1728x2304` | `1152x864`, `2304x1728` |
| 2:3 / 3:2 | `832x1248`, `1664x2496` | `1248x832`, `2496x1664` |
| 10:16 / 16:10 | `800x1280`, `1600x2560` | `1280x800`, `2560x1600` |
| 9:16 / 16:9 | `720x1280`, `1440x2560` | `1280x720`, `2560x1440` |
| 1:2 / 2:1 | `720x1440`, `1440x2880` | `1440x720`, `2880x1440` |
| 1:3 / 3:1 | `512x1536`, `1024x3072` | `1536x512`, `3072x1024` |
| 9:22 | `1296x3168` | `3168x1296` |
| 9:23 | `1152x2944` | `2944x1152` |
| 3:8 | `1248x3328` | `3328x1248` |
| 5:12 | `1280x3072` | `3072x1280` |

Common targets: Instagram feed 4:5 (`896x1120`), story or Reel 9:16 (`720x1280`), YouTube
thumbnail 16:9 (`1280x720`), poster 2:3 (`832x1248`) or 3:4, book cover 2:3, banner 3:1
(`1536x512`), phone wallpaper 9:16 or 1:2, square social 1:1.

Web-app presets: vertical `1:3 1:2 9:16 10:16 2:3 3:4 4:5`, square `1:1`, horizontal `5:4 4:3 3:2
16:10 16:9 2:1 3:1`. API forms use `x` (`16x9`), not `:`.

The caption's bboxes are normalized to the frame, so **decide the ratio before writing bboxes**, and
keep the same ratio when you regenerate a caption that has them.

## 6. Describe → style recipe → apply

The blog's workflow, step by step:

1. For each reference image call `describe_image` (MCP) or `POST /v1/ideogram-v4/describe`. You
   get a full V4 caption: medium, palette, lighting, composition, grain, mark-making, plus every
   element with bboxes.
2. Read the captions side by side and write down the **shared** visual logic in four headings:
   *Medium* (e.g. flat graphic illustration and bold display type; no 3D, no photography, no
   gradients), *Palette* (three to four spot colors, named and as hex), *Composition* (poster
   hierarchy: dominant headline top, central illustration, supporting detail below, plus what
   breaks the formality), *Texture* (risograph halftone, paper tooth, worn registration).
3. Turn it into a reusable recipe: a complete `style_description` block (correct key order,
   uppercase hex) plus two or three sentences on composition and texture that go into
   `background` and element descs. Remove everything subject-specific. Offer to save the recipe as
   a JSON block the user can paste into a future session.
4. Apply: write a fresh `high_level_description` and `compositional_deconstruction` for the new
   subject; drop the recipe's `style_description` in verbatim; carry over the composition and
   texture notes. Reuse a reference's bboxes only when the user wants that exact layout.
5. Generate, compare with the references, adjust one field at a time.

The same works without references: a prose style brief ("1970s Italian horror movie poster, warm
earth-tone palette, bold condensed display type, heavy grain") converts directly into the
`style_description` fields.

## 7. Safety and errors

- NSFW and other disallowed content is blocked; the API returns 422 ("Prompt failed the safety
  check") and the open model returns a gray blocked image. Rephrase rather than retry verbatim.
- On open weights, plain-text prompts trip the filter often; JSON avoids most false positives.
- `enable_copyright_detection` (API) adds likeness and logo checks after generation.
- Rate limiting: 429; back off and retry.
