# Writing Ideogram 4 captions well

Condensed from Ideogram's open-source magic-prompt system prompt
(`ideogram-oss/ideogram4`, `src/ideogram4/magic_prompt_system_prompts/v1.txt`), the LLM
instructions Ideogram ships to turn a plain idea into a caption. The schema itself is in
`SKILL.md` and `docs/prompting.md`; this file is about *what to put in each field*. Two caveats
from Ideogram: this prompt is tested with Claude Opus, and it is not identical to the production
magic prompt behind ideogram.ai.

Note one deliberate difference: the shipped v1 prompt emits only `high_level_description` and
`compositional_deconstruction` (plus an `aspect_ratio` field the pipeline strips), and the
shipped configs strip bboxes by default. The official prompting guide and every official example
include `style_description`, and the hosted describe/magic-prompt API returns it too. Follow the
guide: include `style_description`, and use bboxes where placement matters.

## Contents

1. Output contract
2. high_level_description
3. Elements: what is one element
4. Element desc: what to write, what to leave out
5. Background: the shell rule
6. Bounding boxes
7. Specificity: commit to one value
8. Planning: medium, style, photoreal defaults, populating
9. Text handling
10. Pop culture, brands, named references
11. Transparent background

## 1. Output contract

- Emit a single JSON object, minified when sending, no markdown fences, no commentary, no
  keys beyond the schema.
- Preserve non-ASCII as literal characters (CJK, Cyrillic, Devanagari, Arabic, accented Latin).
  Never `\uNNNN`-escape, transliterate or strip accents (`café` stays `café`).
- In prose fields use **single quotes** for embedded text references (`the 'Joe's Diner' sign`).
  Only the `text` field of a text element holds the user's verbatim characters, any quoting.
- Prose (`high_level_description`, `background`, every `desc`) is in English regardless of the
  brief's language. Only `text` follows the brief's language.

## 2. high_level_description (50-word cap)

- One long sentence preferred, never more than two. Reads like a short prompt, not an analysis.
- Start with the subject. No "this image shows", "depicts", "captures".
- Name subject(s), medium, and overall composition. Name recognized entities in full
  (`Nike Air Jordan 1`, `Eiffel Tower`, `Mario (Nintendo character)`).
- Do not enumerate granular features (every color, grid dimension, typographic choice); that
  belongs in element descs or `background`. General words like "various", "multiple" are fine
  *here* and only here.
- For transparent backgrounds include the literal phrase `on a transparent background`.

Good: `A full-action shot of a male soccer player in a red kit and black Adidas cleats kicking a
soccer ball on a green turf field, with a blurred crowd in the stadium background.`

Bad (over-specified): `A male soccer player captured mid-kick on a bright green grass pitch, right
leg fully extended through the follow-through at the precise moment his black-and-white studded
boot makes contact with a white-and-black size-5 ball…`

## 3. Elements: what is one element

**Single subject = single element.** One animal, person, vehicle, building, plant, instrument or
machine is exactly one `obj`. Anatomical and structural parts are attributes in its `desc`.
Forbidden: a bee split into thorax/abdomen/wings/legs; a car into body/wheels/windshield; a person
into head/torso/limbs; a building into walls/windows/roof/door.

- Multiple distinct subjects (a person and a dog, three runners) → multiple elements, one each.
- Transparent enclosure plus featured contents (snow globe, aquarium, display case) → one element.
- Configured parts plus revealed interior (car with open door, machine with raised hood) → one element.
- Test: part of one thing → in that thing's desc. Separate thing → its own element.

## 4. Element desc (30–60 words, 60-word hard cap)

Identity first, then major attributes briefly, then one distinguishing detail. Each desc is a
standalone catalog entry: introduce the subject from scratch, not "the woman" as if the reader
had already seen the scene.

Always name:

- People: skin tone, hair color and style, each visible garment with color, expression or gaze,
  pose, one distinguishing feature (glasses, mole, jewelry, held prop).
- Objects: shape, material, color, distinctive parts (handle, label, logo, marking).
- Scenes and structures: type, primary material, color, distinctive structural elements.

Skip (they eat the word budget): surface-finish micro-prose (pick one of matte / glossy /
metallic / textured or omit), per-limb pose mechanics (one action phrase), fabric weave and skin
texture nuances.

Never include in a desc:

- **Shadows** of any kind (cast, drop, contact, ambient occlusion). Scene-wide shadowing goes in
  `background`; otherwise the renderer infers it.
- **Camera or render language**: depth of field, focus, bokeh, exposure, motion blur, lens
  flare, grain. Those live in `style_description` (`photo` / `art_style`) or, as natural prose,
  in `high_level_description` when the user asked for them. Exception: viewpoint (`from a
  low angle`, `bird's-eye view`) may appear once, usually in the focal subject's desc.
- **Impressions instead of physical reality**: luminous, radiant, vibrant, lush, dynamic,
  glowing (metaphorically), gorgeous, stunning, breathtaking, mesmerizing. Write observable
  properties: `cheekbone catches a small highlight`, not `luminous complexion`.
- **Repeated scene context**: lighting direction, weather, mounting surface are described once in
  `background`; each desc says what is unique to that element.

Anchor placement to named references: `applied to the forehead near the hairline above the left
eyebrow`, `resting on the lower-right corner of the table directly in front of the laptop`; not
`pressed against the skin`, `sitting on the surface`.

## 5. Background: the shell rule

`background` describes the scene **shell**: walls and finishes, floor or ground and its surface
state, ceiling and fixtures, windows as architecture, atmosphere (sky, clouds, fog, dust), scene-wide
ambient lighting, and distant out-of-focus context (horizon, blurred crowds, far scenery). It may be
long.

**No double counting.** Each component lives in exactly one field. Before emitting an element,
scan `background`; if it is named there, drop the element.

**Always background, never an element**: sky, clouds, atmospheric color; horizon; distant
mountains, hills, tree lines; fog, haze, mist, smoke; distant cityscape or stadium architecture;
distant or simplified crowds; the floor / ground / turf / paving the scene sits on; ambient walls or
studio backdrop. These cannot be split by region ("sky upper-left" is still the sky).

**Ground is always background, zero tolerance.** Floor, grass, dirt, sand, asphalt, deck, water
surface, snow, tile, hardwood, marble, plus their state: wet, rain-slicked, cracked, polished,
puddles, reflections, frost, footprints, tire tracks. Re-classify even when the brief lists
"wet pavement below" as a foreground item. Why: when a standing subject is the focal element and
the floor is also an `obj` at the bottom of the frame, the renderer treats the floor as a flat 2D
band instead of a receding plane and clips the subject's legs into it. Discrete objects *on* the
floor (shards, cans, leaves, tools) remain elements.

**Shell only, no placeable things.** Furniture, vehicles, equipment, people, animals, decor,
potted plants, free-standing lamps are elements, never background. Do not smuggle them in as
"rows of desks recede toward the back" or "customers seated at the tables"; the arrangement *is*
foreground content.

**Shell-affixed prominent objects get a dual mention.** A chalkboard covering the classroom's back
wall, a fireplace, a large mounted TV, a stage proscenium, a built-in bookshelf, a fixed reception
desk or banner: (1) mention it in `background` as part of the shell, (2) emit it as an `obj` whose
desc opens with "the primary background element" and carries the detail, (3) place it **first** in
`elements` so painter's-algorithm ordering draws it behind everything. Skipping step 1 makes the
renderer float it mid-room or in front of the foreground. This exception applies only to objects
that define the room's architectural identity; a framed picture or a table lamp is a normal element.

**No medium or post-processing effects in background**: film grain, lens flare, chromatic
aberration, vignetting, color cast, paper or canvas texture, brushstroke texture, halftone or
risograph texture. They describe *how* the image was made and belong in `style_description`.

Test: read `background` aloud. If you can picture the empty room with no furniture, people or
decor, you are in the shell. If something disappears when the room's contents are removed, it leaked.

## 6. Bounding boxes

Include bboxes where positioning matters: portrait subjects, products on a surface, logos, signs,
individually placeable objects, text blocks. Omit them for dense, unenumerable visuals: crowds,
wildflower fields, particles, starry skies. Decide per element.

Coordinates: `[y1, x1, y2, x2]`, `y1 < y2`, `x1 < x2`, both axes normalized 0–1000 to the target
frame, origin top-left. `[0, 0, 500, 1000]` is the top half; `[250, 250, 750, 750]` is roughly centered.

Shape warning: a "square" box `[0, 0, 500, 500]` is square only on a 1:1 frame; on 16:9 it is a wide
rectangle, on 9:16 a tall one. Most bbox failures (extra subjects, duplicates, mis-scaled objects)
come from this mismatch. For round or square things scale spans so `(x2-x1)/(y2-y1) ≈ H/W`: a
square object on a 16:9 frame needs an x-span 9/16 of its y-span. (The upstream system prompt prints
this ratio as `W/H`, which contradicts its own next sentence; the geometry and the sentence agree on
`H/W`.) For a single subject on a wide frame prefer a narrower x-span. For multiple subjects give each a tight box
so no box dominates and invites a duplicate. Pick the aspect ratio before writing any box.

## 7. Specificity: commit to one value

The JSON feeds a diffusion model; leave nothing for it to choose.

- Banned hedges in elements and background: `things like`, `such as`, `e.g.`, `for example`,
  `or similar`, `various`, `could include`, `might be`, `some kind of`, `style of`.
- Banned alternatives for one property: `oak or walnut`, `cream or ivory`, `late afternoon or early
  evening`, `italic serif or italic sans-serif`, `bold or semibold`. Pick one. `or` is reserved for
  an actual exclusive choice rendered in the image (`'YES' or 'NO'` buttons).
- Typography: one family (serif / sans-serif / display / script / monospace), one weight, one
  style (italic or upright).
- Banned "implied" hedges: `implied`, `suggested`, `hinted`, `barely visible`, `possibly`,
  `perhaps`, `maybe`, `might be`, `could be`, `reads as`, `almost`. Paint it or leave it out.
- Exhaustive content preservation: schedules, itineraries, menus, lists, names, times: every item
  appears, using as many text elements as needed.
- Every visual unit the user named must appear as its own element: each quoted string → a text
  element; each speech bubble → a text element for the words plus an obj for the bubble; each named
  icon, badge, chip, CTA, divider or accent line → its own obj (unless it is a scene-wide overlay
  belonging in `background`). Count named units in the brief; the element list has at least that many.
- No placeholder enumeration: a numbered or labeled set (stones 1–50, parking spaces A1–A20,
  31 calendar dates, a 22-name roster) lists **every** item. `etc.` and `and so on` are forbidden.
  The "dense unenumerable" exception never applies to identified sets.
- Do not invent visual concepts the user did not ask for (glitch art, wireframe overlays,
  dissolving bodies, digital artifacts).

## 8. Planning

### Pick a medium

`photograph | illustration | 3D render | graphic design`, expressed in `style_description.medium`
and echoed as natural framing in `high_level_description`. The decision is *designed artifact*
versus *captured / drawn / rendered moment*:

- **graphic design**: poster, book or album or magazine cover, flyer, banner, social post,
  sticker, logo, wordmark, packaging, app icon, UI mockup, infographic, menu, greeting card,
  ticket, signage. If a human designer would sit at a desk to make it.
- **photograph**: portrait, landscape, lifestyle, street, sport, wildlife, food, product, fashion
  editorial described as a photo. Default for ambiguous everyday scenes.
- **illustration**: cartoon, anime, manga, comic, watercolor, oil, ink, vector, pixel art,
  children's book, named studios (Ghibli, KyoAni, Pixar 2D).
- **3D render**: CGI, Octane/Unreal/Blender, hyperreal product render, arch viz, isometric
  low-poly, voxel.

Silent or ambiguous → photograph. Wizards, dragons and robots in a photograph are valid; the brief
must explicitly ask for illustration or render to get one. Imperative verbs ("Illustrate a…",
"Paint a…", "Render a…") are *not* medium signals; they mean "show".

### Style commitment

Name the style once, briefly, with a recognizable label: `Studio Ghibli animation`, `Pixar 3D
animation`, `35mm film photograph`, `iPhone photo`, `editorial digital painting`, `flat vector
illustration`. Do not pile technique detail onto a well-known name.

"Professional picture / photo / portrait" of a person means a professional *context* (corporate
headshot, LinkedIn, business bio: neutral business attire, soft even daylight, neutral backdrop,
approachable expression), not professional camera gear (no dramatic rim light, creamy bokeh, moody
backdrop).

### Photoreal defaults (when the brief says photo / photorealistic / selfie / real-world scene and nothing more)

- Default to a phone-snapshot aesthetic: ambient natural light, neutral white balance, accurate
  skin tones, ordinary framing. Avoid DSLR-magazine markers (creamy bokeh, telephoto compression,
  dramatic rim lighting, cinematic grade); they read as AI-generated.
- Default lighting words: `natural daylight`, `overcast daylight`, `diffused daylight`,
  `cool-neutral white balance`. Do not use **"warm"** as a grading adjective (`warm light`, `warm
  tone`, `warm grading`); it triggers the amber AI look. When a scene physically has a warm source
  (candle, sodium streetlamp, sunset) describe the source and its light pool concretely (`amber
  pool from the candle`) while the global grade stays neutral.
- Default composition: off-center, rule of thirds, asymmetry, leading lines. Centered only when the
  brief asks for it (`centered`, `symmetrical`, `mandala`) or the genre is inherently symmetric.
- No motion blur in candid or phone-style photos; real snapshots freeze the moment.
- Mention saturation at most once, and only when asked. Do not stack `vibrant + bright + intense +
  saturated + electric + neon` on a neutral subject.

These are defaults, not bans: when the user asks for golden hour, cinematic grade or warm tones,
give them exactly that (the official sailboat example uses "serene, warm, golden hour").

### Populate underspecified scenes

Real scenes are populated. When the brief is sparse, add believable secondary subjects, micro-props
that imply the subject's life, environmental texture and small narrative moments, each belonging to
the world the brief implies (a paddy-field food stall plausibly has a chicken, a sauce bowl, a
hand-painted price sign, a lantern).

- Populate by depth layer: foreground (often skipped: an out-of-focus leaf in the corner, the rim
  of a bowl), midground, background.
- Commit to a specific cultural or regional identity: "Vietnamese pho stall by the rice paddies
  outside Hoi An", not "Southeast Asian village". Specificity shapes architecture, script, food,
  dress and props.
- Built environments carry text everywhere: shop name, sub-signs (`OPEN`, `TODAY'S SPECIAL`),
  menu boards, price labels, jar and bottle labels, name tags, posters, vehicle and equipment
  labels, sponsor logos. Zero text elements is almost always wrong for a shop, stall, restaurant,
  workshop, market or vehicle. Specific content, never "various labels".
- Fantastical, sci-fi and futuristic briefs get a populate bonus: sky drama (galaxies, ringed
  planets, several moons), opposing focal points, mid-distance scale anchors, light and energy
  effects, exotic architecture, deeply saturated palettes.
- Override: when the brief says `minimal`, `sparse`, `empty`, `lonely`, `isolated`, `quiet`,
  `still`, `negative space`, `alone`, `single subject`, `in the middle of nowhere`, respect the
  restraint and skip populating.

## 9. Text handling

Each text element: `text` = literal characters, verbatim, with diacritics, capitalization and
punctuation intact; `bbox` optional; `desc` = size, location, font style, color, orientation,
effects.

Sources of text to include:

1. User-quoted text (single or double quotes) — exact characters.
2. Format-required text — headlines, taglines, author names, dates, venues, CTAs, brand names,
   publisher marks, edition numbers when the format implies them.
3. In-scene contextual text — signage, labels, license plates, badges, jersey numbers, T-shirt
   prints, awnings, neon signs, name tags.
4. Numeric content — race numbers, dates, prices, scores, time displays, addresses. Numbers are text.
5. Prominent product brand text — if a bottle, package or beverage is prominent and the user gave
   no brand, invent a complete brand identity and list every label.

Rules:

- Exhaustive: if a viewer could read it, it is in the list.
- Each text element appears once. Do not also spell its characters out in `desc`; refer to it by
  role or position.
- `\n` for line breaks within one block (stacked headline, multi-line sign); separate elements for
  visually distinct blocks.
- Stylized hero typography where each letter is a visual unit: stack with `\n` at natural word
  breaks (`"ENTRE\nVERSOS E\nCONTOS"`, not one long line); long single-line stylized titles produce
  typos and dropped letters.
- Language scoping: prose in English; only `text` follows the brief's language.

## 10. Pop culture, brands, named references

When the brief names or clearly implies a brand, product, public figure, athlete, musician,
fictional character, film, show, game, franchise or team, the caption carries the explicit name in
the relevant desc, not a generic look-alike description. Not `black and white retro sneakers` for
`Nike Dunk Low Panda`, not `a red-and-blue masked superhero` for `Spider-Man`, unless the user
asked for an anonymous lookalike.

## 11. Transparent background

If the brief calls for a transparent background, alpha channel, cutout, isolated subject or
sticker with no backdrop: `background` is exactly the string `transparent background` (no
paraphrase: not `clear backdrop`, `no background`, `PNG transparency`), and
`high_level_description` includes the phrase `on a transparent background`. Generate through a
transparent-background endpoint (`/v1/ideogram-v4/generate-transparent`) or the MCP's equivalent
so the alpha channel is actually produced.
