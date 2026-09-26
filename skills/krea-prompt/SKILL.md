---
name: krea-prompt
description: Write, lint and deliver text prompts for Krea 2 Turbo and the other Krea 2 models (Raw, Medium, Large) from Krea AI, then hand over the right settings for Draw Things, the Krea app, the Krea API or MCP server, ComfyUI or the open weights. Use this skill whenever the user mentions Krea, Krea 2, K2, Krea Turbo, a Krea style reference, moodboard or generative slider, or wants an image prompt for a Krea model they run locally, even if they never say the word "prompt". It covers prompt structure, text rendering with quotes, creativity and prompt expansion, aspect ratios and 1K/2K sizes, sampler settings, LoRAs and iteration.
---

# Krea 2 prompting

Krea 2 is Krea AI's 12-billion-parameter image model, trained from scratch on real photographs
and artwork with long, VLM-written captions. **Krea 2 Turbo** is its 8-step distilled checkpoint:
guidance-free, fast, and the version that ships in Draw Things, ComfyUI, fal and the Krea app.
Everything here is reconstructed from Krea's own sources (listed at the end). Companion files,
with paths relative to this skill's folder (the base directory shown when the skill loads):

- `scripts/lint_prompt.py` — lints a plain-text prompt (token count against the 507-token prompt budget, quotes for rendered text, negation, weighting syntax, tag-soup, instructions).
- `scripts/size.py` — width and height for an aspect ratio at 1K or 2K, in multiples of 16 or 64, with the tiled-decode threshold.
- `references/official-guidance.md` — Krea's prompting guide, its prompt-expansion system prompt, the text-encoder template, and the app's creativity modes, verbatim where it matters.
- `references/examples.md` — the twenty official example prompts, verbatim, tagged by form and medium.
- `references/delivery.md` — Draw Things, Krea app, API, MCP, ComfyUI, fal and reference-CLI settings, size tables, sliders, references, LoRAs.

## 0. Four facts that decide how you prompt

1. **The model reads your prompt as an image description.** Krea's text encoder is Qwen3-VL, and the
   reference code wraps every prompt in this instruction before encoding it: *"Describe the image by
   detailing the color, shape, size, texture, quantity, text, spatial relationships of the objects and
   background:"*. Your prompt is the answer to that request. Write it as a description of a finished
   picture that covers that list for the things that matter, not as an instruction to a tool.
2. **Long is fine, tag lists are fine, prose is fine.** Training captions were rewritten into short,
   medium and long variants in varied formats, and Krea's guide says *"Long detailed prompts yield best
   results, but the model is capable of generating high quality images with minimal prompt
   engineering."* The official examples run from 10 words to 180 and use both comma-separated
   descriptors and full paragraphs. The prompt gets 507 tokens (the template prefix sits outside the
   512-token window), about 370 to 400 words of English prose, and anything past it is cut off silently.
3. **Turbo has no negative prompt and no guidance.** It is distilled to run at 8 steps with guidance
   disabled, so there is no unconditional branch to push away from. Say what you want, never what you
   do not want. Prompt weighting syntax like `(word:1.3)` is plain text to the encoder.
4. **The hosted model expands your prompt; the open weights do not.** In the Krea app and API a
   `creativity` setting (`raw`, `low`, `medium`, `high`) controls an LLM that rewrites short prompts
   into caption-like ones. In Draw Things, ComfyUI or the reference CLI nothing rewrites your text
   unless you run Krea's `expansion.txt` through an LLM yourself. This skill *is* that expander:
   when you hand over a full description, tell the user to set creativity to `raw` so it is not
   rewritten twice.

## 1. Read the brief

Pull these out before writing (ask only when a missing item blocks you):

- **Subject and medium**: photograph, illustration, painting, 3D render, anime, collage, poster. If the user names a medium, keep it; Krea's own expander is told never to switch medium to dodge a hard request.
- **Text to render**: exact words and language. Render a name the way the user typed it; if the design wants capitals, put the capitals inside the quotes and say that you changed the casing.
- **References**: style images, a moodboard, a trained style or LoRA. These beat paragraphs of style description on the hosted model. Krea's style references extract the *look* of an image "with minimal content leakage", so a photo of an object the user likes does not put that object in the picture: describe the object in words, and attach the photo as a style reference at about 0.3 to 0.5 for its palette and surfaces. Image-to-image (`image_url` plus `strength`) exists only in the API.
- **Format**: aspect ratio, 1K or 2K, platform. When the user gives none: posters and covers 2:3 or 4:5, social 4:5 or 1:1, stories 9:16, cinematic frames 16:9 or 2.35:1, ambiguous 1:1.
- **Target**: Draw Things, Krea app, API or MCP, ComfyUI, fal, reference CLI. It changes the settings and whether expansion exists.
- **Intent**: precise art direction, or exploration ("some ideas", "surprise me").

## 2. Decide how much to write

| Situation | Write | Hosted creativity | Why |
|---|---|---|---|
| Art-directed brief, text to render, layout, palette, a look to match, any open-weights target | A full description (length guide at the end of section 3) | `raw` (or `low` if the brief has gaps you chose not to fill) | The model is best conditioned on captions near its training distribution, and the open weights have no expander. |
| Exploration, loose brief, no text to render | A short seed prompt, 5 to 30 words: subject, medium, one style cue | `high` (`medium` when the subject must not drift) | Krea's expander is trained with a diversity objective; it will vary directions you would not think of. |
| User already wrote a detailed prompt | Polish it lightly, keep their phrasing | `raw` | Expansion rule 7: detailed prompts get finalized, not rewritten. |

Default to the full description. For Draw Things and other open-weights targets there is no choice:
always write the full description, and offer three seeds instead of expansion when the user wants variety.

Edge cases, in order of precedence:

- **Quoted text anywhere means `raw`.** Krea's expander is told to keep quoted words, but only `raw` guarantees no rewrite, and typography is the thing a rewrite breaks.
- **Exploration plus text to render**: you supply the variety instead of the expander. Write three full prompts of 60 to 120 words each, different in composition and medium, each carrying the quoted text, at `raw`. "A few" means three.
- **A style reference, moodboard or trained style in play**: drop the style prose (the image carries the look) and keep subject, composition, light and one closing label. Krea's own reference examples go as far as "a cat jumping sideways"; yours can stay at 30 to 80 words. This shortening applies to each of the three prompts above when both cases meet.
- **A prompt written for another model** (booru tags, an Ideogram JSON caption, a Midjourney string with `--ar`): rewrite it into one paragraph, do not patch it.

## 3. Write the prompt

Before writing, skim `references/examples.md` for the official example closest to the brief's
medium and match its register and length. Open `references/official-guidance.md` when you need
Krea's exact wording, the expander prompt to reuse as a system prompt, or the creativity and slider
definitions; it adds sources, not rules. The rules, all drawn from Krea's guide, its expander prompt
and its encoder template:

1. **Open with medium, framing and subject in one breath.** The official examples start
   *"close-up anime portrait of a young woman"*, *"3D rendered matte black designer toy figure"*,
   *"A minimalist flat-color illustration of a person wading through..."*, *"high-fashion editorial
   portrait of..."*. Krea's Turbo docs say the same thing as a tip: *"Add style language early."*
2. **Describe, do not instruct.** No "generate", "create", "I want", "make it", and no "In this image
   we see". Start with the subject or the medium.
3. **Follow the encoder's checklist for every important object: color, shape, size, texture,
   quantity, text, spatial relationship, background.** Two of those per object is usually enough;
   the hero gets all of them.
4. **Group each subject with its own attributes and actions.** *"The dark-skinned figure, wearing an
   orange swim cap, light blue top, and bright green shorts, steps carefully through knee-deep
   water."* Do not scatter a subject's traits across the paragraph, and do not let two subjects
   share an adjective list.
5. **Anchor placement with grounded phrases.** "in the lower left foreground", "to the right", "high
   on the left", "behind the figure", "filling the upper third". The expander is told to use
   *"grounded phrasing for poses, interactions, and spatial layout"*; so should you.
6. **Name light and color concretely.** "soft directional studio lighting", "bright high-key lighting,
   luminous shadows with cool blue undertones", "golden hour sunlight hitting rocky orange terrain",
   "solid striking crimson red background". A palette in words beats "vibrant colors".
7. **Photographs get camera language.** Lens or shot type, depth of field, film or grain, and the
   light source. Official examples use "macro lens, shallow depth of field, distinct film grain
   texture" and "extremely shallow depth of field sharply focuses on the animal's face". Krea 2 was
   trained without synthetic images, so describe real photographs and it will make real-looking ones.
8. **Text goes in double quotes, exactly as it must render**, once, near the object that carries it:
   *a poster that reads "RIDE FREE" in heavy condensed sans-serif along the bottom edge*. Describe
   size, weight, placement and color outside the quotes. Keep each quoted string short; split copy
   into separate quoted strings with their own placement.
9. **Commit.** No "or", "maybe", "such as", "various", "some kind of". One value per attribute.
10. **Positive phrasing only.** "an empty road" not "a road with no cars". Negation words become
    content words on a guidance-free model.
11. **Do not over-specify past the brief.** Expansion rule 5: *"Do not invent highly specific
    clothing, colors, materials, or scene details unless the input supports them."* Fill obvious
    gaps (a floor, a light source, a time of day); do not invent props or extra characters.
12. **One paragraph, plain text.** No bullets, headings, JSON or markdown. Comma-separated
    descriptors are allowed as a form, but pick one form per prompt and keep it consistent.
13. **Close with the aesthetic label and surface**, the way the examples do: "clean ligne claire
    drawing aesthetic with a subtle paper texture", "vintage 1980s airbrush aesthetic with smooth
    gradients", "crisp cel-shaded aesthetic". This is where a named movement, print process or
    animation era goes.
14. **Named things stay named.** Captions were enriched with world knowledge, so real places,
    brands, art movements and periods carry meaning. Use them instead of paraphrases when the user
    names them.

Length: as long as the brief needs and no longer. A portrait with one subject is 60 to 120 words; a
dense scene with several subjects and text is 150 to 350. Past about 380 words, cut.

### Lint, then present

```bash
python3 scripts/lint_prompt.py prompt.txt
```

It counts tokens against the 507-token prompt budget: exactly when Qwen's tokenizer files are at
hand (`python3 scripts/lint_prompt.py --fetch-tokenizer` downloads the pair from Hugging Face once
into `~/.cache/krea-prompt/tokenizer`; `--tokenizer DIR` or `KREA_TOKENIZER_DIR` point at another
folder holding `vocab.json` and `merges.txt`), by a calibrated estimate otherwise. It also flags: instruction and meta phrasing, negation, hedges,
weighting syntax, negative-prompt markers, markdown or multiple paragraphs, quality tag-soup
("masterpiece, 8k, best quality"), text that looks meant to render but is not quoted, and a
prompt over 40 words with no medium or style word in its first 25. Without the script, walk that
list by hand.

Present the prompt in a plain fenced block, then the settings block from section 4. Never bury
the settings in prose; the user pastes them.

## 4. Settings that travel with the prompt

**Aspect ratio and size.** The hosted Krea 2 models are 1K only, in these eight ratios in the app (the API also accepts `3:4`):

| Ratio | Size | Ratio | Size |
|---|---|---|---|
| 1:1 | 1024 x 1024 | 4:5 | 928 x 1152 |
| 4:3 | 1184 x 896 | 2:3 | 832 x 1248 |
| 3:2 | 1248 x 832 | 9:16 | 768 x 1376 |
| 16:9 | 1376 x 768 | 2.35:1 | 1568 x 672 |

The open-weights Turbo generates from 1K to 2K: at most 2048 on a side, about 4 megapixels, any size
in multiples of 16 (the reference code pads up). "As large as possible" therefore means 2048 on the
long side. Run `python3 scripts/size.py 3:2 --2k` for the exact size,
the megapixels, and whether Draw Things needs tiled decode. Raw is trained to 1K.

**Open weights (Draw Things, ComfyUI, fal, reference CLI), Turbo:**

| Setting | Value | Source |
|---|---|---|
| Steps | 8 | Krea README, Diffusers docs |
| Guidance | off: `--cfg 0` in Krea's code, CFG 1.0 in ComfyUI and Draw Things | Krea README, Diffusers |
| Negative prompt | none | Diffusers Turbo pipeline takes none |
| Timestep shift | fixed `mu = 1.15`; as a multiplier that is `exp(1.15) = 3.16` | `sampling.py` |
| Sampler | plain Euler on the shifted schedule; in Draw Things a Trailing sampler (DDIM Trailing or DPM++ 2M Trailing), not an ancestral one | `sampling.py`; Draw Things notes for its other flow models |
| Size | 1K to 2K, multiples of 16 (Draw Things steps by 64) | Krea README |
| Draw Things 8-bit above ~2.9 MP | turn tiled decode on (640 tile, 128 overlap) | Draw Things community issue 105 |

**Open weights, Raw:** 52 steps, `--cfg 3.5` in Krea's convention, which is a standard CFG of 4.5
(Krea computes `cond + g * (cond - uncond)`), 1K, negative prompt allowed.

**Hosted Krea 2 (app, API, MCP):** `aspect_ratio`, `resolution: "1K"`, `creativity` (API default for
Turbo is `low`, the app's default is `medium`), `seed`, up to 4 style references in the app (10 in
the API, strength 0 to 1, default 0.5), one moodboard (strength default 0.23), trained styles with
strength -2 to 2, and the three generative sliders `intensity`, `complexity`, `movement` from -100 to
100. Sliders are LoRAs and do not touch the prompt; creativity is expansion and does not touch the
sliders. Leave them at 0 unless the brief calls for one of Krea's documented moves: clean design,
icons and editorial illustration take `complexity` about -60 with `movement` near 0; cinematic,
fashion and character work take `intensity` about +60 with `movement` about +30; expressive worlds
push `intensity` and `complexity` positive. Change one slider at a time.

## 5. Deliver

Read `references/delivery.md` the first time you deliver to a target in a session; it has the
request shapes, the size tables and the settings for Raw.

- **Draw Things**: paste the prompt, leave the negative prompt empty, Steps 8, Text Guidance 1.0, Shift 3.16 with any resolution-dependent shift option off (a value the app pre-fills when you pick the model wins over 3.16), DDIM Trailing or DPM++ 2M Trailing, size from `size.py`, tiled decode on above about 2.9 megapixels. No creativity, sliders or references exist there; style comes from the prompt or a LoRA trained on Raw.
- **Krea app** (krea.ai/image): pick Krea 2 Turbo, set creativity to match section 2, attach references or a moodboard, choose the ratio, batch of 4. Hand over settings in this shape:

  ```
  Model: Krea 2 Turbo   Aspect ratio: 2:3 (1K)   Creativity: Raw
  Style reference: <image>, strength 0.5   Moodboard: none   Krea style: none
  Sliders: Intensity 0, Complexity 0, Movement 0   Batch: 4   Seed: any
  ```

  For Draw Things the same block reads: Model, Size, Steps 8, Text Guidance 1.0, Shift 3.16, Sampler, Negative prompt empty, Tiled decode on/off, Seed.
- **Krea API**: `POST https://api.krea.ai/generate/image/krea/krea-2/medium-turbo` with a Bearer token from `KREA_API_TOKEN`, then poll `/jobs/{job_id}`. Medium and Large use `/krea-2/medium` and `/krea-2/large` with the same body. Never paste the token into a prompt or a log.
- **Krea MCP** (`https://api.krea.ai/mcp`, OAuth): read the tool schema first; pass the same fields. Generation spends the user's compute units, so generate when they asked for an image and hand back the prompt when they asked for a prompt.
- **ComfyUI**: the official Krea 2 template ships an LLM expansion toggle; turn it off when pasting a full description. 8 steps, cfg 1.0.
- **fal**: `fal-ai/krea-2/turbo` with `enable_prompt_expansion: false` for a full description.
- **Reference CLI**: `uv run inference.py "<prompt>" --checkpoint oss_turbo --steps 8 --cfg 0.0 --mu 1.15 --width W --height H`.

## 6. Look, then iterate

Turbo is cheap, so iterate in batches of four seeds and change one thing per round, with the
schedule (steps, shift, size) held fixed. A different schedule changes texture and composition on
its own, so a wording that lands at 8 steps and shift 3.16 may not at 9 steps and shift 3.84:
settle the words first, then explore settings.

- **Text wrong**: shorten the string, keep it quoted, describe the surface it sits on, reduce competing detail near it. Two short quoted strings beat one long one.
- **Style drifting or generic**: move the medium and style words to the front, name a process or era, or on the hosted model add a style reference instead of more adjectives.
- **Too literal or flat** (hosted): raise creativity one step, or push `intensity` positive. **Too busy**: `complexity` negative. **Stiff pose**: `movement` positive.
- **Subject in the wrong place**: replace vague placement with a grounded phrase and name what it is next to. Something that must cross the whole frame is placed through the frame edges ("parallel to the bottom edge, both rims running out of the frame on the left and right"); "in the middle distance" makes the same thing recede and close inside the picture. "Its top edge out of frame" puts that edge exactly on the frame line, which reads as a crop; "running out of the frame through the top-left and top-right corners" keeps it open.
- **Pose or gaze wrong**: describe the body, not the intent, with degree words. "Looking up" sends the head to the zenith; "head tilted slightly back, looking up at a shallow angle, hat sitting level" lands the gaze. Eye contact needs "facing the camera, staring straight into the lens".
- **An unusual object reverts to its usual form** (an inverted pyramid comes out Giza on some seeds): the noun carries its normal look, so spend the words on what differs from it, from more than one angle ("upside-down, point aimed at the ground, faces widening upward"), instead of repeating the noun.
- **Distance or haze not landing**: say what the haze does to color and surface ("half-dissolved in the haze", "blank and smooth, barely darker than the sky, the same blue-grey as the farthest hills"). "Reduced by haze to a silhouette" gives a sharp dark shape.
- **A figure loses an attribute on some seeds**: "a second identical man" does not carry the first man's hat. Each figure gets its own hat, clothes and prop in its own sentence.
- **Something appears that was never asked for**: look for a simile or a second mention. "As wide as a river" puts a river in the chasm, and a case described twice becomes two cases. Compare with a plain measure ("as wide as a highway") and mention each object once, with its count ("a single black case").
- **Looks like AI art**: describe a real photograph (lens, film, light source, imperfections) and drop quality words; the model was trained on real images and answers to their vocabulary.
- **Same picture every seed**: that is the distilled model being consistent; change the composition or the style label, or add a reference, rather than rewording details.
- **Truncated ending ignored**: you passed the token window; cut the middle, not the style tail.

## 7. Traps

- A negative prompt field on Turbo does nothing; on Raw it works only with CFG on.
- `(word:1.3)`, `[word]`, `word++` and `--no` are text, not controls.
- "masterpiece, best quality, 8k, ultra detailed, trending on artstation" describe nothing; Krea's captions never contained them.
- Instructions and meta phrases ("Create an image of", "In this image") are not how captions begin.
- Expecting 2K from the hosted model: it is 1K only. Expecting sliders or creativity in Draw Things: they are hosted-only LoRAs and an LLM.
- CFG above 1 on Turbo fights the distillation; steps far above 8 add nothing.
- Style words at the end of a long prompt lose to the subject description; put them early and repeat the label at the end.
- Silent truncation at 507 prompt tokens: the lint reports the count.

## 8. Two compact examples

**Photograph, art-directed (creativity `raw`, 3:2):**

```
A medium-format color photograph of a woman in a yellow oilskin raincoat waiting alone at a rural bus shelter on a grey coastal road, seen in profile from across the wet asphalt. The shelter is a small concrete box with a corrugated roof, a timetable behind scratched plexiglass on its back wall, a puddle mirroring it in the foreground. Low overcast sky, flat diffuse daylight, drizzle streaking the air, gorse and stone walls receding to the right toward a headland. Kodak Portra 400, 80mm lens, mid distance, deep depth of field, muted greens and greys against the single yellow, quiet documentary aesthetic.
```

**Poster with text, illustration (creativity `raw`, 2:3):**

```
Risograph-style concert poster for a jazz quartet, two-color print in deep navy and warm orange on cream paper. A saxophone player in silhouette fills the lower two thirds, bell raised to the upper right, rendered in flat navy with visible ink grain and slight misregistration. The title "BLUE NOTE SESSIONS" runs across the top in heavy condensed sans-serif capitals, orange, edge to edge. Beneath the figure a single line reads "FRIDAY 21 MARCH, 9 PM" in small navy capitals, letterspaced. Solid cream background, coarse paper texture, mid-century print aesthetic.
```

## Sources

- krea-ai/krea-2 repository: `docs/prompting.md` (guidelines and examples), `docs/expansion.txt` (expander system prompt), `README.md` (settings), `encoder.py` (Qwen3-VL template, 512-token window), `sampling.py` (Euler sampler, `mu` schedule), `docs/safety.md`.
- Krea docs: Krea 2 Turbo and Krea 2 user guides (ratios, tips, creativity, sliders), Krea 2 API overview, Krea 2 Turbo API reference (OpenAPI schema), generative sliders, style transfer, moodboards, MCP server.
- Krea 2 technical report (captioning pipeline, prompt expansion, text encoder, training data).
- Hugging Face Diffusers Krea 2 pipeline docs (guidance convention, Turbo pipeline, `max_sequence_length`).
- ComfyUI official Krea 2 tutorial (template, expansion toggle, model files); Draw Things community issues 95 and 105; fal Krea 2 Turbo API page.
