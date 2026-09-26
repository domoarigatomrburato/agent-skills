#!/usr/bin/env python3
"""Validate, fix and minify an Ideogram 4 JSON caption.

The schema checks are a faithful port of ``CaptionVerifier`` from the official
``ideogram-oss/ideogram4`` repository (``src/ideogram4/caption_verifier.py``),
which is what the reference inference pipeline runs on every prompt. On top of
that, this script adds *advisory hints* taken from Ideogram's open-source
magic-prompt guidance (hedge words, over-long fields, stray ``aspect_ratio``).
Hints never fail the run; schema issues do.

Standard library only. Works on Python 3.8+.

Usage
-----
  validate_caption.py caption.json                 # report; exit 1 if schema issues
  validate_caption.py - < caption.json             # read the caption from stdin
  validate_caption.py caption.json --fix           # repair key order, hex case, stray
                                                   # aspect_ratio, integral bbox floats
  validate_caption.py caption.json --fix --minify  # print the single-line string to send
  validate_caption.py caption.json --strip-bbox    # drop every bbox (free placement)
  validate_caption.py caption.json --fix -o out.json --quiet
  validate_caption.py --plain prompt.txt            # lint a plain-text (magic prompt ON) prompt

Exit codes: 0 clean, 1 schema issues remain after any fixing, 2 input error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Schema constants (mirror CaptionVerifier)
# --------------------------------------------------------------------------- #

TOP_LEVEL_KEYS = frozenset(
  {"high_level_description", "style_description", "compositional_deconstruction"}
)
TOP_LEVEL_ORDER = ("high_level_description", "style_description", "compositional_deconstruction")

STYLE_ORDER_PHOTO = ("aesthetics", "lighting", "photo", "medium", "color_palette")
STYLE_ORDER_NON_PHOTO = ("aesthetics", "lighting", "medium", "art_style", "color_palette")
STYLE_KNOWN = frozenset({"aesthetics", "lighting", "photo", "art_style", "medium", "color_palette"})
STYLE_REQUIRED = ("aesthetics", "lighting", "medium")

CD_ORDER = ("background", "elements")

ELEMENT_ORDER_OBJ = ("type", "bbox", "desc", "color_palette")
ELEMENT_ORDER_TEXT = ("type", "bbox", "text", "desc", "color_palette")
ELEMENT_KNOWN = frozenset({"type", "bbox", "text", "desc", "color_palette"})
ELEMENT_TYPES = frozenset({"obj", "text"})

BBOX_MIN, BBOX_MAX = 0, 1000
STYLE_PALETTE_MAX = 16
ELEMENT_PALETTE_MAX = 5

# Matches \uXXXX escapes for non-ASCII code points (same regex as upstream).
NON_ASCII_UNICODE_ESCAPE_RE = re.compile(
  r"\\u(?:00[89a-fA-F][0-9a-fA-F]|0[1-9a-fA-F][0-9a-fA-F]{2}|[1-9a-fA-F][0-9a-fA-F]{3})"
)

HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
ANY_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")

# Advisory-only vocab from the open-source magic-prompt system prompt.
HEDGE_PHRASES = (
  "things like", "such as", "e.g.", "for example", "or similar", "various",
  "could include", "might be", "some kind of", "style of", "implied", "suggested",
  "hinted", "barely visible", "possibly", "perhaps", "maybe", "could be",
  "reads as", "almost", "etc.", "and so on",
)
IMPRESSION_WORDS = (
  "luminous", "radiant", "gorgeous", "stunning", "breathtaking", "mesmerizing",
)
NEGATION_RE = re.compile(r"\b(no|without)\b", re.IGNORECASE)
HLD_WORD_CAP = 50
DESC_WORD_CAP = 60
TOKEN_BUDGET = 2048  # open-weights pipeline max_text_tokens


# --------------------------------------------------------------------------- #
# Verification (port of CaptionVerifier; returns lists of strings)
# --------------------------------------------------------------------------- #


def check_ensure_ascii_false(raw_text: str, max_examples: int = 3) -> List[str]:
  matches = NON_ASCII_UNICODE_ESCAPE_RE.findall(raw_text)
  if not matches:
    return []
  if any(ord(c) > 0x7F for c in raw_text):
    return []  # both forms coexist; assume escapes are intentional
  uniq = sorted(set(matches))
  examples = ", ".join(uniq[:max_examples]) + ("" if len(uniq) <= max_examples else ", ...")
  return [
    f"raw text: {len(matches)} non-ASCII \\uXXXX escape(s) (e.g. {examples}) and no literal "
    "non-ASCII characters. Serialize with ensure_ascii=False so 'café' stays 'café'."
  ]


def _style_order_for(sd: Dict[str, Any]) -> Optional[Sequence[str]]:
  has_photo, has_art = "photo" in sd, "art_style" in sd
  if has_photo == has_art:
    return None
  order = STYLE_ORDER_PHOTO if has_photo else STYLE_ORDER_NON_PHOTO
  return tuple(k for k in order if k != "color_palette" or "color_palette" in sd)


def _element_order_for(elem: Dict[str, Any]) -> Optional[Sequence[str]]:
  t = elem.get("type")
  if t == "obj":
    order = ELEMENT_ORDER_OBJ
  elif t == "text":
    order = ELEMENT_ORDER_TEXT
  else:
    return None
  return tuple(
    k for k in order
    if k not in ("bbox", "color_palette") or k in elem
  )


def _check_key_order(obj: Dict[str, Any], expected: Sequence[str], path: str, out: List[str]) -> None:
  present = tuple(k for k in obj if k in expected)
  if present != tuple(expected):
    out.append(f"{path}: key order is {present}, expected {tuple(expected)}")
  extra = [k for k in obj if k not in expected]
  if extra:
    out.append(f"{path}: keys {extra} are not allowed in this context")


def _check_unknown(obj: Dict[str, Any], known: frozenset, path: str, out: List[str]) -> None:
  unknown = [k for k in obj if k not in known]
  if unknown:
    out.append(f"{path}: unknown keys {unknown} (not in schema)")


def _verify_palette(palette: Any, path: str, max_colors: int, out: List[str]) -> None:
  if not isinstance(palette, list):
    out.append(f"{path}: expected a list")
    return
  if len(palette) > max_colors:
    out.append(f"{path}: too many colors ({len(palette)}), expected at most {max_colors}")
    return
  for i, color in enumerate(palette):
    if not isinstance(color, str) or not HEX_RE.match(color):
      out.append(f"{path}[{i}]: '{color}' is not a valid uppercase #RRGGBB hex color")


def _verify_bbox(i: int, bbox: Any, out: List[str]) -> None:
  if not isinstance(bbox, list) or len(bbox) != 4:
    out.append(f"elements[{i}].bbox: expected [ymin, xmin, ymax, xmax]")
    return
  if not all(isinstance(v, int) and not isinstance(v, bool) for v in bbox):
    out.append(f"elements[{i}].bbox: all values must be int (got {bbox})")
    return
  ymin, xmin, ymax, xmax = bbox
  if not all(BBOX_MIN <= v <= BBOX_MAX for v in bbox):
    out.append(f"elements[{i}].bbox: values must be in [{BBOX_MIN}, {BBOX_MAX}], got {bbox}")
  if ymin > ymax:
    out.append(f"elements[{i}].bbox: ymin ({ymin}) > ymax ({ymax})")
  if xmin > xmax:
    out.append(f"elements[{i}].bbox: xmin ({xmin}) > xmax ({xmax})")


def _verify_style(sd: Any, out: List[str]) -> None:
  if not isinstance(sd, dict):
    out.append("style_description: expected a dict")
    return
  _check_unknown(sd, STYLE_KNOWN, "style_description", out)
  has_photo, has_art = "photo" in sd, "art_style" in sd
  if has_photo and has_art:
    out.append("style_description: contains both 'photo' and 'art_style'; expected exactly one")
    return
  if not has_photo and not has_art:
    out.append(
      "style_description: expected one of 'photo' (for photo captions) or 'art_style' "
      "(for non-photo captions)"
    )
    return
  for k in STYLE_REQUIRED:
    if k not in sd:
      out.append(f"style_description: '{k}' is required when style_description is present")
  _check_key_order(sd, _style_order_for(sd) or (), "style_description", out)
  if "color_palette" in sd:
    _verify_palette(sd["color_palette"], "style_description.color_palette", STYLE_PALETTE_MAX, out)
  for k in ("aesthetics", "lighting", "photo", "art_style", "medium"):
    if k in sd and not isinstance(sd[k], str):
      out.append(f"style_description.{k}: expected a string")


def _verify_element(i: int, elem: Any, out: List[str]) -> None:
  if not isinstance(elem, dict):
    out.append(f"elements[{i}]: expected a dict")
    return
  _check_unknown(elem, ELEMENT_KNOWN, f"elements[{i}]", out)
  if "type" not in elem:
    out.append(f"elements[{i}]: 'type' must exist")
    return
  if elem.get("type") not in ELEMENT_TYPES:
    out.append(f"elements[{i}]: 'type' must be one of {sorted(ELEMENT_TYPES)}")
    return
  _check_key_order(elem, _element_order_for(elem) or (), f"elements[{i}]", out)
  if "desc" not in elem:
    out.append(f"elements[{i}]: 'desc' must exist")
  elif not isinstance(elem["desc"], str):
    out.append(f"elements[{i}].desc: expected a string")
  if elem["type"] == "text":
    if "text" not in elem:
      out.append(f"elements[{i}]: text element must have a 'text' field")
    elif not isinstance(elem["text"], str) or not elem["text"].strip():
      out.append(f"elements[{i}].text: expected a non-empty string")
  if "bbox" in elem:
    _verify_bbox(i, elem["bbox"], out)
  if "color_palette" in elem:
    _verify_palette(elem["color_palette"], f"elements[{i}].color_palette", ELEMENT_PALETTE_MAX, out)


def _verify_cd(cd: Any, out: List[str]) -> None:
  if not isinstance(cd, dict):
    out.append("compositional_deconstruction: expected a dict")
    return
  if "background" not in cd:
    out.append("compositional_deconstruction: 'background' must exist")
    return
  if not isinstance(cd["background"], str):
    out.append("compositional_deconstruction.background: expected a string")
    return
  if "elements" not in cd:
    out.append("compositional_deconstruction: 'elements' must exist")
    return
  _check_key_order(cd, CD_ORDER, "compositional_deconstruction", out)
  elements = cd["elements"]
  if not isinstance(elements, list):
    out.append("compositional_deconstruction.elements: expected a list")
    return
  for i, elem in enumerate(elements):
    _verify_element(i, elem, out)


def verify(caption: Any) -> List[str]:
  """Schema issues (the checks the reference pipeline enforces)."""
  out: List[str] = []
  if not isinstance(caption, dict):
    return [f"root: expected a JSON object, got {type(caption).__name__}"]
  _check_unknown(caption, TOP_LEVEL_KEYS, "root", out)
  present = tuple(k for k in caption if k in TOP_LEVEL_ORDER)
  expected = tuple(k for k in TOP_LEVEL_ORDER if k in caption)
  if present != expected:
    out.append(f"root: key order is {present}, expected {expected}")
  if "high_level_description" in caption and not isinstance(caption["high_level_description"], str):
    out.append("high_level_description: expected a string")
  if "style_description" in caption:
    _verify_style(caption["style_description"], out)
  if "compositional_deconstruction" in caption:
    _verify_cd(caption["compositional_deconstruction"], out)
  else:
    out.append("root: 'compositional_deconstruction' must exist")
  return out


# --------------------------------------------------------------------------- #
# Advisory hints (never fail the run)
# --------------------------------------------------------------------------- #


def _words(s: str) -> int:
  return len(s.split())


def _scan_prose(text: str, path: str, out: List[str]) -> None:
  low = text.lower()
  hedges = [h for h in HEDGE_PHRASES if h in low]
  if hedges:
    out.append(f"{path}: hedge wording {hedges}; commit to one concrete value")
  imps = [w for w in IMPRESSION_WORDS if w in low]
  if imps:
    out.append(f"{path}: impression words {imps}; describe observable properties instead")
  if NEGATION_RE.search(text):
    out.append(f"{path}: contains negation ('no', 'without'); describe what IS there instead")
  if '"' in text:
    out.append(f"{path}: double quotes inside prose; use single quotes when referring to text")


def hints(caption: Any, minified: str) -> List[str]:
  out: List[str] = []
  if not isinstance(caption, dict):
    return out
  if "aspect_ratio" in caption:
    out.append(
      "root: 'aspect_ratio' is a magic-prompt intermediate, not a caption key; the pipeline "
      "strips it and the API rejects it. Pass aspect ratio/resolution as a request parameter."
    )
  if "high_level_description" not in caption:
    out.append("root: 'high_level_description' is strongly recommended (the REST API requires it)")
  if "style_description" not in caption:
    out.append("root: no 'style_description'; official examples always include one")
  hld = caption.get("high_level_description")
  if isinstance(hld, str):
    if _words(hld) > HLD_WORD_CAP:
      out.append(f"high_level_description: {_words(hld)} words; aim for one or two sentences under {HLD_WORD_CAP}")
    low = hld.lower()
    for opener in ("this image shows", "this image depicts", "the image shows", "an image of"):
      if low.startswith(opener):
        out.append("high_level_description: start with the subject, not 'this image shows'")
        break
    _scan_prose(hld, "high_level_description", out)
  sd = caption.get("style_description")
  if isinstance(sd, dict):
    for k in ("aesthetics", "lighting", "photo", "art_style"):
      if isinstance(sd.get(k), str):
        _scan_prose(sd[k], f"style_description.{k}", out)
  cd = caption.get("compositional_deconstruction")
  if isinstance(cd, dict):
    bg = cd.get("background")
    if isinstance(bg, str):
      _scan_prose(bg, "background", out)
      if bg.strip().lower() != bg.strip() and bg.strip().lower() == "transparent background":
        out.append("background: transparent background must be exactly the lowercase string 'transparent background'")
    for i, e in enumerate(cd.get("elements") or []):
      if not isinstance(e, dict):
        continue
      d = e.get("desc")
      if isinstance(d, str):
        if _words(d) > DESC_WORD_CAP:
          out.append(f"elements[{i}].desc: {_words(d)} words; cap is {DESC_WORD_CAP}")
        _scan_prose(d, f"elements[{i}].desc", out)
        t = e.get("text")
        if isinstance(t, str) and len(t) > 3 and t.lower() in d.lower():
          out.append(f"elements[{i}].desc: repeats the literal text; describe style/position instead")
      if "bbox" not in e and e.get("type") == "text":
        out.append(f"elements[{i}]: text element without bbox; give text blocks a box when placement matters")
    if isinstance(bg, str) and bg.strip() == "transparent background" and isinstance(hld, str):
      if "on a transparent background" not in hld.lower():
        out.append("high_level_description: add the phrase 'on a transparent background'")
  est_tokens = len(minified) / 3.2  # rough English/JSON estimate for the Qwen tokenizer
  if est_tokens > TOKEN_BUDGET:
    out.append(f"caption is roughly {int(est_tokens)} tokens; the open-weights pipeline caps text at {TOKEN_BUDGET}")
  return out


# --------------------------------------------------------------------------- #
# Fixing
# --------------------------------------------------------------------------- #


def _ordered(d: Dict[str, Any], order: Sequence[str]) -> Dict[str, Any]:
  known = [k for k in order if k in d]
  extra = [k for k in d if k not in order]
  return {k: d[k] for k in (*known, *extra)}


def _fix_hex(value: Any) -> Any:
  if isinstance(value, str) and ANY_HEX_RE.match(value):
    body = value[1:]
    if len(body) == 3:
      body = "".join(ch * 2 for ch in body)
    return "#" + body.upper()
  return value


def fix(caption: Dict[str, Any], strip_bbox: bool = False) -> Tuple[Dict[str, Any], List[str]]:
  """Repair mechanical problems. Returns (fixed_caption, list_of_changes)."""
  changes: List[str] = []
  cap = dict(caption)

  if "aspect_ratio" in cap:
    cap.pop("aspect_ratio")
    changes.append("removed top-level 'aspect_ratio' (pass it as a request parameter instead)")

  sd = cap.get("style_description")
  if isinstance(sd, dict):
    if "color_palette" in sd and isinstance(sd["color_palette"], list):
      new = [_fix_hex(c) for c in sd["color_palette"]]
      if new != sd["color_palette"]:
        changes.append("style_description.color_palette: normalized hex to uppercase #RRGGBB")
      sd = dict(sd, color_palette=new)
    if "medium" in sd and isinstance(sd["medium"], str):
      # photo captions must use 'photo'; if only art_style is missing and medium is photograph, leave for the model author
      pass
    order = _style_order_for(sd)
    if order is not None:
      reordered = _ordered(sd, order)
      if list(reordered) != list(sd):
        changes.append("style_description: reordered keys to canonical order")
      sd = reordered
    cap["style_description"] = sd

  cd = cap.get("compositional_deconstruction")
  if isinstance(cd, dict):
    reordered_cd = _ordered(cd, CD_ORDER)
    if list(reordered_cd) != list(cd):
      changes.append("compositional_deconstruction: moved 'background' before 'elements'")
    cd = reordered_cd
    elements = cd.get("elements")
    if isinstance(elements, list):
      new_elems = []
      for i, e in enumerate(elements):
        if isinstance(e, dict):
          e = dict(e)
          if strip_bbox and "bbox" in e:
            e.pop("bbox")
            changes.append(f"elements[{i}]: stripped bbox")
          if "bbox" in e and isinstance(e["bbox"], list):
            nb = []
            for v in e["bbox"]:
              if isinstance(v, float) and v.is_integer():
                nb.append(int(v))
              else:
                nb.append(v)
            if nb != e["bbox"]:
              changes.append(f"elements[{i}].bbox: converted integral floats to int")
            e["bbox"] = nb
          if "color_palette" in e and isinstance(e["color_palette"], list):
            new = [_fix_hex(c) for c in e["color_palette"]]
            if new != e["color_palette"]:
              changes.append(f"elements[{i}].color_palette: normalized hex")
            e["color_palette"] = new
          order = _element_order_for(e)
          if order is not None:
            re_e = _ordered(e, order)
            if list(re_e) != list(e):
              changes.append(f"elements[{i}]: reordered keys to canonical order")
            e = re_e
        new_elems.append(e)
      cd["elements"] = new_elems
    cap["compositional_deconstruction"] = cd

  top = _ordered(cap, TOP_LEVEL_ORDER)
  if list(top) != list(cap):
    changes.append("root: reordered top-level keys")
  return top, changes


def minify(caption: Any) -> str:
  return json.dumps(caption, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Plain-text prompt lint (magic prompt ON mode)
# --------------------------------------------------------------------------- #

PLAIN_WORD_SOFT, PLAIN_WORD_HARD = 150, 160  # docs.ideogram.ai: ~150-160 words / ~200 tokens
VAGUE_ADJECTIVES = ("beautiful", "interesting", "nice", "artistic", "amazing", "awesome", "pretty", "gorgeous", "stunning")
HEX_IN_PROSE_RE = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
WEIGHT_SYNTAX_RE = re.compile(r"(::\d|\(\w+:\d|--ar\b|--v\b|--style\b|--no\b)")
QUOTED_RE = re.compile(r"[\"\u201c\u201d]([^\"\u201c\u201d]{1,200})[\"\u201c\u201d]")
TEXT_CUE_RE = re.compile(r"\b(reads|says|saying|text|lettering|headline|title|slogan|caption|label|sign)\b", re.IGNORECASE)


def lint_plain(text: str) -> Tuple[List[str], List[str]]:
  """Return (issues, hints) for a plain-text prompt."""
  issues: List[str] = []
  hints: List[str] = []
  text = text.strip()
  if text.startswith("{") or text.startswith("```"):
    issues.append("this looks like JSON or a fenced block; run without --plain to validate a caption")
    return issues, hints
  words = text.split()
  n = len(words)
  if n > PLAIN_WORD_HARD:
    issues.append(f"{n} words; Ideogram reads roughly the first {PLAIN_WORD_SOFT}-{PLAIN_WORD_HARD}, the rest may be ignored")
  elif n > PLAIN_WORD_SOFT:
    hints.append(f"{n} words; you are at the ceiling, trim or lead with what matters most")
  if n < 6:
    hints.append(f"only {n} words; fine for exploration, but magic prompt will invent everything else")
  if HEX_IN_PROSE_RE.search(text):
    issues.append("hex color codes do nothing in plain text; describe colors in words or switch to JSON mode")
  if WEIGHT_SYNTAX_RE.search(text):
    issues.append("weight or flag syntax (::1, --ar, --style) is not supported; write natural sentences")
  if NEGATION_RE.search(text):
    hints.append("negation ('no', 'without') is read as a keyword; describe the positive opposite")
  low = text.lower()
  hedges = [h for h in HEDGE_PHRASES if h in low]
  if hedges:
    hints.append(f"hedge wording {hedges}; commit to one value")
  vague = [w for w in VAGUE_ADJECTIVES if re.search(rf"\b{w}\b", low)]
  if vague:
    hints.append(f"vague adjectives {vague}; replace with concrete visual detail or a named style")
  quotes = [m for m in QUOTED_RE.finditer(text)]
  if quotes:
    first_pos = len(text[: quotes[0].start()].split())
    if n and first_pos / n > 0.4:
      hints.append("the first quoted text appears late; mention rendered text near the start of the prompt")
    for m in quotes:
      if len(m.group(1).split()) > 8:
        hints.append(f"quoted text '{m.group(1)[:40]}...' is long; short phrases render more reliably, split into chunks")
  elif TEXT_CUE_RE.search(text):
    hints.append("the prompt mentions text or a sign but nothing is in double quotes; quote the exact wording")
  if not re.search(r"\b(photo|photograph|illustration|painting|render|3d|logo|poster|design|watercolor|oil|ink|vector|sketch|drawing|graphic|cartoon|anime|pixel|collage|print)\w*", low):
    hints.append("no medium or style word found; name one (photograph, watercolor, flat vector illustration, ...)")
  if re.search(r"\b(no|without|never|don't|do not)\b", low) is None and re.search(r"\bnot\b", low):
    hints.append("contains 'not'; check it is not a negation the model will read as a keyword")
  return issues, hints


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _load(path: str) -> Tuple[str, Any]:
  raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
  text = raw.strip()
  # tolerate a ```json fence pasted from chat
  if text.startswith("```"):
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
      lines = lines[1:]
    if lines and lines[-1].strip() == "```":
      lines = lines[:-1]
    text = "\n".join(lines).strip()
  return raw, json.loads(text)


def main(argv: Optional[Sequence[str]] = None) -> int:
  p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  p.add_argument("path", help="caption JSON file (or plain prompt with --plain), or '-' for stdin")
  p.add_argument("--plain", action="store_true", help="lint a plain-text prompt for magic-prompt mode instead of validating JSON")
  p.add_argument("--fix", action="store_true", help="repair key order, hex case, stray keys, integral bbox floats")
  p.add_argument("--strip-bbox", action="store_true", help="remove every bbox (implies --fix)")
  p.add_argument("--minify", action="store_true", help="print the single-line minified caption")
  p.add_argument("--pretty", action="store_true", help="print the caption pretty-printed")
  p.add_argument("-o", "--output", help="write the (fixed) caption to this file")
  p.add_argument("--quiet", action="store_true", help="only print the caption / final status")
  p.add_argument("--no-hints", action="store_true", help="skip advisory hints")
  args = p.parse_args(argv)

  if args.plain:
    try:
      text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    except OSError as exc:
      print(f"input error: {exc}", file=sys.stderr)
      return 2
    issues, advisory = lint_plain(text)
    if issues:
      print("issues:")
      for w in issues:
        print(f"  - {w}")
    if advisory and not args.no_hints:
      print("hints (advisory):")
      for h in advisory:
        print(f"  - {h}")
    if not issues:
      print(f"OK: plain prompt, {len(text.split())} words")
    return 1 if issues else 0

  try:
    raw, caption = _load(args.path)
  except (OSError, json.JSONDecodeError) as exc:
    print(f"input error: {exc}", file=sys.stderr)
    return 2

  issues = check_ensure_ascii_false(raw) + verify(caption)
  changes: List[str] = []
  if args.fix or args.strip_bbox:
    if isinstance(caption, dict):
      caption, changes = fix(caption, strip_bbox=args.strip_bbox)
      issues = verify(caption)  # re-verify; escapes are gone once we re-serialize
    else:
      issues = verify(caption)

  minified = minify(caption)
  advisory = [] if args.no_hints else hints(caption, minified)

  err = sys.stderr if (args.minify or args.pretty) else sys.stdout
  if not args.quiet:
    if changes:
      print("fixed:", file=err)
      for c in changes:
        print(f"  - {c}", file=err)
    if issues:
      print("schema issues:", file=err)
      for w in issues:
        print(f"  - {w}", file=err)
    if advisory:
      print("hints (advisory):", file=err)
      for h in advisory:
        print(f"  - {h}", file=err)
    if not issues:
      print(f"OK: caption passes CaptionVerifier checks ({len(minified)} chars minified)", file=err)

  if args.output:
    with open(args.output, "w", encoding="utf-8") as fh:
      fh.write(json.dumps(caption, indent=2, ensure_ascii=False) + "\n")
  if args.minify:
    print(minified)
  if args.pretty:
    print(json.dumps(caption, indent=2, ensure_ascii=False))
  return 1 if issues else 0


if __name__ == "__main__":
  sys.exit(main())
