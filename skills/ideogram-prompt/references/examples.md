# Official Ideogram 4 caption examples

All examples below are reproduced from official Ideogram sources: `docs/prompting.md` in
`ideogram-oss/ideogram4`, the docs.ideogram.ai "JSON Prompting (Ideogram 4.0)" page, and the
"Ideogram 4.0 prompt guide" blog post. They pass `scripts/validate_caption.py`. Use them as
patterns, not as templates to copy verbatim.

## 1. Photo, no bboxes, with palette (prompting guide and docs, "warm sunset palette")

Rendered in the docs at aspect ratio 1:2 with Magic Prompt off.

```json
{
  "high_level_description": "A lone sailboat on calm water at sunset.",
  "style_description": {
    "aesthetics": "serene, warm, golden hour",
    "lighting": "golden hour backlighting, warm atmospheric haze",
    "photo": "wide angle, f/8, long exposure",
    "medium": "photograph",
    "color_palette": ["#FF6B35", "#F7C59F", "#004E89", "#1A659E", "#2B2D42"]
  },
  "compositional_deconstruction": {
    "background": "A calm ocean stretching to a low horizon, sky washed in orange and pink with thin wisps of cloud.",
    "elements": [
      {"type": "obj", "desc": "A single sailboat with a white triangular sail, silhouetted against the setting sun."}
    ]
  }
}
```

## 2. Photo with bboxes (prompting guide, skateboarding retriever)

```json
{
  "high_level_description": "A golden retriever riding a skateboard down a sunny sidewalk.",
  "style_description": {
    "aesthetics": "warm, playful, vibrant",
    "lighting": "bright afternoon sunlight, long soft shadows",
    "photo": "shallow depth of field, eye-level, 85mm lens",
    "medium": "photograph",
    "color_palette": ["#F5C542", "#87CEEB", "#4A4A4A", "#FFFFFF", "#2E8B57"]
  },
  "compositional_deconstruction": {
    "background": "A sun-drenched suburban sidewalk lined with green hedges and a white picket fence. Dappled light filters through overhead trees.",
    "elements": [
      {"type": "obj", "bbox": [200, 300, 800, 900], "desc": "A golden retriever with a fluffy coat, standing on a red skateboard with all four paws. Its tongue is out and ears are flapping in the wind."},
      {"type": "obj", "bbox": [250, 750, 750, 950], "desc": "A worn red skateboard with black wheels rolling along the concrete sidewalk."}
    ]
  }
}
```

## 3. Graphic design with text, no bboxes (prompting guide, "corporate design palette")

```json
{
  "high_level_description": "A clean, modern business card layout for a tech company.",
  "style_description": {
    "aesthetics": "minimal, professional, geometric",
    "lighting": "even, diffuse studio lighting",
    "medium": "graphic_design",
    "art_style": "flat vector design, generous whitespace, sans-serif typography",
    "color_palette": ["#FFFFFF", "#F0F0F0", "#333333", "#0066FF", "#00CC88"]
  },
  "compositional_deconstruction": {
    "background": "A solid off-white card surface with subtle paper texture.",
    "elements": [
      {"type": "text", "text": "ACME TECH", "desc": "Bold dark grey sans-serif company name across the upper third of the card."},
      {"type": "text", "text": "hello@acme.tech", "desc": "Small blue sans-serif contact email near the bottom of the card."}
    ]
  }
}
```

## 4. Poster with bboxes on every element (docs.ideogram.ai, "Blue Note Sessions")

Rendered at 1:2 with Magic Prompt off. Note how each text block has its own zone so the layout
holds across runs.

```json
{
  "high_level_description": "A bold event poster for a jazz night called 'Blue Note Sessions' at The Velvet Room, Saturday August 9th.",
  "style_description": {
    "aesthetics": "moody, retro, sophisticated, 1960s jazz club aesthetic",
    "lighting": "dramatic, deep shadows, warm spotlight glow",
    "medium": "graphic_design",
    "art_style": "vintage poster design, textured paper, bold typography, muted color palette with warm accents",
    "color_palette": ["#1A1A2E", "#16213E", "#E8C97A", "#D4A843", "#F5F0E8", "#8B4513"]
  },
  "compositional_deconstruction": {
    "background": "Deep navy and near-black background with subtle aged paper texture and faint horizontal grain lines.",
    "elements": [
      {"type": "obj", "bbox": [150, 200, 650, 800], "desc": "A silhouetted jazz trumpeter in side profile, mid-performance, instrument raised. Warm golden spotlight illuminates from above, casting dramatic shadows. Stylized, slightly abstract illustration style."},
      {"type": "text", "bbox": [30, 50, 140, 950], "text": "BLUE NOTE SESSIONS", "desc": "Large bold all-caps serif headline in warm golden-yellow, spanning the full width near the top of the poster."},
      {"type": "text", "bbox": [660, 100, 760, 900], "text": "Live jazz every Saturday night", "desc": "Medium-weight italic serif subheading in off-white, centered beneath the main title."},
      {"type": "text", "bbox": [820, 200, 900, 800], "text": "THE VELVET ROOM", "desc": "Smaller all-caps sans-serif venue name in warm gold, centered near the bottom."},
      {"type": "text", "bbox": [900, 300, 970, 700], "text": "SAT · AUGUST 9", "desc": "Small light-weight serif date text in off-white, near the bottom of the poster."}
    ]
  }
}
```

## 5. Claude-written photoreal caption (blog, the wolf, magic prompt off)

The brief was four words: "a wolf in a snowy forest". Note the neutral photoreal choices: natural
light, cool key with one warm accent named as a source, off-center framing, no motion blur, one
element for the whole animal, forest and snow plane in `background`.

```json
{
  "high_level_description": "A cinematic editorial photograph of a grey wolf standing alert in a snowy boreal forest, full body visible, head three-quarters toward camera, amber eyes sharp. Authentic natural light, cool blue shadows, distant amber glow.",
  "style_description": {
    "aesthetics": "cool blue-grey and warm amber, asymmetrical rule of thirds, cinematic editorial",
    "lighting": "overcast natural light, cool blue key, warm amber accent deep in trees",
    "photo": "medium depth of field, eye-level, natural light",
    "medium": "photograph"
  },
  "compositional_deconstruction": {
    "background": "Dense boreal pine forest in deep winter. Blue-grey overcast light through snow-laden branches. Flat plane of undisturbed deep snow. Distant warm amber glow. Bokeh pine trunks with cool blue shadows.",
    "elements": [
      {"type": "obj", "desc": "Grey wolf at left-of-center, full body paws to ear-tips. Head three-quarters toward camera, ears forward, amber-gold eyes in crisp focus. Grey fur, cream belly markings, steam breath at muzzle. All four legs planted in snow. Sharp from ears to front paws, background in soft bokeh."}
    ]
  }
}
```

The plain-mode counterpart from the same post, for comparison (magic prompt on):

> A grey wolf standing alert in a snowy boreal forest. Full body visible from paws to the tips of
> its ears. Head turned three-quarters toward the camera, ears upright and forward, amber-gold eyes
> catching the light. Dense grey winter fur with cream belly markings, slight steam breath visible
> at the muzzle in the cold air. All four legs fully visible and planted in deep snow. In the
> background: a dense pine forest in deep winter, blue-grey overcast light filtering through
> snow-laden branches, a distant warm amber glow deep in the trees. Bokeh pine trunks receding into
> the distance, cool blue shadows pooling between them. Cinematic editorial photograph, medium
> depth of field, eye-level angle, natural available light.

## 6. Training-style caption with many text elements (prompting guide, "Full example")

This is how a *training* caption looks: exhaustive, one element per readable string, sponsor
logos and even the watermark listed, real names kept. It shows the density the model was trained
on; you rarely need this many elements, but every visible string in your design should be an
element.

```json
{
  "high_level_description": "A medium-shot photograph of Formula 1 driver Max Verstappen wearing his Red Bull Racing racing suit and cap, smiling as he holds his racing helmet and talks to a man in a white shirt and black vest at a race track.",
  "style_description": {
    "aesthetics": "saturated primary colors, rule of thirds, joyful and triumphant",
    "lighting": "overcast daylight, diffused, soft subtle shadows",
    "photo": "shallow depth of field, sharp focus, eye-level, telephoto",
    "medium": "photograph"
  },
  "compositional_deconstruction": {
    "background": "The background is an out-of-focus racing paddock or track environment. Several blurred figures are visible, including one in an orange shirt. A purple and white structure with a red 'F1' logo stands on the left. The scene is outdoors with daylight, though the sky is not visible.",
    "elements": [
      {"type": "obj", "bbox": [55, 642, 1000, 937], "desc": "An older man standing in profile, facing left toward Max Verstappen. He has grey hair and fair skin. He is wearing a white long-sleeved button-down shirt with a navy blue quilted vest over it. He has a slight smile."},
      {"type": "obj", "bbox": [34, 137, 1000, 617], "desc": "Max Verstappen, a fair-skinned male Formula 1 driver, positioned in the center. He is facing forward with a joyful expression and a slight smile. He wears a navy blue Red Bull Racing team uniform with numerous sponsor logos and a matching baseball cap with the number '1'. He is holding a white and red racing helmet in his hands. He has a silver watch on his left wrist."},
      {"type": "obj", "bbox": [422, 212, 792, 452], "desc": "Max Verstappen's racing helmet, held in front of his chest. It features a white, red, and yellow design with the Red Bull logo and the 'Player 0.0' branding. The visor is clear and open."},
      {"type": "text", "bbox": [657, 0, 755, 142], "text": "F1", "desc": "Large, stylized red logo on a black and purple background in the lower left."},
      {"type": "text", "bbox": [768, 0, 818, 147], "text": "Formula 1\nWorld Championship™", "desc": "Small white sans-serif text below the F1 logo on the left side."},
      {"type": "text", "bbox": [78, 447, 117, 510], "text": "ORACLE\nRed Bull\nRacing", "desc": "Very small white and orange logo on the front of the navy blue cap."},
      {"type": "text", "bbox": [78, 417, 120, 440], "text": "1", "desc": "Bold red numeral '1' on the front left side of the navy blue cap."},
      {"type": "text", "bbox": [332, 442, 363, 483], "text": "Red Bull", "desc": "Small yellow and red text logo on the collar of the uniform."},
      {"type": "text", "bbox": [373, 490, 423, 532], "text": "RAUCH", "desc": "Small yellow and blue logo on the right chest of the uniform."},
      {"type": "text", "bbox": [422, 473, 500, 532], "text": "BYBIT\nHONDA", "desc": "Medium-sized white sans-serif text on the right chest of the uniform."},
      {"type": "text", "bbox": [410, 203, 442, 257], "text": "RAUCH", "desc": "Small yellow logo on the left upper arm of the uniform."},
      {"type": "text", "bbox": [530, 448, 627, 510], "text": "Red Bull", "desc": "Medium red text logo on the right side of the torso, part of the Red Bull graphic."},
      {"type": "text", "bbox": [680, 417, 768, 523], "text": "Red Bull", "desc": "Large red text logo across the lower torso of the uniform."},
      {"type": "text", "bbox": [797, 475, 815, 518], "text": "MAX", "desc": "Small white text next to a Dutch flag on the belt area of the uniform."},
      {"type": "text", "bbox": [558, 317, 715, 355], "text": "Player 0.0", "desc": "Black sans-serif text on a white band on the racing helmet."},
      {"type": "text", "bbox": [560, 800, 582, 835], "text": "IA.COM", "desc": "Small blue sans-serif text on the right sleeve of the white shirt."},
      {"type": "text", "bbox": [968, 8, 997, 332], "text": "© Anadolu Agency via Getty Images", "desc": "Small white watermark text in the bottom left corner."}
    ]
  }
}
```

## 7. Hosted magic-prompt output shape (API reference example)

What `POST /v1/ideogram-v4/magic-prompt` returned for `"A photo of a cat"` with `AUTO` ratio (the
model picked `1x1`). Note it lacks `photo`/`art_style`; run `--fix` and add `photo` before sending
it to the open-weights pipeline, which enforces the strict schema.

```json
{
  "json_prompt": {
    "high_level_description": "A photorealistic ginger cat perched on a vintage wooden chair by a sunlit window.",
    "compositional_deconstruction": {
      "background": "A dim room with a bright window casting warm light.",
      "elements": [
        {"type": "obj", "desc": "ginger cat with green eyes sitting upright on a vintage wooden chair"}
      ]
    },
    "style_description": {
      "aesthetics": "warm, cozy, nostalgic",
      "lighting": "soft natural window light",
      "medium": "photograph"
    }
  },
  "aspect_ratio": "1x1"
}
```

## 8. Plain-text examples from the blog gallery (magic prompt on)

Short, style-led prose that lets magic prompt do the expansion:

- 19th-century botanical illustration: passion fruit cross-section, watercolor over ink, coral arils and purple-black rind on cream laid paper.
- Julius Shulman-style architectural photograph: mid-century modern glass house cantilevered over a hillside at dusk, warm amber interior, city lights below.
- Literary novel cover: THE CARTOGRAPHER'S DAUGHTER in tall serif, solitary figure on an ice floe, aurora borealis in deep navy, flat graphic with coarse halftone.
- Risograph print, two-color fluorescent orange and deep teal: a toucan on a tropical branch with monstera leaves, coarse halftone dots, deliberate ink misregistration.
- Swiss International Style poster on crimson red: CUSTOM COACHWORK in large all-capitals yellow slab serif at top left, a black-and-white vintage photograph of a 1950s hot rod at center-right, small yellow serif body copy at lower right.
