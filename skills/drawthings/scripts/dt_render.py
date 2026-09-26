#!/usr/bin/env python3
"""Render prompts through a Draw Things API server (gRPC), one job per seed.

Built on the drawthings-py SDK (PyPI, GPL-3.0). The one thing added on top is the
`override.models` model spec that cloud-only models need when the app forwards jobs
to Draw Things+ cloud compute through Bridge Mode.

Examples:
  dt_render.py --check
  dt_render.py --list-recipes
  dt_render.py --recipe krea-2-turbo --prompt-file prompt.txt --seeds 4 --out renders/r1
  dt_render.py --recipe ideogram-4 --prompt-file caption.json --size 2048x1344 --seeds 12345 --out renders/r2 --log runs.jsonl
  dt_render.py --spec my-model.json --prompt "a red apple" --out renders/r3
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    """Re-exec under the interpreter that has drawthings-py when this one lacks it."""
    try:
        import drawthings_py  # noqa: F401
        return
    except ImportError:
        pass
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    venv = cache / "drawthings-skill" / "venv"
    candidates = [os.environ.get("DRAWTHINGS_PYTHON"), venv / "bin" / "python", venv / "Scripts" / "python.exe"]
    for cand in candidates:
        if cand and Path(cand).exists() and Path(cand).resolve() != Path(sys.executable).resolve():
            os.execv(str(cand), [str(cand), os.path.abspath(__file__), *sys.argv[1:]])
    sys.exit(
        "drawthings-py is not installed for this interpreter.\n"
        "Run scripts/setup.sh once (it creates ~/.cache/drawthings-skill/venv), "
        "or point DRAWTHINGS_PYTHON at a Python 3.11+ that has drawthings-py."
    )


_bootstrap()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import drawthings_py.grpc.grpc_service as _grpc_service  # noqa: E402
from drawthings_py import Configs, DrawThings, RequestBuilder  # noqa: E402
from drawthings_py.generated.dt_grpc import image_service  # noqa: E402
from drawthings_py.request_builder import build_grpc_message as _sdk_build  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_units  # noqa: E402
import qwen_tokens  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
RECIPES_PATH = SKILL_DIR / "recipes.json"
USER_AGENT = "drawthings-skill"
SAMPLER_NAMES = [
    "DPMPP2MKarras", "EulerA", "DDIM", "PLMS", "DPMPPSDEKarras", "UniPC", "LCM", "EulerASubstep",
    "DPMPPSDESubstep", "TCD", "EulerATrailing", "DPMPPSDETrailing", "DPMPP2MAYS", "EulerAAYS",
    "DPMPPSDEAYS", "DPMPP2MTrailing", "DDIMTrailing", "UniPCTrailing", "UniPCAYS", "TCDTrailing",
]
RETRYABLE = ("unavailable", "deadline", "unknown error processing request", "cancelled", "reset", "timed out")


# --- model spec override -------------------------------------------------------------

def _build_with_override(builder: RequestBuilder):
    """drawthings-py never fills `override`; add the model spec the server does not know."""
    message, callback = _sdk_build(builder)
    spec = getattr(builder, "model_spec", None)
    if spec:
        message.override = image_service.MetadataOverride(models=json.dumps([spec]).encode("utf-8"))
    message.user = USER_AGENT
    message.device = image_service.DeviceType.LAPTOP
    return message, callback


if _grpc_service.build_grpc_message is not _sdk_build:  # pragma: no cover
    sys.exit("drawthings-py changed its request builder; this script needs an update (pin drawthings-py<0.5).")
_grpc_service.build_grpc_message = _build_with_override
_grpc_service.decode_preview = lambda _raw: None  # previews are not needed; the SDK's decoder logs noise on compressed ones


# --- helpers ---------------------------------------------------------------------------

def normalize_sampler(name: str) -> str:
    key = re.sub(r"[\s_\-]+", "", name.lower()).replace("dpm++", "dpmpp")
    for canonical in SAMPLER_NAMES:
        if canonical.lower() == key:
            return canonical
    raise SystemExit(f"Unknown sampler {name!r}. Known: {', '.join(SAMPLER_NAMES)}")


def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", text)
    if not m:
        raise SystemExit(f"--size must look like 2048x1344, got {text!r}")
    w, h = int(m.group(1)), int(m.group(2))
    w64, h64 = max(64, w // 64 * 64), max(64, h // 64 * 64)
    if (w64, h64) != (w, h):
        print(f"note: size {w}x{h} rounded down to multiples of 64: {w64}x{h64}", file=sys.stderr)
    return w64, h64


def parse_seeds(text: str) -> list[int]:
    text = text.strip()
    if re.fullmatch(r"\d+", text) and "," not in text and int(text) <= 64:
        return [random.randint(1, 2**32 - 2) for _ in range(int(text))]
    seeds = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if not re.fullmatch(r"\d+", part):
            raise SystemExit(f"bad seed {part!r}; use a count (4) or a list (12345,777)")
        seeds.append(int(part))
    return seeds


def load_recipes() -> dict:
    if not RECIPES_PATH.exists():
        return {}
    return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))


def read_prompt(path: str | None, inline: str | None) -> tuple[str, str | None]:
    """Return (prompt text, source path). JSON files are validated and minified."""
    if inline is not None:
        return inline.strip(), None
    if not path:
        raise SystemExit("give --prompt-file or --prompt")
    p = Path(path)
    text = p.read_text(encoding="utf-8").strip()
    if p.suffix.lower() == ".json":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{p} is not valid JSON: {e}")
        text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    return text, str(p)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_retryable(message: str) -> bool:
    low = message.lower()
    return any(k in low for k in RETRYABLE)


# --- contact sheet ---------------------------------------------------------------------

def contact_sheet(entries: list[dict], out_path: Path, thumb: int) -> Path | None:
    from PIL import Image, ImageDraw, ImageFont

    ok = [e for e in entries if e["status"] == "ok"]
    if len(ok) < 2:
        return None
    cols = math.ceil(math.sqrt(len(ok)))
    rows = math.ceil(len(ok) / cols)
    pad, label_h = 12, 28
    thumbs = []
    for e in ok:
        im = Image.open(e["file"]).convert("RGB")
        im.thumbnail((thumb, thumb))
        thumbs.append((e, im))
    cell_w = max(im.width for _, im in thumbs) + pad
    cell_h = max(im.height for _, im in thumbs) + pad + label_h
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    for i, (e, im) in enumerate(thumbs):
        x = pad + (i % cols) * cell_w
        y = pad + (i // cols) * cell_h
        sheet.paste(im, (x, y))
        draw.text((x, y + im.height + 4), f"seed {e['seed']}  {e['seconds']:.0f}s", fill=(230, 230, 230), font=font)
    sheet.save(out_path, quality=88)
    return out_path


# --- generation ------------------------------------------------------------------------

async def render_all(args, spec: dict, settings: dict, prompt: str, negative: str, seeds: list[int],
                     out_dir: Path, name: str) -> list[dict]:
    entries: list[dict] = []
    async with DrawThings.grpc(host=args.host, port=args.port, progressbar=False, disable_messages=True) as service:
        for seed in seeds:
            entry = await render_one(service, args, spec, settings, prompt, negative, seed, out_dir, name)
            entries.append(entry)
            print(f"  seed {seed}: {entry['status']}"
                  + (f" in {entry['seconds']:.0f}s (first step at {entry['first_step_seconds']}s) -> {entry['file']}"
                     if entry["status"] == "ok" else f": {entry['error']}"))
    return entries


async def render_one(service, args, spec, settings, prompt, negative, seed, out_dir: Path, name: str) -> dict:
    config = Configs.create(
        model=spec["file"], width=settings["width"], height=settings["height"], steps=settings["steps"],
        guidance=settings["cfg"], shift=settings["shift"], sampler=settings["sampler"], seed=seed,
        seed_mode="ScaleAlike", strength=1.0, batch_count=1, batch_size=1,
        resolution_dependent_shift=settings["resolution_dependent_shift"], tiled_decoding=settings["tiled_decode"],
        zero_negative_prompt=settings["zero_negative"],
    )
    if settings.get("loras"):
        config["loras"] = [{"file": f, "weight": w} for f, w in settings["loras"]]
    rb = RequestBuilder(config, prompt, negative or None)
    rb.model_spec = spec  # picked up by _build_with_override
    t0 = time.monotonic()
    first_step: dict = {}

    def on_progress(signpost, _preview):
        if signpost is not None and signpost.is_set("sampling") and "t" not in first_step:
            first_step["t"] = round(time.monotonic() - t0, 1)

    if hasattr(rb, "on_progress"):
        rb.on_progress(on_progress)
    else:
        rb._on_progress = on_progress  # noqa: SLF001

    file = out_dir / f"{name}-s{seed}.png"
    attempts = args.retries + 1
    error = ""
    for attempt in range(1, attempts + 1):
        t0 = time.monotonic()
        first_step.clear()
        try:
            result = await asyncio.wait_for(service.generate(rb), timeout=args.timeout)
            result[-1].to_file(file)
            return {"seed": seed, "status": "ok", "seconds": round(time.monotonic() - t0, 1),
                    "first_step_seconds": first_step.get("t"), "file": str(file), "attempts": attempt, "error": None}
        except asyncio.TimeoutError:
            error = f"timed out after {args.timeout}s"
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {str(e)[:300]}"
        elapsed = time.monotonic() - t0
        # The cloud behind Bridge Mode often aborts for no reason before the first sampling
        # step; such failures are retried whatever the message says.
        before_sampling = "t" not in first_step
        if attempt < attempts and (before_sampling or is_retryable(error)):
            print(f"  seed {seed}: attempt {attempt} failed after {elapsed:.0f}s ({error}); retrying in {args.retry_wait:.0f}s")
            await asyncio.sleep(args.retry_wait)
            continue
        break
    return {"seed": seed, "status": "error", "seconds": round(time.monotonic() - t0, 1),
            "first_step_seconds": first_step.get("t"), "file": None, "attempts": attempts, "error": error}


async def check(args, recipes: dict) -> int:
    async with DrawThings.grpc(host=args.host, port=args.port, progressbar=False, disable_messages=True) as service:
        info = await service.get_models()
        print(f"Draw Things API server at {args.host}:{args.port}: reachable (TLS ok)")
        print(f"  local models: {len(info.models)}, LoRAs: {len(info.loras)}, files: {len(info.files)}")
        for m in info.models:
            print(f"    {m.get('name')}  ({m.get('file')}, {m.get('version')})")
        if info.loras:
            print("  LoRA files: " + ", ".join(sorted(l.get("file", "?") for l in info.loras)))
        local = set(info.files)
        for key, recipe in recipes.items():
            f = recipe["spec"]["file"]
            where = "local" if f in local else "not local: needs Bridge Mode + Draw Things+ cloud"
            print(f"  recipe {key}: {f} -> {where}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # live lines when the run is backgrounded and polled
        try:
            stream.reconfigure(line_buffering=True)
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipe", help="name from recipes.json")
    ap.add_argument("--spec", help="JSON file with a Draw Things model spec (and optional 'defaults')")
    ap.add_argument("--prompt-file", help="prompt text file, or a .json caption (minified before sending)")
    ap.add_argument("--prompt", help="inline prompt (instead of --prompt-file)")
    ap.add_argument("--negative-file"); ap.add_argument("--negative", default=None)
    ap.add_argument("--size", help="WxH in pixels, multiples of 64 (default: recipe default)")
    ap.add_argument("--seeds", default="1", help="a count (4 random seeds) or a list (12345,777)")
    ap.add_argument("--steps", type=int); ap.add_argument("--cfg", type=float); ap.add_argument("--shift", type=float)
    ap.add_argument("--sampler"); ap.add_argument("--resolution-dependent-shift", action="store_true")
    ap.add_argument("--tiled-decode", action="store_true")
    ap.add_argument("--zero-negative", dest="zero_negative", action="store_true", default=None,
                    help="zero negative prompt: the model's own unconditional branch under CFG (Ideogram 4 needs it)")
    ap.add_argument("--no-zero-negative", dest="zero_negative", action="store_false")
    ap.add_argument("--lora", action="append", default=[], metavar="FILE:WEIGHT", help="local LoRA file and weight (repeatable)")
    ap.add_argument("--out", help="directory for the PNGs, run.json and the contact sheet")
    ap.add_argument("--name", help="base name for files (default: prompt file stem or 'render')")
    ap.add_argument("--log", help="append one JSON line per image to this runs.jsonl")
    ap.add_argument("--note", default="", help="free text stored with the run (what changed this round)")
    ap.add_argument("--no-sheet", action="store_true"); ap.add_argument("--thumb", type=int, default=512)
    ap.add_argument("--retries", type=int, default=3, help="extra attempts per image (default 3; the cloud aborts jobs at random)"); ap.add_argument("--retry-wait", type=float, default=20)
    ap.add_argument("--timeout", type=float, default=900, help="seconds per image")
    ap.add_argument("--host", default=os.environ.get("DRAWTHINGS_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DRAWTHINGS_PORT", "7859")))
    ap.add_argument("--tier", choices=["plus", "community"], default=os.environ.get("DRAWTHINGS_TIER", "plus"),
                    help="cloud tier for the compute-unit limit (default plus, 40,000 per image)")
    ap.add_argument("--force", action="store_true", help="send even when the estimate exceeds the tier limit")
    ap.add_argument("--estimate-only", action="store_true", help="print the compute-unit estimate and exit")
    ap.add_argument("--check", action="store_true", help="connect, list local models, say which recipes need the cloud")
    ap.add_argument("--list-recipes", action="store_true")
    ap.add_argument("--json", action="store_true", help="print a JSON summary at the end")
    args = ap.parse_args()

    recipes = load_recipes()
    if args.list_recipes:
        for key, r in recipes.items():
            d = r.get("defaults", {})
            print(f"{key}: {r.get('title', '')}\n    model {r['spec']['file']}  steps {d.get('steps')}  cfg {d.get('cfg')}  "
                  f"shift {d.get('shift')}  sampler {d.get('sampler')}  size {d.get('size')}\n    {r.get('notes', '')}")
        return 0
    if args.check:
        return asyncio.run(check(args, recipes))

    # resolve spec and defaults
    if args.recipe:
        if args.recipe not in recipes:
            raise SystemExit(f"unknown recipe {args.recipe!r}; try --list-recipes")
        recipe = recipes[args.recipe]
    elif args.spec:
        recipe = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        if "spec" not in recipe:  # a bare spec file
            recipe = {"spec": recipe, "defaults": {}}
    else:
        raise SystemExit("give --recipe NAME or --spec FILE")
    spec = recipe["spec"]
    d = recipe.get("defaults", {})
    width, height = parse_size(args.size or d.get("size") or "1024x1024")
    settings = {
        "width": width, "height": height,
        "steps": args.steps if args.steps is not None else int(d.get("steps", 20)),
        "cfg": args.cfg if args.cfg is not None else float(d.get("cfg", 1.0)),
        "shift": args.shift if args.shift is not None else float(d.get("shift", 1.0)),
        "sampler": normalize_sampler(args.sampler or d.get("sampler", "EulerATrailing")),
        "resolution_dependent_shift": bool(args.resolution_dependent_shift or d.get("resolution_dependent_shift", False)),
        "tiled_decode": bool(args.tiled_decode or d.get("tiled_decode", False)),
        "zero_negative": bool(d.get("zero_negative_prompt", False) if args.zero_negative is None else args.zero_negative),
        "loras": [],
    }
    for item in args.lora:
        f, _, w = item.partition(":")
        settings["loras"].append((f, float(w or 1.0)))

    prompt, prompt_path = read_prompt(args.prompt_file, args.prompt)
    negative = (Path(args.negative_file).read_text(encoding="utf-8").strip() if args.negative_file else (args.negative or "")).strip()
    seeds = parse_seeds(args.seeds)
    if not args.out and not args.estimate_only:
        raise SystemExit("give --out DIR")
    out_dir = Path(args.out or ".")
    if not args.estimate_only:
        out_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or (Path(prompt_path).stem if prompt_path else "render")
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "render"

    if not args.estimate_only:  # keep the exact prompt with the renders
        (out_dir / ("prompt.json" if prompt_path and prompt_path.endswith(".json") else "prompt.txt")).write_text(prompt + "\n", encoding="utf-8")
        if negative:
            (out_dir / "negative.txt").write_text(negative + "\n", encoding="utf-8")

    tokens, exact = qwen_tokens.count(prompt)
    print(f"{spec['file']} {width}x{height} steps {settings['steps']} cfg {settings['cfg']} shift {settings['shift']} "
          f"{settings['sampler']} | {len(prompt.split())} words, {tokens} tokens ({'exact' if exact else 'estimate'}) | seeds {seeds}")
    max_tokens = recipe.get("prompt_max_tokens")
    if max_tokens and tokens > max_tokens:
        print(f"prompt is {tokens} tokens; this recipe's limit is {max_tokens} ({recipe.get('prompt_max_tokens_note', '')})",
              file=sys.stderr)
        if not args.force and not args.estimate_only:
            print("shorten the prompt, or pass --force to send anyway", file=sys.stderr)
            return 4
    units = compute_units.estimate(spec.get("version", ""), width, height, settings["steps"], settings["cfg"],
                                   text_length=spec.get("padded_text_encoding_length"))
    limit = compute_units.THRESHOLDS[args.tier]
    if units is None:
        print(f"compute units: no estimate for version {spec.get('version')!r} (limit {limit:,} per image on {args.tier})")
    else:
        verdict = "ok" if units <= limit else f"OVER the {args.tier} limit, the cloud will refuse it"
        print(f"compute units: about {units:,} per image, limit {limit:,} ({verdict})")
        if units > limit and not args.force and not args.estimate_only:
            print("lower the size or the steps, or pass --force to send anyway", file=sys.stderr)
            return 3
    if args.estimate_only:
        return 0 if units is None or units <= limit else 1
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entries = asyncio.run(render_all(args, spec, settings, prompt, negative, seeds, out_dir, name))

    sheet = None if args.no_sheet else contact_sheet(entries, out_dir / f"{name}-sheet.jpg", args.thumb)
    run = {
        "started": started, "run_dir": str(out_dir), "name": name, "recipe": args.recipe, "model": spec["file"], "spec": spec,
        "prompt_file": prompt_path, "prompt_sha256": sha256(prompt), "prompt_words": len(prompt.split()), "prompt_chars": len(prompt),
        "prompt_tokens": tokens, "prompt_tokens_exact": exact,
        "prompt": prompt, "negative": negative, "settings": {k: v for k, v in settings.items() if k != "loras"},
        "loras": settings["loras"], "note": args.note, "host": f"{args.host}:{args.port}", "compute_units": units, "images": entries,
        "sheet": str(sheet) if sheet else None,
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.log:
        log_path = Path(args.log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for e in entries:
                line = {"ts": started, "run_dir": str(out_dir), "name": name, "recipe": args.recipe, "model": spec["file"],
                        "prompt_file": prompt_path, "prompt_sha256": run["prompt_sha256"], "prompt_words": run["prompt_words"], "prompt_tokens": tokens,
                        "width": width, "height": height, "steps": settings["steps"], "cfg": settings["cfg"], "shift": settings["shift"],
                        "sampler": settings["sampler"], "rds": settings["resolution_dependent_shift"], "zero_negative": settings["zero_negative"], "loras": settings["loras"],
                        "compute_units": units, "seed": e["seed"], "status": e["status"], "seconds": e["seconds"], "first_step_seconds": e["first_step_seconds"],
                        "file": e["file"], "error": e["error"], "note": args.note}
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    ok = [e for e in entries if e["status"] == "ok"]
    print(f"\n{len(ok)}/{len(entries)} images in {out_dir}")
    if sheet:
        print(f"contact sheet: {sheet}")
    elif ok:
        print(f"image: {ok[0]['file']}")
    if args.json:
        print(json.dumps(run, ensure_ascii=False))
    return 0 if len(ok) == len(entries) else 1


if __name__ == "__main__":
    sys.exit(main())
