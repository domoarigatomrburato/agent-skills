# Z-Image Turbo: official guidance

What Tongyi-MAI publishes about prompting and running Z-Image Turbo, collected from the model's own
repository, its Hugging Face Space and Draw Things' model entries. Paraphrased in English; the prompt
enhancer's original is Chinese.

## The prompt enhancer (`pe.py`, Tongyi-MAI/Z-Image-Turbo Space)

The Space can pass the user's prompt through an LLM before generation. Its system prompt casts the
LLM as a visual artist bound by logic: it must turn the user's prompt into a final visual description
that is faithful to the intent, full of detail, aesthetically strong and directly usable by a
text-to-image model, and it cannot tolerate vagueness or metaphor. The workflow, in order:

1. **Core elements.** Identify and lock what must not change: subject, quantity, action, state, and
   any named IP, colors and text. These are kept absolutely.
2. **Generative reasoning.** Decide whether the prompt needs reasoning: when it is not a direct scene
   description but asks for a solution (answering "what is", producing a design, showing how to solve
   a problem), first imagine a complete, concrete, drawable solution and describe that.
3. **Aesthetic and realistic detail.** Once the core picture is set, add professional detail: a clear
   composition, the light and atmosphere, material textures, a defined color scheme, and a space with
   depth and layers.
4. **Text.** The most important step: transcribe every piece of text that should appear, word for
   word, inside English double quotes as an explicit instruction. Posters, menus and UI get all their
   text described with fonts and layout; signs, road signs and screens get their content, position,
   size and material; text the enhancer invents while reasoning (charts, solution steps) follows the
   same rule. With no text in the picture, all effort goes into visual detail.

Final rule: the description must be objective and concrete, with no metaphors, no emotional rhetoric,
and never meta tags such as "8K" or "masterpiece", nor drawing instructions. The enhancer outputs only
the rewritten prompt.

## The encoder (`src/zimage/pipeline.py`, Draw Things)

- Each prompt becomes one user message of Qwen3's chat template with `add_generation_prompt=True` and
  `enable_thinking=True`, which for Qwen3 means no empty thinking block:
  `<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n`. No system prompt.
- The formatted text is tokenized with `max_length=512`, padding and truncation
  (`DEFAULT_MAX_SEQUENCE_LENGTH = 512` in `src/config/inference.py`). The template takes 8 tokens, so
  the prompt gets 504.
- Draw Things builds the same template for `zImage` (`LocalImageGenerator.swift`) with no maximum
  length, and uses Qwen3-VL 4B Instruct as the text encoder file. The tokenizer is Qwen3's
  (vocabulary identical to Qwen3-VL's).

## Settings

- Turbo (README): `num_inference_steps=9`, which "actually results in 8 DiT forwards", and
  `guidance_scale=0.0` ("Guidance should be 0 for the Turbo models"). `inference.py` defaults:
  1024x1024, 8 steps, guidance 0.
- Space (`app.py`): shift 3.0, 8 steps (it passes steps + 1 to the pipeline), guidance 0.
- Base model Z-Image (README): 512x512 to 2048x2048 in total pixel area at any aspect ratio,
  guidance 3.0 to 5.0, 28 to 50 steps, negative prompts "strongly recommended". These belong to the
  base model, not Turbo.
- Draw Things preset "Z Image Turbo 1.0" (`configs/z-image-turbo-1.0/metadata.json`): UniPC Trailing,
  8 steps, guidance 1, shift 3, resolution-dependent shift off, negative a single space, model file
  `z_image_turbo_1.0_q6p.ckpt`. The app's zoo also lists `z_image_turbo_1.0_q8p.ckpt` ("Z Image Turbo
  1.0") and an i8x variant. Model note: trailing samplers give the best results, 8 steps recommended.

## Resolution tiers (`app.py`, `RES_CHOICES`)

| Tier | 1:1 | 9:7 / 7:9 | 4:3 / 3:4 | 3:2 / 2:3 | 16:9 / 9:16 | 21:9 / 9:21 |
|---|---|---|---|---|---|---|
| 1024 | 1024x1024 | 1152x896 | 1152x864 | 1248x832 | 1280x720 | 1344x576 |
| 1280 | 1280x1280 | 1440x1120 | 1472x1104 | 1536x1024 | 1536x864 | 1680x720 |
| 1536 | 1536x1536 | 1728x1344 | 1728x1296 | 1872x1248 | 2048x1152 | 2016x864 |

## The shape of the official examples (`app.py`, README)

- A short Chinese scene sentence (a man and his poodle in matching outfits at a dog show, indoor
  lighting, audience behind).
- A Chinese low-key portrait: the subject, one hard light shaped by a mask across the face, then "high
  contrast, crisp light-shadow boundary, sense of mystery, Leica color tones".
- A Chinese phone selfie in an elevator: picture type first ("a medium-shot phone selfie photo"),
  then the person, clothes, pose, the phone and how it covers the face.
- The English Hanfu portrait: terse comma phrases for clothing, makeup, headdress, the prop, a lamp
  with a lightning-bolt shape, then the night background with a named landmark in Chinese.
- A long English description of a vertical Shanshui-style illustration with overlaid text, listing
  each text block with its color, typeface and size and quoting the words.
- A long Chinese film poster with a dozen quoted English text blocks, each with position and type,
  ending with the style, the lighting and the palette.
- The README's Chinese two-person photo: each woman's hair, clothes, accessories and pose in her own
  clause, the printed words on a sweatshirt in quotes, then a closing run of photo attributes (natural
  light, soft shadows, navy and cream palette, casual fashion photography, medium depth of field,
  faces in focus, relaxed pose, plain background).

## Sources

- https://github.com/Tongyi-MAI/Z-Image (`README.md`, `src/zimage/pipeline.py`, `src/config/inference.py`)
- https://huggingface.co/Tongyi-MAI/Z-Image-Turbo (model card, `tokenizer/`)
- https://huggingface.co/spaces/Tongyi-MAI/Z-Image-Turbo (`pe.py`, `app.py`), Apache-2.0
- https://github.com/drawthingsai/community-models (`configs/z-image-turbo-1.0/metadata.json`)
- https://github.com/drawthingsai/draw-things-community (`Libraries/ModelZoo/Sources/ModelZoo.swift`,
  `Libraries/LocalImageGenerator/Sources/LocalImageGenerator.swift`)
