# Draw Things API server: what is verified

Verified 2026-09-26 against Draw Things 26.0910.1 on an Apple M3 with a Draw Things+
subscription, API Server on (gRPC, 7859, TLS, response compression, model browsing, Bridge
Mode), Cloud Compute selected in the project.

## Protocol

- Service `ImageGenerationService` (proto in `Libraries/GRPC/Models/Sources/imageService/imageService.proto` of `drawthingsai/draw-things-community`): `GenerateImage` (server stream), `Echo` (returns the local model list as JSON in `override.models`), `FilesExist`, `UploadFile`.
- TLS uses the Draw Things root CA that `drawthings-py` bundles (`resources/root_ca.crt`); the certificate's name is `localhost`, hostname checking is off in the SDK.
- The request carries `prompt`, `negativePrompt`, `configuration` (a FlatBuffer `GenerationConfiguration`, schema `Libraries/DataModels/Sources/config.fbs`), an optional target-sized fp16 `image` tensor for image-to-image, `override.models` (JSON list of model specs), `user`, `device`, `chunked`.
- Response stream: a `currentSignpost` per stage (`textEncoded`, `imageEncoded`, `sampling.step`, `imageDecoded`), preview images, then `generatedImages`; with Response Compression on, images are fpzip tensors that the SDK decodes. With `chunked` false the final PNG is the last generated image.
- A model the app does not have (cloud-only) needs its spec in `override.models`; the SDK never fills that field, so `dt_render.py` patches its request builder to add it. The patch is guarded: if the SDK changes the builder, the script exits with a message.

## Model spec fields that matter

```json
{"name": "Krea 2 Turbo (8-bit S)", "file": "krea_2_turbo_i8x.ckpt", "version": "krea_2", "prefix": "",
 "text_encoder": "qwen_3_vl_4b_q8p.ckpt", "autoencoder": "qwen_image_vae_f16.ckpt",
 "clip_encoder": "krea_2_turbo_i8x.ckpt", "modifier": "none", "default_scale": 32, "upcast_attention": false}
```

- `version` is the app's `ModelVersion` raw value (`Libraries/SwiftDiffusion/Sources/Samplers/Sampler.swift`): `krea_2`, `ideogram_4`, `z_image`, `qwen_image`, `flux2`, ...
- `text_encoder` and `autoencoder` are file names from the app's `ModelZoo.swift` hash table (`Libraries/ModelZoo/Sources/ModelZoo.swift`); cloud-only files sit there without a built-in specification, next to their text encoder. The autoencoder follows the latent layout: 16-channel models use `qwen_image_vae_f16.ckpt` or `flux_1_vae_f16.ckpt`, 32-channel (128 after 2x2 patching, the `latentsMean`/`latentsStd` arrays with 128 entries) use `flux_2_vae_f16.ckpt`.
- `default_scale` 16 in a spec for a cloud-only model (Krea 2, Ideogram 4) caps generation at 1024 px on a side through the API; 32 allows 2048. Every size above 1024 failed at sampling step 0 with 16 and rendered with 32. For a model the zoo already has, keep the zoo's value: Qwen Image 2512's entry says 16, and with 16 it rendered 1920x1280 (as it did with 32).
- `clip_encoder` set to the model file mirrors the app's own community entries for these architectures.

## How the prompt is tokenized (LocalImageGenerator.swift)

Both cloud recipes encode with a Qwen3 tokenizer and a chat template the server adds itself:

- Krea 2: `<|im_start|>system\nDescribe the image by detailing the color, shape, size, texture, quantity, text, spatial relationships of the objects and background:<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n` (the same template as Krea's reference encoder, so the krea-prompt linter's budget applies as is).
- Ideogram 4: `<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n`, about ten tokens of overhead; no system prompt, no JSON rewriting. The app's own "Expand Prompt to JSON" feature is a client-side LLM (a local Qwen 3.5 checkpoint) and never runs on API jobs, so a JSON caption reaches the model exactly as sent.

Truncation and padding follow the spec's `padded_text_encoding_length`; for `krea_2` and `ideogram_4` the fallback is 0, meaning no truncation and no padding. A Krea prompt of 341 tokens with a "black and white" instruction in its last sentence rendered monochrome through the API, so the whole window is encoded (the 256 in `ComputeUnits.swift` is only the cost estimate's default).

## Configuration fields used

`model`, `startWidth`/`startHeight` (pixels / 64), `seed`, `steps`, `guidanceScale`,
`strength` 1.0, `sampler`, `shift`, `resolutionDependentShift` false, `batchCount` 1,
`batchSize` 1, `seedMode` ScaleAlike, `tiledDecoding` (tile 640, overlap 128 when on).
Sampler enum order: DPMPP2MKarras, EulerA, DDIM, PLMS, DPMPPSDEKarras, UniPC, LCM,
EulerASubstep, DPMPPSDESubstep, TCD, EulerATrailing, DPMPPSDETrailing, DPMPP2MAYS, EulerAAYS,
DPMPPSDEAYS, DPMPP2MTrailing, DDIMTrailing, UniPCTrailing, UniPCAYS, TCDTrailing. Flow models
(Krea 2, Ideogram 4, Z Image, Qwen Image, FLUX) take the Trailing or AYS samplers only.

## Configuration JSON formats

Draw Things has three related JSON shapes:

- **Copy/Paste Configuration** uses the scripting `JSGenerationConfiguration` schema:
  camelCase keys, with enum values such as `sampler` and `seedMode` stored as integers. It has
  settings only, no prompt.
- App presets wrap that object as `{name, version, negative, configuration}`. Official presets
  are published at `https://models.drawthings.ai/configs.json`; custom app presets use the same
  wrapper, although the app may leave their negative prompt empty.
- PNG metadata contains the prompt as `c`, negative as `uc`, compact display fields at the top
  level, and the full scripting configuration as `v2`.

The skill's reusable recipe is the app preset shape plus `prompt`:

```json
{"name":"name","prompt":"text","negative":"text","configuration":{}}
```

The inner `configuration` object can still be copied back to the app unchanged. `dt_render.py
--config` accepts all three useful inputs: a bare configuration object, an app preset, or the
reusable recipe. The configuration's model file selects the full spec in `recipes.json`;
command-line options take precedence. `png_config.py --config-out` converts a PNG's `v2`, `c`
and `uc` fields to the reusable form, and every successful API render writes the same form next
to its PNG.

drawthings-py 0.4's `config_dict_from_json` has a truthiness bug: its `if value := ...` drops
every `false`, numeric `0`, empty list and empty string. In particular,
`resolutionDependentShift: false` disappears and the SDK falls back to `true`, recomputing the
shift. The renderer therefore walks the SDK property table itself, retains every value that is
not `None`, and supplies camelCase aliases for scripting fields missing from that table.

## Ideogram 4 guidance path (UNetFixedEncoder.swift)

With CFG on, the encoder builds the transformer's text as `negative tokens + caption tokens` in
one sequence unless `zeroNegativePrompt` is set *and* the checkpoint carries the separate
unconditional transformer (`__unconditional_dit__` tensors), in which case the caption alone goes
to the conditional model and the unconditional model takes no text, as in the open weights.
What the cloud does with a long caption depends on the model file, not on the flags. With
`ideogram_4_i8x.ckpt`, observed at 1024x704 with the 1,309-token Observer caption: CFG 1
clean, CFG 3 posterized, CFG 7 noise at 8 and at 20 steps; a 145-token caption and a 513-token
plain prompt were fine at CFG 7; 781 tokens were blown out. `zeroNegativePrompt`,
`padded_text_encoding_length` 1024 or 2048, removing hex palettes and line breaks, or adding an
`aspect_ratio` key changed nothing, and identical (prompt, seed, settings) came back
byte-identical across those variants. With `ideogram_4_q8p.ckpt`, the file the app's "Ideogram 4
remote" uses (read from the metadata of a PNG the app exported), the same caption renders
cleanly at CFG 7 with zero negative prompt on or off, and the app's exact settings (32 steps,
shift 2.99, DPM++ 2M Trailing, zero negative on, 1920x1280, its seed) reproduced the app's image
pixel for pixel through the API. So the i8x file is the one whose guided branch collapses on
long text; whether it lacks the unconditional transformer or is an older conversion is not
known. The proxy uses the request's override spec for the compute-unit estimate and forwards
the request unchanged; the estimate matched the app's own number for that setting (39,477
against about 39,000 shown in the app).

## Qwen Image 2512 through the API

The app has this model in its zoo, so a spec is only needed because Bridge Mode forwards the
request with the override. A bare spec (name, file, version, encoders, default scale) failed
four times in a row mid-sampling with `No images received from server`; the full zoo entry
(`objective` `{"u": {"condition_scale": 1000}}`, `hires_fix_scale` 24, and the `mmdit` block
with `qk_norm` and activation scaling 2 on all 60 layers for QK, projection, FFN up-projection
and FFN) rendered at 1024x704, 1536x1024 and 1920x1280. With the app's exact settings (36 steps,
CFG 4, shift 3.99, DPM++ 2M Trailing, no negative, 1920x1280, its seed) the API render matched
the app's image down to fine detail (same composition, figures and textures; small changes in
the lettering colours of a sign) but not pixel for pixel: about 5 % of the pixels are identical.
The prompt was byte-identical and the configuration stored in both PNGs differs only in fields
Qwen text-to-image does not use, so the cause is on the server side (the cloud's own model entry
or run-to-run variation between machines) and not known. The model card's 50 Euler steps (DDIM
Trailing) and 34 steps of DPM++ 2M Trailing gave practically the same image at 1536x1024 (mean
difference 2.8 on a 0 to 255 scale at 64 px), which is why the recipe uses 34.

## Z Image Turbo through the API

The app has Z Image Turbo 1.0 in its zoo (`z_image_turbo_1.0_q8p.ckpt`, version `z_image`), so the
recipe's spec is that entry: Qwen3-VL 4B Instruct q8p as text encoder, `flux_1_vae_f16.ckpt`,
`objective` `{"u": {"condition_scale": 1000}}`, `hires_fix_scale` 24, default scale 16. It rendered
through Bridge Mode on the first attempt at 1024x1536 (2026-09-29, four jobs of 20 to 33 s). The text
template is `<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n` with no length cap
(`LocalImageGenerator.swift`); the reference pipeline caps template plus prompt at 512 tokens.
`compute_units.py` ports `ZImageInstructionCount.swift`: about 2,000 units at 1536x1024 and 8 steps,
not yet compared with the number the app shows.

## SeedVR2 7B image input and fill frame

An app-exported 3840x2560 PNG made from a 1920x1280 input identifies the model as
`seedvr2_7b_q8p.ckpt` and carries these effective settings: one step, guidance 1, shift 1.03,
DPM++ 2M Trailing, strength 1, Scale Alike, both tiled decoding and tiled diffusion enabled,
1024x1024 tiles with 128px overlap, and empty positive and negative prompts. The model-zoo
spec uses version `seedvr2_7b`, itself as text encoder, `seedvr2_vae_f16.ckpt`, modifier
`inpainting`, default scale 24, hires-fix scale 512, u-objective condition scale 1000 and latent
scaling factor 0.9152.

The renderer exposes image-to-image `strength` with `--strength`. On Draw Things+ Bridge
Mode, the Avedon portrait was rendered successfully with the same SeedVR2 recipe at 0.8;
compared at native size with the strength-1.0 upscale, this reduced fine etched texture
but softened eyes and denim too. The setting is a broad image-to-image control, not a
SeedVR2 microtexture slider. Keep separate output directories for comparisons.

`RequestBuilder.init_image()` puts an image tensor in the gRPC request, but drawthings-py 0.4
always calls `ImageBuffer.resized(width, height, 3)`, which stretches a mismatched aspect ratio.
Its unused `center_cropped()` helper also computes the crop against target dimensions instead
of source dimensions. `dt_render.py` therefore prepares the canvas itself: EXIF transpose,
RGB conversion, proportional bilinear cover resize, centered crop to the exact output size.
Because the resulting `ImageBuffer` already has the target dimensions, the SDK performs no
further resize. This is the terminal equivalent of the app's Paste → Fill Frame workflow.

## Timings seen

| Model | Size | Steps | Total | First step |
|---|---|---|---|---|
| Krea 2 Turbo | 1024x704 | 8 | 60 to 90 s | 15 to 50 s |
| Krea 2 Turbo | 2048x1344 | 8 | 94 s | 30 s |
| Ideogram 4 | 1024x704 | 8 | 103 to 124 s | 48 to 58 s |
| Ideogram 4 | 2048x1344 | 8 | 144 s | 67 s |
| Ideogram 4, CFG 1 | 1024x704 | 8 | 91 s | 51 s |
| Ideogram 4 (q8p), CFG 7 | 1920x1280 | 32 | 198 s | 40 s |
| Ideogram 4 (q8p), CFG 7 | 1024x704 | 20 | 52 s | 23 s |
| the app itself, same job as the 198 s row | 1920x1280 | 32 | 185 s | 21 s (text encoding 12 s) |
| Qwen Image 2512, CFG 4 | 1024x704 | 8 | 76 s | 53 s |
| Qwen Image 2512, CFG 4, DDIM Trailing | 1536x1024 | 50 | 183 s | 71 s |
| Qwen Image 2512, CFG 4, DPM++ 2M Trailing | 1536x1024 | 34 | 148 s | 23 s |
| Qwen Image 2512, CFG 4, DPM++ 2M Trailing | 1920x1280 | 36 | 239 s | 28 s |
| the app itself, same job as the 239 s row | 1920x1280 | 36 | 230 s | 30 s (text encoding 23 s) |
| SeedVR2 7B, 1920x1280 init image | 3840x2560 | 1 | 108 s | 67 s |
| Z Image Turbo, UniPC Trailing | 1024x1536 | 8 | 20 to 33 s | 6 to 14 s |

No throttling across some twenty jobs in one morning. Random aborts before the first step do
happen and are the reason for the retries. Mid-sampling drops (`No images received from server`) also happen; four in a row on one model turned out to be an incomplete spec (see SKILL.md, section 5), not the cloud.

## Deriving a spec for a new cloud model

First check that the cloud serves the model at all. The served list is the file
`models.txt` in the `drawthingsai/community-models` repository on GitHub (the wiki's Cloud
Compute page links it as "current community models"; `loras.txt` beside it lists the cloud
LoRAs). The entries are model ids, not checkpoint file names (`flux-2-dev`, `qwen-image-2.1`,
`ideogram-4`, `ideogram-4-fast`, `ideogram-4-instant`, `krea-2-raw`, `hidream-i1-full`,
`ltx-2.3-22b-dev`, `wan-v2.2-a14b-...`, plus dozens of SDXL and SD 1.5 community checkpoints on
2026-09-26); the file name the request must carry still comes from a PNG the app exported or
from the model zoo. A model missing from that list fails through Bridge Mode whatever the spec
says. The wiki states the per-job ceilings: 40,000 compute units on Draw Things+, 15,000 on
the free Community tier, and local LoRAs (BYOL) only on Draw Things+.

Shortest route: export any PNG the app made with that model and run `scripts/png_config.py`
on it. The metadata names the model file exactly as the cloud expects it (the app's "Ideogram 4
remote" is `ideogram_4_q8p.ckpt`, not the `i8x` file the download list shows) and the settings
block gives the app's defaults. The text encoder and autoencoder still come from the model zoo.
In the app's model list, a cloud icon with a slash through it marks a variant the cloud will not
run; export the PNG from a variant with a plain cloud icon.

1. Find the file in the `ModelZoo.swift` hash table (`*_i8x.ckpt`, `*_q8p.ckpt`); the text encoder is usually the entry right after it.
2. Take the `version` raw value from `Sampler.swift`'s `ModelVersion` enum.
3. Pick the autoencoder by the model's latent channel count (`latentsMean` arrays in `ModelZoo.swift`, or the open-weights repository's VAE `z_channels`).
4. Set `default_scale` 32, `modifier` "none", `prefix` "", `clip_encoder` to the file, unless the zoo entry says otherwise. Carry over every other field the zoo entry has (`objective`, `noise_discretization`, `hires_fix_scale`, the `mmdit` block with its activation scaling, `is_bf16`): the spec replaces the app's built-in entry, and a missing field breaks the job mid-sampling. The model's `metadata.json` in `drawthingsai/community-models` is the zoo entry in JSON with snake_case keys; `configs/<model>/metadata.json` beside it holds Draw Things' recommended settings for it.
5. Test with a short plain prompt at 1024x704 and 8 steps; a coherent image proves the encoder and autoencoder pair, then test the real prompt format and the target size. Repeat any failure before changing the spec.

## drawthings-py notes

- Version 0.4.x, Python 3.11+, depends on a betterproto pre-release (the setup script lists it explicitly so pip and uv accept it). GPL-3.0: a dependency of this skill, never copied into it.
- `RequestBuilder(config, prompt, negative)`; `Configs.create(width=..., height=..., steps=..., guidance=..., shift=..., sampler="DDIMTrailing", seed=..., seed_mode="ScaleAlike", strength=1.0, resolution_dependent_shift=False, tiled_decoding=False, model="file.ckpt")`; `DrawThings.grpc(host, port, progressbar=False, disable_messages=True)`; `await service.generate(rb)` returns image buffers with `to_file()`, which writes Draw Things metadata into the PNG.
- `RequestBuilder.init_image(path_or_buffer)` supplies the image-to-image tensor. Pre-size it to the output dimensions before attaching it when the placement policy matters; the SDK's request builder otherwise resizes directly to `(width, height)` with bilinear interpolation.
- `raise_grpc_error` maps INTERNAL to `DrawThingsServerError` and UNAVAILABLE to `DrawThingsUnavailableError`; the message text carries the gRPC status and details.
- The SDK's `strength` defaults to 0 when unset; the script sets 1.0 explicitly.
