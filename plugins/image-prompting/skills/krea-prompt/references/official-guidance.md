# Krea 2 official prompting guidance

Everything in this file comes from Krea's own material: the `krea-ai/krea-2` repository, the Krea
docs, and the Krea 2 technical report. Quotations are verbatim; the notes between them explain what
each source implies for writing a prompt.

## 1. The prompting guide (`docs/prompting.md`, verbatim)

> We recommend users to use natural language prompts to generate images.
> The turbo model can generate up to 2k resolution images. Long detailed prompts yield best results, but the model is capable of generating high quality images with minimal prompt engineering. For text rendering, we recommend putting quotes around the words to be rendered.
> If you wish to use LLM assistance for generating longer prompts, check out expansion.txt and use it as a system prompt for LLM of your choice.

That is the entire guidance text. The rest of the file is twenty example prompts, reproduced in
`examples.md`. What the examples add to the text:

- Both forms are official: comma-separated descriptor lists (8 of 20), full prose paragraphs (11 of 20) and one ten-word fragment.
- Most examples open with medium or shot type, then the subject: "close-up anime portrait of", "3D rendered matte black designer toy figure", "A minimalist flat-color illustration of", "high-fashion editorial portrait of", "stylized digital painting of", "An extreme low-angle close-up captures".
- Most examples close with an aesthetic label or a surface: "clean ligne claire drawing aesthetic with a subtle paper texture", "vintage 1980s airbrush aesthetic", "crisp cel-shaded aesthetic", "bold, high-contrast macro editorial style", "distinct film grain texture, vintage atmospheric aesthetic".
- Lengths run from 10 words to 180. Nothing is padded with quality words.
- Photographs carry camera language: "macro photograph", "extremely shallow depth of field", "macro lens", "film grain", "medium close-up shot", "soft directional studio lighting".
- Placement is grounded: "in the blurred right foreground", "in the lower left foreground near a pale grey shoreline", "in the upper center", "from the left and right edges of the horizon", "on the left ... On the right".

## 2. The prompt-expansion system prompt (`docs/expansion.txt`, verbatim)

This is what Krea suggests running through an LLM to turn a short prompt into a long one. It is also
the best description of what a good Krea 2 prompt looks like, because the hosted `creativity`
setting drives a trained version of the same idea.

> You are an expert prompt engineer for text-to-image models. Your task is to expand the user's prompt into a highly effective image-generation prompt.
>
> Think step by step about the request before writing the answer:
> - What is the subject and mood?
> - What visual styles, mediums, and lighting options would fit? Consider two or three alternatives and pick the one that best serves the caption.
> - What composition, framing, and grounded details will help the text-to-image model?
>
> Then output a single expanded prompt paragraph.
>
> Follow these rules strictly:
> 1. **Faithfulness First:** Preserve all original subjects, actions, colors, and spatial relationships. Do not add new objects, props, characters, or animals unless the user clearly implies them.
> 2. **Practical T2I Structure:** Write a prompt that a text-to-image model can parse cleanly. Group subjects with their own attributes and actions. Use grounded phrasing for poses, interactions, and spatial layout.
> 3. **Style Planning Stays Internal:** Use your internal reasoning to choose style, medium, framing, and lighting. Do not emit planning tags or wrappers in the visible answer body.
> 4. **Text Rendering:** If the user requests visible text, quotes, labels, or typography, specify the exact text clearly and wrap requested words in quotes.
> 5. **Avoid Over-Specification:** Do not invent highly specific clothing, colors, materials, or scene details unless the input supports them.
> 6. **Structure:** Write one cohesive paragraph after the thinking block. No bullets, JSON, or markdown.
> 7. **Respect Existing Detail:** If the user's prompt is already detailed, lightly polish and finalize rather than heavily expanding — preserve their phrasing and direction.
> 8. **Respect the Human Form:** Treat depictions of people with dignity. Assume clothing covers genitals and intimate anatomy.
> 9. **Preserve User Medium:** When the user explicitly requests a medium (e.g. "photo of", "photograph of", "illustration of", "painting of", "sketch of", "3D render of"), honor it. Do not pivot to a different medium to avoid difficulty — match the user's stated intent.

How to use it when you are the expander: follow the nine rules as written. Rule 1 and rule 5 pull in
opposite directions on purpose; fill obvious gaps (light, ground, time of day, a plausible
background), never new subjects. Rule 7 is why a user's detailed prompt gets a polish, not a rewrite.

## 3. The text encoder and its template (`encoder.py`)

The conditioner is `Qwen/Qwen3-VL-4B-Instruct`, read through hidden states of twelve layers rather
than the last one. Before encoding, every prompt is wrapped in a chat template whose system message is:

> Describe the image by detailing the color, shape, size, texture, quantity, text, spatial relationships of the objects and background:

The user turn is your prompt; the assistant turn is left empty. The model was trained with this
exact framing, which has three consequences:

1. The prompt is read as an image description that answers that instruction. Descriptions of a
   finished picture are in distribution; instructions to a tool ("generate", "make me") and
   meta-openers ("In this image") are not.
2. The eight nouns in the instruction are a checklist: color, shape, size, texture, quantity, text,
   spatial relationships, background. A prompt that answers them for its main objects is doing what
   the encoder expects.
3. The tokenizer is called with `max_length = 512 + 34 - 5` on prefix plus prompt; the 34-token
   template prefix is sliced off after encoding and the 5-token assistant suffix is appended after
   truncation, so the 512 conditioning tokens hold 507 tokens of prompt, roughly 370 to 400 English
   words under Qwen's tokenizer. Overflow is dropped without warning, so a prompt that is too long
   loses its tail.

## 4. From the technical report

On training data and captions:

> we use a cheaper LLM to reformat it into a variety of lengths and formats, exposing the model to a range of prompt styles.

> training on long prompts provides dense supervision, yielding faster convergence and lower training loss

Captions were built from OCR of any text in the image, a VLM description enriched with "world
knowledge alongside the extracted text" and "any available metadata (camera settings, known
entities, and so on)", then reformatted into short, medium and long variants. The pretraining mix
contained "no AI-generated images". Implications: named entities, camera settings and real-world
vocabulary are meaningful; visible text was captioned as text; long prompts are the native
register, short ones are supported.

On prompt expansion (what `creativity` does on the hosted model):

> the image model is best conditioned on detailed captions that lie close to its training distribution, while real user prompts are often short, conversational, and underspecified.

The expander "maps simple or underspecified user prompts into richer visual directions without
overwriting the user's intent", was trained on synthetic short "user captions" derived from long
captions, then tuned with RL on the images it produces, with an explicit penalty on "diversity
collapse". So `high` creativity is a legitimate exploration tool, not a quality knob, and `raw` is
the setting for a prompt you have already written in full.

On post-training targets: aesthetics, prompt adherence (rubric rewards that decompose a prompt into
verifiable requirements), text rendering (a dedicated reward model), and artifact avoidance. Prompt
adherence was optimized against checkable requirements, which is why concrete, checkable phrasing
(counts, colors, positions, quoted text) pays off.

## 5. From the Krea docs

Krea 2 Turbo prompting tips (user guide, verbatim table):

| Tip | Example |
|---|---|
| Keep the subject clear | "A streetwear poster for a neon running shoe" |
| Add style language early | "risograph print, limited palette, bold silhouette" |
| Use references for visual identity | Upload a poster, editorial image, or moodboard instead of trying to describe every visual detail |
| Generate in batches | Compare several outputs quickly, then refine the strongest direction |
| Escalate when needed | Move to Krea 2 Medium or Large when the draft needs more polish |

Also from the Turbo page: "Turbo works well with concise prompts, but benefits from clear style,
palette, and composition notes." And: "Use Turbo for prompt and style discovery. Once you find a
strong direction, regenerate with Krea 2 Medium for more stability or Krea 2 Large for richer
photorealism and texture."

Creativity modes (developer overview, verbatim):

- **raw — no expansion.** The model renders only what you've explicitly described. Best for tightly art-directed prompts where every detail is already specified.
- **low — close to the prompt.** Minimal expansion. The model stays close to the literal prompt but fills in obvious gaps.
- **medium — balanced (default).** Default behavior. The model adds reasonable interpretation without straying far from the prompt's intent.
- **high — expressive interpretation.** Strong expansion. The model takes meaningful creative liberty with style, mood, and aesthetics — best for short or open-ended prompts where you want the model to surprise you.

The Turbo API schema sets `creativity` default to `low`; the app's default is `medium`.

Generative sliders (verbatim table), hosted models only, each -100 to 100 with 0 neutral:

| Slider | Negative direction | Positive direction |
|---|---|---|
| Intensity | Bland, muted images | Intensely stylized images |
| Complexity | Minimal, clean compositions | Chaotic, dense compositions |
| Movement | Static images | Strong pose and camera movement |

Suggested combinations from the Krea 2 user guide: clean design, icons, editorial illustration:
Complexity about -60, Movement near 0. Cinematic, fashion, character work: Intensity about +60,
Movement about +30. Expressive worlds: Intensity and Complexity positive, add Movement.
"Generative Sliders are independent of Creativity."

When to use Turbo (verbatim): use when you need the fastest Krea 2 generations, are testing many
prompt directions, want expressive illustration or graphic design drafts, are iterating on style
references or moodboards, or want low-cost exploration. Avoid when you need the most detailed or
polished output, final photorealistic production, the raw texture of Krea 2 Large, or maximum
consistency across a final campaign set.

## 6. Safety (`docs/safety.md`, summary)

Krea fine-tuned the model against harmful outputs, runs input and output classifiers on its hosted
products, and requires open-weights deployers under the Community License to implement content
filtering or equivalent review. Reports go to safety@krea.ai. The expander's rule 8 (dignity,
clothing assumed) is the prompt-level counterpart; keep it.
