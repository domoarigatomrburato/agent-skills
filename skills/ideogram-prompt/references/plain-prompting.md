# Plain-text prompting (magic prompt ON)

Source: Ideogram's official prompting guide at docs.ideogram.ai (sections "Quick Summary",
"Prompting Fundamentals", "Prompt Structure", "Text and Typography", "Handling Negatives",
"Common Pitfalls and Fixes", "Prompt Iteration and Refinement", "Troubleshooting") and the
generation-settings pages for Magic Prompt, Color Palette and Negative Prompt.

In plain mode for Ideogram 4.0 your text is rewritten server-side into a JSON caption by magic
prompt (on ideogram.ai it is on by default; on the API `text_prompt` enables it automatically).
The model then makes its own decisions about color, lighting, composition and medium. That is the
point of the mode: use it for exploration, loose briefs and "interpret my intent" requests; switch
to JSON when text, palette, placement or repeatability matter.

## What plain text can and cannot do

- Natural sentences, not tags. "A man in the forest, fire, dramatic, painting" works less well
  than a sentence with grammar and relationships.
- No weights (`::1`, `(important)`), no flags (`--ar`, `--style`), no hex codes or RGB values.
  Describe colors in words ("deep red", "pale blue"). Hex control exists only in JSON captions
  or the Color Palette setting.
- Earlier words carry more weight. Lead with the subject and any text.
- Length: about **150–160 words (roughly 200 tokens)** is the practical ceiling; past that,
  content may be ignored or misread.
- Any language works, but English gives the most reliable results, especially for rendered text;
  magic prompt translates to English anyway. Non-Latin scripts render best-effort.

## The structure

*[Image summary]. [Main subject details], [Pose or action], [Secondary elements], [Setting and
background], [Lighting and atmosphere], [Framing and composition], [Technical enhancers]*

1. **Image summary**: one sentence for the whole image as glanced at for two seconds. Visual form
   (photo, logo, painting), main subject, tone. If you could write only one sentence, this is it.
   Magic prompt expands this part best.
2. **Main subject details**: color, shape, material, texture. Also the place for any text to
   render, in double quotes, early.
3. **Pose or action**: what the subject is doing or how it is placed.
4. **Secondary elements**: props and ambient details that complete the scene without stealing focus.
5. **Setting and background**: indoors or outdoors, time of day, environment.
6. **Lighting and atmosphere**: how the light looks and how the image feels.
7. **Framing and composition**: camera angle, shot type, subject placement; applies to logos and
   paintings too.
8. **Technical enhancers**: lens, bokeh, brush texture, rendering style; polish, not content.

Use only the parts you need. A logo brief rarely needs secondary elements.

Official assembled example (near the length ceiling):

> A product photo of a men's perfume bottle named "Nightlife for men" in a sleek studio setup. The
> bottle is tall and rectangular with dark glass, a matte black cap, and silver lettering. The text
> "Nightlife for men" appears on the label in bold, modern font. The bottle stands upright with a
> slight reflection on the surface below. A wristwatch and a pair of sunglasses sit nearby, adding a
> masculine vibe. The scene is set on a smooth black surface with blurred city lights in the
> background. Lighting is moody and cool, with soft blue highlights and deep shadows. The bottle is
> centered in the frame, captured at eye level. A shallow depth of field gives the image a polished,
> professional look.

Official logo template:

> A {minimalist / modern / vintage / sleek / elegant / professional / playful / whimsical / dynamic}
> logo design for the brand "{Brand Name}", featuring a {stylized / abstract / illustrated /
> geometric / hand-drawn / delicate} {subjects}. {describe the subjects in more detail.} The text
> "{Brand Name}" is written in a {clean / bold / elegant / playful} {serif / sans-serif / cursive /
> handwritten / geometric / pixelated} font, [with {color} outline,] [rendered in {lowercase /
> uppercase / small caps}, and] positioned {below / beside / integrated with} the logo[, with
> {tagline} in smaller text]. The background is {solid color / soft gradient / white / textured},
> giving the logo a {clean / warm / bold / elegant / modern / handcrafted} look. {Describe the vibe.}

## Photoreal briefs

Magic prompt will add its own styling, but the wording you give it still steers the grade. For
photo briefs with no style direction, keep the neutral defaults from `caption-writing.md` section
8: natural or overcast daylight, neutral white balance, off-center framing, no motion blur, one
saturation word at most, and no "warm" as a grading adjective (name the warm light *source*
instead). The official plain-mode example is the wolf prompt in `examples.md` section 5.

## Text in plain mode

- Put the exact wording in **double quotes** and describe its context: `a poster on a wall with
  text that reads: "Everything you can imagine is real."`
- Mention it **early**.
- Short phrases render best; the longer the string, the likelier a typo, a dropped or doubled
  letter. Break multi-line copy into chunks with placement cues ("along the bottom", "beneath the
  icon").
- Relative size words work: "the huge title …", "a smaller mention 'magazine' under it", "the big
  headline …", "a second smaller headline …".
- Typefaces cannot be named, but stylistic properties can: bold sans-serif, ultra thin sans-serif,
  serif, thin rounded Bauhaus style, refined formal script with flourishes, 1960s hippie style.
- Reduce visual complexity around the text.
- Not for full documents; long copy is added afterwards in an editor.
- If a word comes out wrong: regenerate a few times, swap long words for shorter synonyms, or fix
  in the editor and remix at high image strength. It is usually easier to remix the picture around
  correct text than to fix text while keeping the picture.
- Pixel-precise placement is a JSON feature (bboxes); move to JSON mode when it matters.

## Negatives

Negation is read as a keyword. "A man without a beard" tends to produce a beard. Describe the
positive opposite: "an empty room with chairs neatly arranged", "a bald figure with smooth skin",
"an empty beach at sunrise", "a robot with a smooth, featureless face", "a quiet pedestrian-only
street". Ask: "if this thing were not there, what would I see instead?"

The Negative Prompt setting (web app; not part of the V4 JSON contract) takes comma-separated
terms ("green, green candies") and works as a soft nudge; the main prompt always wins over it. A
guitar prompt implies strings, so "guitar" plus negative "strings" rarely works.

## Common pitfalls and fixes

- **Vague adjectives** ("beautiful", "nice", "cool") → concrete visual details ("a dense forest with
  tall pine trees and soft rays of sunlight filtering through the branches").
- **Generic style terms** ("artistic", "modern") → named movement, technique or medium
  ("impressionist painting with thick brushstrokes and pastel tones").
- **Contradictions** ("minimalist sculpture with intricate details") → pick one coherent direction.
- **Abstract concepts** ("a symbol of hope") → a tangible visual ("a single flower blooming through
  a crack in the concrete").
- **The model shows what you describe.** Mention red sneakers and you get a full-body shot even if
  you asked for a waist-up portrait. Remove details that force unwanted framing.
- **Aspect ratio changes framing.** The same prompt in 1:2 shows a full body; in 2:1 it crops to the
  waist. For full body, describe things near the feet; for a close-up, focus on upper-body
  features; for wider framing make the environment the subject.
- **Distorted faces or hands at a distance** → move the subject closer ("close-up", "portrait") or
  fix with Magic Fill afterwards.
- **Something important is missing** → move it earlier, repeat it in another part of the prompt
  (summary, details, framing), describe it more fully with size, color, texture, placement.

## Iterating

- **One-change rule**: change one thing per regeneration so you can attribute the effect.
- **Prompt chaining**: start simple ("a medieval castle"), add one element per step ("… on a
  hilltop", "… at sunset", "… with a dragon overhead").
- **Alternate wording**: "lush jungle" → "dense rainforest"; "sad expression" → "a face with
  downturned eyes and a slight frown".
- **Emphasis by repetition**: reference the focal subject in several parts of the prompt.
- Magic prompt itself can cause unwanted additions; if the image keeps gaining things you did not
  ask for, turn it off (that is, move to JSON mode).

## Style Reference, Color Palette, Describe (web app tools)

- **Style Reference** (up to three images, or preset styles): turn Magic Prompt off, avoid
  style keywords in the prompt, keep the prompt short and focused, and strip color words and
  stylistic sentences from a Describe output before applying a style to it.
- **Color Palette** setting: creative direction, not exact matching; combine with descriptive color
  words. Custom palettes take up to five colors on Plus and above.
- **Describe**: with model 4.0 selected it returns a structured JSON caption of any image (the
  basis of style-recipe extraction); with 3.0 it returns natural language.
