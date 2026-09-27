#!/usr/bin/env python3
"""Print the settings and prompt stored in a Draw Things PNG, and the command that reproduces it.

Works on PNGs exported by the Draw Things app and on PNGs written by dt_render.py: both carry
an XMP block whose exif:UserComment holds the generation configuration as JSON.

    python3 png_config.py image.png                 # settings, prompt head, reproduce command
    python3 png_config.py image.png --prompt-out caption.json
    python3 png_config.py image.png --config-out image.config.json
    python3 png_config.py image.png --json          # the whole configuration as JSON
"""
import argparse
import html
import json
import re
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECIPES = HERE.parent / "recipes.json"


def text_chunks(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"tEXt":
            key, _, value = body.partition(b"\x00")
            yield key.decode("latin1"), value.decode("latin1", "replace")
        elif ctype == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            yield key.decode("latin1"), zlib.decompress(rest[1:]).decode("latin1", "replace")
        elif ctype == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            compressed = rest[0]
            rest = rest[2:]
            _lang, _, rest = rest.partition(b"\x00")
            _translated, _, text = rest.partition(b"\x00")
            if compressed:
                text = zlib.decompress(text)
            yield key.decode("latin1"), text.decode("utf-8", "replace")


def read_config(path: str) -> dict:
    data = Path(path).read_bytes()
    if not data.startswith(b"\x89PNG"):
        sys.exit(f"{path}: not a PNG")
    for _key, text in text_chunks(data):
        m = re.search(r"<exif:UserComment>\s*<rdf:Alt>\s*<rdf:li[^>]*>(.*?)</rdf:li>", text, re.S)
        if not m:
            continue
        try:
            return json.loads(html.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
    sys.exit(f"{path}: no Draw Things configuration found in the PNG metadata")


def count_tokens(prompt: str):
    try:
        sys.path.insert(0, str(HERE))
        import qwen_tokens  # noqa: E402
        return qwen_tokens.count(prompt)
    except Exception:
        return None


def recipe_for(model_file: str):
    try:
        recipes = json.loads(RECIPES.read_text())
    except Exception:
        return None
    for name, recipe in recipes.items():
        if recipe.get("spec", {}).get("file") == model_file:
            return name
    return None


def configuration_block(cfg: dict) -> dict:
    """Return the app's pasteable Copy Configuration block from PNG metadata."""
    if isinstance(cfg.get("v2"), dict):
        return cfg["v2"]
    # Older PNGs may only carry the compact, human-readable metadata.
    sampler = cfg.get("sampler")
    sampler_names = [
        "DPM++ 2M Karras", "Euler A", "DDIM", "PLMS", "DPM++ SDE Karras", "UniPC", "LCM",
        "Euler A Substep", "DPM++ SDE Substep", "TCD", "Euler A Trailing", "DPM++ SDE Trailing",
        "DPM++ 2M AYS", "Euler A AYS", "DPM++ SDE AYS", "DPM++ 2M Trailing", "DDIM Trailing",
        "UniPC Trailing", "UniPC AYS", "TCD Trailing",
    ]
    try:
        sampler = sampler_names.index(sampler)
    except ValueError:
        pass
    width, height = (cfg.get("size") or "1024x1024").split("x", 1)
    return {
        "model": cfg.get("model"), "width": int(width), "height": int(height),
        "seed": cfg.get("seed"), "steps": cfg.get("steps"), "guidanceScale": cfg.get("scale"),
        "strength": cfg.get("strength", 1), "sampler": sampler, "shift": cfg.get("shift"),
    }


def write_config_recipe(path: str, image: str, cfg: dict) -> None:
    model = cfg.get("model") or cfg.get("v2", {}).get("model")
    document = {
        "name": recipe_for(model) or Path(image).stem,
        "prompt": cfg.get("c", "") or "",
        "negative": cfg.get("uc", "") or "",
        "configuration": configuration_block(cfg),
    }
    Path(path).write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--prompt-out", help="write the prompt exactly as sent to this file")
    ap.add_argument("--config-out", help="write a reusable recipe with prompt, negative and Copy Configuration JSON")
    ap.add_argument("--json", action="store_true", help="print the whole configuration as JSON and exit")
    args = ap.parse_args()

    cfg = read_config(args.image)
    if args.config_out:
        write_config_recipe(args.config_out, args.image, cfg)
        print(f"config written:  {args.config_out}")
    if args.json:
        print(json.dumps(cfg, indent=1, ensure_ascii=False))
        return

    v2 = cfg.get("v2", {})
    prompt = cfg.get("c", "") or ""
    negative = cfg.get("uc", "") or ""
    model = cfg.get("model") or v2.get("model")
    size = cfg.get("size") or f"{v2.get('width')}x{v2.get('height')}"
    steps = cfg.get("steps", v2.get("steps"))
    scale = cfg.get("scale", v2.get("guidanceScale"))
    shift = cfg.get("shift", v2.get("shift"))
    sampler = cfg.get("sampler")
    seed = cfg.get("seed", v2.get("seed"))
    zero_negative = v2.get("zeroNegativePrompt")
    rds = v2.get("resolutionDependentShift")
    tiled = v2.get("tiledDecoding")
    tiled_diffusion = v2.get("tiledDiffusion")
    loras = v2.get("loras") or []
    expand = cfg.get("expand_prompt_to_json", v2.get("expandPromptToJson"))
    profile = cfg.get("profile") or {}

    print(f"file:            {args.image}")
    print(f"model:           {model}")
    print(f"size:            {size}")
    print(f"steps:           {steps}")
    print(f"guidance (cfg):  {scale}")
    print(f"shift:           {shift:.4g}" if isinstance(shift, (int, float)) else f"shift:           {shift}")
    print(f"sampler:         {sampler}")
    print(f"seed:            {seed}  ({cfg.get('seed_mode', v2.get('seedMode'))})")
    print(f"strength:        {cfg.get('strength', v2.get('strength'))}")
    print(f"zero negative:   {zero_negative}")
    print(f"res.-dep. shift: {rds}")
    print(f"tiled decoding:  {tiled}")
    print(f"tiled diffusion: {tiled_diffusion}")
    if expand is not None:
        print(f"expand to JSON:  {expand}")
    if loras:
        print("loras:           " + ", ".join(f"{l.get('file')}:{l.get('weight')}" for l in loras))
    print(f"negative prompt: {negative!r}")
    if profile.get("duration"):
        stages = {t["name"]: round(sum(t["durations"]), 1) for t in profile.get("timings", [])}
        print(f"app profile:     {profile['duration']:.1f} s total, {stages}")
    counted = count_tokens(prompt)
    tokens = f", {counted[0]} Qwen tokens ({'exact' if counted[1] else 'estimate'})" if counted else ""
    print(f"prompt:          {len(prompt)} chars, {len(prompt.split())} words{tokens}")
    print("prompt head:     " + prompt[:160].replace("\n", " ") + ("..." if len(prompt) > 160 else ""))

    is_json = prompt.lstrip().startswith("{")
    is_seedvr2 = isinstance(model, str) and model.startswith("seedvr2_")
    if args.prompt_out:
        Path(args.prompt_out).write_text(prompt)
        print(f"prompt written:  {args.prompt_out}")
        prompt_arg = args.prompt_out
    else:
        prompt_arg = "PROMPT.json" if is_json else "PROMPT.txt"
        if prompt:
            print(f"(pass --prompt-out {prompt_arg} to save the prompt for the command below)")
    if is_seedvr2:
        print("source image:    not embedded in PNG metadata; supply the original as --init-image")

    recipe = recipe_for(model)
    cmd = ["python3", str(HERE / "dt_render.py")]
    if args.config_out:
        cmd += ["--config", args.config_out]
        if is_seedvr2:
            cmd += ["--init-image", "ORIGINAL.png"]
        cmd += ["--out", "renders/repro"]
        print()
        print("reproduce with:")
        print("  " + " ".join(cmd))
        return
    cmd += ["--recipe", recipe] if recipe else ["--spec", "SPEC.json"]
    if prompt or not is_seedvr2:
        cmd += ["--prompt-file", prompt_arg]
    if is_seedvr2:
        cmd += ["--init-image", "ORIGINAL.png"]
    cmd += ["--size", str(size), "--steps", str(steps), "--cfg", f"{scale:g}" if isinstance(scale, (int, float)) else str(scale)]
    if isinstance(shift, (int, float)):
        cmd += ["--shift", f"{shift:.4g}"]
    if sampler:
        cmd += ["--sampler", f'"{sampler}"']
    if zero_negative is not None:
        cmd.append("--zero-negative" if zero_negative else "--no-zero-negative")
    if rds:
        cmd.append("--resolution-dependent-shift")
    if tiled:
        cmd.append("--tiled-decode")
    if tiled_diffusion:
        cmd.append("--tiled-diffusion")
    for lora in loras:
        cmd += ["--lora", f"{lora.get('file')}:{lora.get('weight')}"]
    if negative:
        cmd += ["--negative-file", "NEGATIVE.txt"]
    cmd += ["--seeds", str(seed), "--out", "renders/repro"]
    print()
    if not recipe:
        print(f"# no recipe carries {model}; derive a spec first (references/server.md) and save it as SPEC.json")
    if negative:
        print("# save the negative prompt shown above as NEGATIVE.txt")
    print("reproduce with:")
    print("  " + " ".join(cmd))


if __name__ == "__main__":
    main()
