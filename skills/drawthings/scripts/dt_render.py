#!/usr/bin/env python3
"""Render prompts through a Draw Things API server (gRPC), one job per seed.

Built on the drawthings-py SDK (PyPI, GPL-3.0). The one thing added on top is the
`override.models` model spec that cloud-only models need when the app forwards jobs
to Draw Things+ cloud compute through Bridge Mode.

Examples:
  dt_render.py --check
  dt_render.py --list-recipes
  dt_render.py --recipe krea-2-turbo --prompt-file prompt.txt --count 4 --out renders/r1
  dt_render.py --recipe ideogram-4 --prompt-file caption.json --size 2048x1344 --seeds 12345 --out renders/r2 --log runs.jsonl
  dt_render.py --spec my-model.json --prompt "a red apple" --out renders/r3
  dt_render.py --config image.config.json --out renders/repro
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
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import signal  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import drawthings_py.grpc.grpc_service as _grpc_service  # noqa: E402
from drawthings_py import Configs, DrawThings, ImageBuffer, RequestBuilder  # noqa: E402
from drawthings_py.configs.config_prop import load_props  # noqa: E402
from drawthings_py.configs.enums import sampler_type_to_int, seed_mode_to_int  # noqa: E402
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
    """--seeds is always literal seeds (12345 or 12345,777); random seeds come from --count."""
    seeds = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if not re.fullmatch(r"\d+", part):
            raise SystemExit(f"bad seed {part!r}; --seeds takes seeds (12345,777), --count N draws random ones")
        seeds.append(int(part))
    return seeds


def load_recipes() -> dict:
    if not RECIPES_PATH.exists():
        return {}
    return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def config_dict_from_app(data: dict) -> dict:
    """Map Copy Configuration JSON to the SDK without dropping false or zero.

    drawthings-py 0.4's public ``from_json`` uses a truthiness test, so values such as
    ``resolutionDependentShift: false`` disappear and fall back to SDK defaults.  Use the
    same property table one property at a time and keep every value except ``None``.  A few
    scripting-schema names are camelCase even where the SDK table only lists snake_case, so
    offer that alias too.
    """
    result = {}
    for prop in load_props().values():
        value = prop.from_json(data)
        if value is None:
            alias = _camel(prop.name)
            if alias in data:
                value = prop.from_json({prop.name: data[alias]})
        if value is not None:
            result[prop.name] = value
    return result


def load_config_recipe(path: str) -> dict:
    """Read bare Copy Configuration JSON, an app preset, or this skill's recipe format."""
    source = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        document = json.loads(source)
    except json.JSONDecodeError as e:
        where = "stdin" if path == "-" else path
        raise SystemExit(f"{where} is not valid JSON: {e}")
    if not isinstance(document, dict):
        raise SystemExit("--config JSON must be an object")
    if "configuration" in document:
        raw = document["configuration"]
        if not isinstance(raw, dict):
            raise SystemExit("--config field 'configuration' must be an object")
        prompt = document.get("prompt")
        negative = document.get("negative")
        name = document.get("name")
        init_image = document.get("init_image")
        init_fit = document.get("init_fit", "fill")
    else:
        raw, prompt, negative, name, init_image, init_fit = document, None, None, None, None, "fill"
    if prompt is not None and not isinstance(prompt, str):
        raise SystemExit("--config field 'prompt' must be a string")
    if negative is not None and not isinstance(negative, str):
        raise SystemExit("--config field 'negative' must be a string")
    if init_image is not None and not isinstance(init_image, str):
        raise SystemExit("--config field 'init_image' must be a string")
    if init_fit not in ("fill", "stretch"):
        raise SystemExit("--config field 'init_fit' must be 'fill' or 'stretch'")
    if init_image and path != "-" and not Path(init_image).is_absolute():
        init_image = str(Path(path).resolve().parent / init_image)
    return {
        "path": None if path == "-" else path,
        "name": name if isinstance(name, str) else None,
        "prompt": prompt,
        "negative": negative,
        "init_image": init_image,
        "init_fit": init_fit,
        "raw": raw,
        "sdk": config_dict_from_app(raw),
    }


def recipe_for_model(recipes: dict, model: str) -> tuple[str, dict] | None:
    for key, recipe in recipes.items():
        if recipe.get("spec", {}).get("file") == model:
            return key, recipe
    return None


def app_configuration(raw: dict, config: dict, seed: int) -> dict:
    """Return pasteable app JSON, preserving source-only fields and applying actual settings."""
    out = copy.deepcopy(raw)
    # These are the generation values this renderer can intentionally select or override.
    values = {
        "model": config.get("model"),
        "width": config.get("width"),
        "height": config.get("height"),
        "seed": seed,
        "steps": config.get("steps"),
        "guidanceScale": config.get("guidance"),
        "strength": config.get("strength"),
        "sampler": sampler_type_to_int(config.get("sampler")),
        "shift": config.get("shift"),
        "resolutionDependentShift": config.get("resolution_dependent_shift"),
        "batchCount": config.get("batch_count"),
        "batchSize": config.get("batch_size"),
        "seedMode": seed_mode_to_int(config.get("seed_mode")),
        "tiledDecoding": config.get("tiled_decoding"),
        "tiledDiffusion": config.get("tiled_diffusion"),
        "decodingTileWidth": config.get("decoding_tile_width"),
        "decodingTileHeight": config.get("decoding_tile_height"),
        "decodingTileOverlap": config.get("decoding_tile_overlap"),
        "diffusionTileWidth": config.get("diffusion_tile_width"),
        "diffusionTileHeight": config.get("diffusion_tile_height"),
        "diffusionTileOverlap": config.get("diffusion_tile_overlap"),
        "zeroNegativePrompt": config.get("zero_negative_prompt"),
        "loras": config.get("loras"),
        "controls": config.get("controls"),
    }
    for key, value in values.items():
        if value is not None:
            out[key] = value
    return out


def write_config_recipe(path: Path, name: str, prompt: str, negative: str,
                        raw: dict, config: dict, seed: int, init_image: str | None = None,
                        init_fit: str = "fill") -> None:
    document = {
        "name": name,
        "prompt": prompt,
        "negative": negative,
        "configuration": app_configuration(raw, config, seed),
    }
    if init_image:
        document["init_image"] = init_image
        document["init_fit"] = init_fit
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_image_size(path: str) -> tuple[int, int]:
    """Read the display-oriented dimensions of an init image."""
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as im:
            return ImageOps.exif_transpose(im).size
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"cannot read --init-image {path!r}: {type(e).__name__}: {e}") from e


def prepare_init_image(path: str, width: int, height: int, fit: str) -> tuple[ImageBuffer, dict]:
    """Build the exact RGB canvas sent to Draw Things.

    ``fill`` preserves aspect ratio, covers the whole canvas, and center-crops the excess.
    Preparing the target-sized canvas here also bypasses drawthings-py's unconditional resize,
    which would otherwise stretch an image whose aspect ratio differs from the output.
    """
    from PIL import Image, ImageOps

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"--init-image not found: {source}")
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            source_width, source_height = image.size
            if fit == "fill":
                scale = max(width / source_width, height / source_height)
                resized_width = max(width, math.ceil(source_width * scale))
                resized_height = max(height, math.ceil(source_height * scale))
                resized = image.resize((resized_width, resized_height), Image.Resampling.BILINEAR)
                left = (resized_width - width) // 2
                top = (resized_height - height) // 2
                canvas = resized.crop((left, top, left + width, top + height))
                crop = [left, top, left + width, top + height]
            else:
                resized_width, resized_height = width, height
                crop = [0, 0, width, height]
                canvas = image.resize((width, height), Image.Resampling.BILINEAR)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"cannot prepare --init-image {source}: {type(e).__name__}: {e}") from e
    metadata = {
        "source": str(source),
        "sha256": sha256_file(source),
        "source_size": [source_width, source_height],
        "canvas_size": [width, height],
        "fit": fit,
        "resized_size": [resized_width, resized_height],
        "crop": crop,
        "prepared_file": "init-image.png",
    }
    return ImageBuffer(canvas.tobytes(), width, height, 3), metadata


def backoff(attempt: int, base: float, cap: float) -> float:
    """Seconds to wait after failed attempt number `attempt`: base, 2x, 4x ... up to cap, with jitter."""
    return min(cap, base * 2 ** (attempt - 1)) * random.uniform(0.85, 1.15)


async def server_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


class StopRun(Exception):
    """Ends the whole run: a stop file, the server gone, or failures that look systematic."""


GLOBAL_STOP = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "drawthings-skill" / "STOP"
RUN_STARTED = time.time()  # stop files older than this run are leftovers and ignored


def check_stop(out_dir: Path) -> None:
    for f in (out_dir / "STOP", GLOBAL_STOP):
        try:
            if f.stat().st_mtime >= RUN_STARTED - 1:
                raise StopRun(f"stop file {f} found")
        except FileNotFoundError:
            pass


async def nap(seconds: float, out_dir: Path) -> None:
    """asyncio.sleep that notices a stop file within a second."""
    end = time.monotonic() + seconds
    while (left := end - time.monotonic()) > 0:
        check_stop(out_dir)
        await asyncio.sleep(min(1.0, left))
    check_stop(out_dir)


async def wait_for_server(host: str, port: int, max_wait: float, out_dir: Path) -> None:
    """Wait briefly for the API server (a Bridge Mode hiccup, the app restarting); stop the run if it
    stays away, since the likeliest reason is that the user quit Draw Things on purpose."""
    if await server_reachable(host, port):
        return
    print(f"  API server {host}:{port} not reachable; waiting up to {max_wait:.0f}s")
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        await nap(min(5.0, max(0.0, deadline - time.monotonic())), out_dir)
        if await server_reachable(host, port):
            print("  API server is back")
            return
    raise StopRun(f"API server {host}:{port} unreachable for {max_wait:.0f}s (Draw Things closed?)")


def image_problem(path: Path, width: int, height: int) -> str | None:
    """Why a returned PNG is unusable (wrong size, or one flat colour from a NaN decode), or None."""
    from PIL import Image, ImageStat

    try:
        with Image.open(path) as im:
            im.load()
            if im.size != (width, height):
                return f"image is {im.size[0]}x{im.size[1]}, asked for {width}x{height}"
            if max(ImageStat.Stat(im.convert("L").resize((256, 256))).stddev) < 1.0:
                return "image is a single flat colour (failed decode)"
    except Exception as e:  # noqa: BLE001
        return f"image unreadable: {type(e).__name__}: {e}"
    return None


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

# The Draw Things+ cloud behind Bridge Mode is generous but flaky: it aborts jobs before the
# first step, drops them mid-sampling ("No images received from server"), and stalls. A failed
# attempt is retried on a fresh connection with growing pauses, a stalled one is cancelled, and
# seeds that still fail get one more pass at the end; finished seeds are never rendered twice
# (resume, in main). The run stays easy to stop: Ctrl-C or kill end it at once, a STOP file ends
# it within seconds, and it stops by itself when the server is gone (the user may have quit the
# app on purpose) or when attempts keep failing in a row (a systematic problem, not the cloud).

def report(entry: dict) -> None:
    seed = entry["seed"]
    if entry["status"] == "ok" and entry.get("resumed"):
        print(f"  seed {seed}: already rendered, skipped -> {entry['file']}")
    elif entry["status"] == "ok":
        print(f"  seed {seed}: ok in {entry['seconds']:.0f}s (first step at {entry['first_step_seconds']}s, "
              f"attempt {entry['attempts']}) -> {entry['file']}")
    elif entry["status"] == "stopped":
        print(f"  seed {seed}: stopped ({entry['error']})")
    else:
        print(f"  seed {seed}: gave up after {entry['attempts']} attempts: {entry['error']}")


async def render_all(args, spec: dict, settings: dict, config_base: dict, config_recipe: dict,
                     prompt: str, negative: str, seeds: list[int], init_image: ImageBuffer | None,
                     out_dir: Path, name: str,
                     done: dict[int, dict], save, state: dict) -> list[dict]:
    """Render every seed not in `done`; `save(entries)` runs after each seed so a crash loses nothing."""
    entries: dict[int, dict] = {s: done[s] for s in seeds if s in done}
    for e in entries.values():
        report(e)

    def ordered() -> list[dict]:
        return [entries[s] for s in seeds if s in entries]

    todo = [s for s in seeds if s not in entries]
    try:
        for pass_no in range(1, args.passes + 1):
            if not todo:
                break
            if pass_no > 1:
                print(f"\npass {pass_no}: retrying {len(todo)} failed seed(s) after {args.pass_wait:.0f}s")
                await nap(args.pass_wait, out_dir)
            for seed in todo:
                previous = entries.get(seed)
                entry = await render_one(args, spec, settings, config_base, config_recipe,
                                         prompt, negative, seed, init_image, out_dir, name, state)
                if previous:  # keep the attempt history of earlier passes
                    entry["history"] = previous.get("history", []) + entry["history"]
                    entry["attempts"] = len(entry["history"])
                entries[seed] = entry
                report(entry)
                save(ordered())
                if state.get("stop"):
                    raise StopRun(state["stop"])
            todo = [s for s in seeds if entries[s]["status"] != "ok"]
    except StopRun as e:
        state["stop"] = str(e)
        print(f"\nrun stopped: {e}")
    return ordered()


async def attempt_once(args, rb: RequestBuilder, progress: dict, out_dir: Path):
    """One generation on a fresh connection; cancelled on a stall, a timeout or a stop file."""
    async with DrawThings.grpc(host=args.host, port=args.port, progressbar=False, disable_messages=True) as service:
        task = asyncio.ensure_future(service.generate(rb))
        t0 = time.monotonic()
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=2)
                if done:
                    return task.result()
                check_stop(out_dir)
                now = time.monotonic()
                if now - t0 > args.timeout:
                    raise TimeoutError(f"no image after {args.timeout:.0f}s")
                if now - progress["last"] > args.stall_timeout:
                    where = f"step {progress['step']}" if progress.get("step") is not None else "before the first step"
                    raise TimeoutError(f"stalled {args.stall_timeout:.0f}s with no progress ({where})")
        finally:
            if not task.done():
                task.cancel()
                await asyncio.wait({task}, timeout=5)


async def render_one(args, spec, settings, config_base, config_recipe, prompt, negative, seed,
                     init_image: ImageBuffer | None, out_dir: Path, name: str, state: dict) -> dict:
    job_config = copy.deepcopy(config_base)
    job_config["seed"] = seed
    config = Configs.create(job_config)
    rb = RequestBuilder(config, prompt, negative or None)
    if init_image is not None:
        rb.init_image(init_image)
    rb.model_spec = spec  # picked up by _build_with_override
    progress: dict = {}

    def on_progress(signpost, _preview):
        now = time.monotonic()
        progress["last"] = now
        if signpost is not None and signpost.is_set("sampling"):
            progress["step"] = signpost.sampling.step
            progress.setdefault("first", round(now - progress["t0"], 1))

    if hasattr(rb, "on_progress"):
        rb.on_progress(on_progress)
    else:
        rb._on_progress = on_progress  # noqa: SLF001

    file = out_dir / f"{name}-s{seed}.png"
    config_file = file.with_suffix(".config.json")
    part = out_dir / f"{name}-s{seed}.part.png"  # PIL picks the format from the extension
    attempts = args.retries + 1
    history: list[dict] = []
    error = ""

    def entry(status: str) -> dict:
        last = history[-1] if history else {}
        return {"seed": seed, "status": status, "seconds": last.get("seconds"),
                "first_step_seconds": last.get("first_step_seconds"), "file": str(file) if status == "ok" else None,
                "config_file": str(config_file) if status == "ok" else None,
                "attempts": len(history), "error": None if status == "ok" else error, "history": history}

    for attempt in range(1, attempts + 1):
        progress.clear()
        progress["t0"] = progress["last"] = time.monotonic()
        try:
            check_stop(out_dir)
            await wait_for_server(args.host, args.port, args.server_wait, out_dir)
            progress["t0"] = progress["last"] = time.monotonic()
            state["requests"] = state.get("requests", 0) + 1
            result = await attempt_once(args, rb, progress, out_dir)
            if len(result) == 0:
                raise RuntimeError("empty result")
            result[-1].to_file(part)  # write aside, check, then rename: a .png on disk is always a good one
            problem = image_problem(part, settings["width"], settings["height"])
            if problem:
                raise RuntimeError(problem)
            write_config_recipe(config_file, config_recipe["name"], prompt, negative,
                                config_recipe["raw"], job_config, seed,
                                "init-image.png" if init_image is not None else None,
                                args.init_fit)
            part.replace(file)
            history.append({"attempt": attempt, "error": None, "seconds": round(time.monotonic() - progress["t0"], 1),
                            "first_step_seconds": progress.get("first"), "last_step": progress.get("step")})
            state["failures_in_a_row"] = 0
            return entry("ok")
        except StopRun as e:
            error = str(e)
            part.unlink(missing_ok=True)
            state["stop"] = error
            return entry("stopped")
        except Exception as e:  # noqa: BLE001  (CancelledError and KeyboardInterrupt pass through)
            error = f"{type(e).__name__}: {str(e)[:300]}"
        part.unlink(missing_ok=True)
        elapsed = time.monotonic() - progress["t0"]
        where = f"at step {progress['step']}" if progress.get("step") is not None else "before the first step"
        history.append({"attempt": attempt, "error": error, "seconds": round(elapsed, 1),
                        "first_step_seconds": progress.get("first"), "last_step": progress.get("step")})
        state["failures_in_a_row"] = state.get("failures_in_a_row", 0) + 1
        if state["failures_in_a_row"] >= args.max_failures_in_a_row:
            state["stop"] = (f"{state['failures_in_a_row']} attempts failed in a row, last: {error}; that looks "
                             "systematic (spec, settings, prompt, or this script), not the cloud")
            return entry("error")
        if attempt < attempts:
            wait = backoff(attempt, args.retry_wait, args.retry_wait_max)
            print(f"  seed {seed}: attempt {attempt}/{attempts} failed after {elapsed:.0f}s {where} ({error}); "
                  f"retrying in {wait:.0f}s")
            try:
                await nap(wait, out_dir)
            except StopRun as e:
                state["stop"] = str(e)
                return entry("error")
    return entry("error")


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
    ap.add_argument("--config", help="Copy Configuration JSON, app preset, or recipe file; '-' reads stdin")
    ap.add_argument("--prompt-file", help="prompt text file, or a .json caption (minified before sending)")
    ap.add_argument("--prompt", help="inline prompt (instead of --prompt-file)")
    ap.add_argument("--negative-file"); ap.add_argument("--negative", default=None)
    ap.add_argument("--init-image", help="source image for image-to-image or upscaling")
    ap.add_argument("--init-fit", choices=["fill", "stretch"], default=None,
                    help="place the init image on the canvas: fill preserves aspect ratio and center-crops (default)")
    ap.add_argument("--size", help="WxH in pixels, multiples of 64 (default: recipe default)")
    ap.add_argument("--scale", type=float,
                    help="output scale relative to --init-image (for example 2 for 2x); exclusive with --size")
    ap.add_argument("--seeds", help="literal seeds: 12345 or 12345,777 (never a count)")
    ap.add_argument("--count", type=int, help="draw this many random seeds (default 1 when --seeds is not given)")
    ap.add_argument("--steps", type=int); ap.add_argument("--cfg", type=float); ap.add_argument("--shift", type=float)
    ap.add_argument("--sampler")
    ap.add_argument("--resolution-dependent-shift", dest="resolution_dependent_shift", action="store_true", default=None)
    ap.add_argument("--no-resolution-dependent-shift", dest="resolution_dependent_shift", action="store_false")
    ap.add_argument("--tiled-decode", dest="tiled_decode", action="store_true", default=None)
    ap.add_argument("--no-tiled-decode", dest="tiled_decode", action="store_false")
    ap.add_argument("--tiled-diffusion", dest="tiled_diffusion", action="store_true", default=None)
    ap.add_argument("--no-tiled-diffusion", dest="tiled_diffusion", action="store_false")
    ap.add_argument("--zero-negative", dest="zero_negative", action="store_true", default=None,
                    help="zero negative prompt: the model's own unconditional branch under CFG (Ideogram 4 needs it)")
    ap.add_argument("--no-zero-negative", dest="zero_negative", action="store_false")
    ap.add_argument("--lora", action="append", default=[], metavar="FILE:WEIGHT", help="local LoRA file and weight (repeatable)")
    ap.add_argument("--out", help="directory for the PNGs, run.json and the contact sheet")
    ap.add_argument("--name", help="base name for files (default: prompt file stem or 'render')")
    ap.add_argument("--log", help="append one JSON line per image to this runs.jsonl")
    ap.add_argument("--note", default="", help="free text stored with the run (what changed this round)")
    ap.add_argument("--no-sheet", action="store_true"); ap.add_argument("--thumb", type=int, default=512)
    ap.add_argument("--retries", type=int, default=3,
                    help="extra attempts per image within a pass (default 3; every failure counts as transient)")
    ap.add_argument("--retry-wait", type=float, default=20, help="first pause between attempts; doubles each time (default 20 s)")
    ap.add_argument("--retry-wait-max", type=float, default=240, help="longest pause between attempts (default 240 s)")
    ap.add_argument("--passes", type=int, default=2, help="passes over the seeds; later passes retry the failed ones (default 2)")
    ap.add_argument("--pass-wait", type=float, default=120, help="pause before a retry pass (default 120 s)")
    ap.add_argument("--timeout", type=float, default=1200, help="seconds per attempt (default 1200)")
    ap.add_argument("--stall-timeout", type=float, default=300,
                    help="cancel and retry an attempt that sends no progress for this long (default 300 s)")
    ap.add_argument("--server-wait", type=float, default=60,
                    help="how long to wait for an unreachable API server before stopping the run (default 60 s)")
    ap.add_argument("--max-failures-in-a-row", type=int, default=5,
                    help="stop the run after this many failed attempts in a row: past that it is not the cloud (default 5)")
    ap.add_argument("--max-images", type=int, default=8,
                    help="refuse to start when more images than this would be rendered (default 8; raise it on purpose)")
    ap.add_argument("--overwrite", action="store_true",
                    help="render every seed again even when --out already holds it from the same settings")
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

    config_input = load_config_recipe(args.config) if args.config else None

    # Resolve the model spec. With --config alone, its model file selects the recipe.
    recipe_key = args.recipe
    if args.recipe:
        if args.recipe not in recipes:
            raise SystemExit(f"unknown recipe {args.recipe!r}; try --list-recipes")
        recipe = recipes[args.recipe]
    elif args.spec:
        recipe = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        if "spec" not in recipe:  # a bare spec file
            recipe = {"spec": recipe, "defaults": {}}
    elif config_input:
        model = config_input["sdk"].get("model") or config_input["raw"].get("model")
        if not model:
            raise SystemExit("--config has no model; give --recipe NAME or --spec FILE")
        matched = recipe_for_model(recipes, str(model))
        if not matched:
            raise SystemExit(f"no recipe carries model {model!r}; derive its spec first, then give --spec FILE")
        recipe_key, recipe = matched
    else:
        raise SystemExit("give --recipe NAME, --spec FILE, or --config FILE")
    spec = recipe["spec"]
    d = recipe.get("defaults", {})

    base = copy.deepcopy(config_input["sdk"] if config_input else {})
    init_image_path = args.init_image or (config_input["init_image"] if config_input else None)
    args.init_fit = args.init_fit or (config_input["init_fit"] if config_input else None) or d.get("init_fit", "fill")
    if args.size and args.scale is not None:
        raise SystemExit("give --size or --scale, not both")
    if args.scale is not None and args.scale <= 0:
        raise SystemExit("--scale must be greater than zero")
    if args.size:
        width, height = parse_size(args.size)
    elif args.scale is not None:
        if not init_image_path:
            raise SystemExit("--scale needs --init-image")
        source_width, source_height = source_image_size(init_image_path)
        width, height = parse_size(f"{round(source_width * args.scale)}x{round(source_height * args.scale)}")
    elif base.get("width") is not None and base.get("height") is not None:
        width, height = parse_size(f"{base['width']}x{base['height']}")
    elif init_image_path and d.get("scale") is not None:
        source_width, source_height = source_image_size(init_image_path)
        width, height = parse_size(f"{round(source_width * float(d['scale']))}x{round(source_height * float(d['scale']))}")
    else:
        width, height = parse_size(d.get("size") or "1024x1024")
    steps = args.steps if args.steps is not None else int(base.get("steps", d.get("steps", 20)))
    cfg = args.cfg if args.cfg is not None else float(base.get("guidance", d.get("cfg", 1.0)))
    shift = args.shift if args.shift is not None else float(base.get("shift", d.get("shift", 1.0)))
    sampler = normalize_sampler(args.sampler or base.get("sampler") or d.get("sampler", "EulerATrailing"))
    rds = (args.resolution_dependent_shift if args.resolution_dependent_shift is not None
           else bool(base.get("resolution_dependent_shift", d.get("resolution_dependent_shift", False))))
    tiled_decode = (args.tiled_decode if args.tiled_decode is not None
                    else bool(base.get("tiled_decoding", d.get("tiled_decode", False))))
    tiled_diffusion = (args.tiled_diffusion if args.tiled_diffusion is not None
                       else bool(base.get("tiled_diffusion", d.get("tiled_diffusion", False))))
    zero_negative = (args.zero_negative if args.zero_negative is not None
                     else bool(base.get("zero_negative_prompt", d.get("zero_negative_prompt", False))))

    loras = copy.deepcopy(base.get("loras", []))
    if args.lora:  # explicit CLI LoRAs replace the file's list
        loras = []
        for item in args.lora:
            f, _, weight = item.partition(":")
            loras.append({"file": f, "weight": float(weight or 1.0), "mode": "All"})

    base.update({
        "model": spec["file"], "width": width, "height": height, "steps": steps,
        "guidance": cfg, "shift": shift, "sampler": sampler,
        "resolution_dependent_shift": rds, "tiled_decoding": tiled_decode,
        "tiled_diffusion": tiled_diffusion,
        "zero_negative_prompt": zero_negative, "loras": loras,
    })
    for key in ("decoding_tile_width", "decoding_tile_height", "decoding_tile_overlap",
                "diffusion_tile_width", "diffusion_tile_height", "diffusion_tile_overlap"):
        if key not in base and key in d:
            base[key] = d[key]
    base.setdefault("seed_mode", "ScaleAlike")
    base.setdefault("strength", d.get("strength", 1.0))
    base.setdefault("batch_count", 1)
    base.setdefault("batch_size", 1)
    base.setdefault("controls", [])
    if base["batch_count"] != 1 or base["batch_size"] != 1:
        raise SystemExit("--config batchCount and batchSize must both be 1; this renderer saves one image per seed")

    settings = {
        "width": width, "height": height,
        "steps": steps, "cfg": cfg, "shift": shift, "sampler": sampler,
        "resolution_dependent_shift": rds, "tiled_decode": tiled_decode,
        "tiled_diffusion": tiled_diffusion,
        "zero_negative": zero_negative,
        "loras": [(item.get("file"), item.get("weight", 1.0)) for item in loras],
    }

    if args.prompt_file or args.prompt is not None:
        prompt, prompt_path = read_prompt(args.prompt_file, args.prompt)
    elif config_input and config_input["prompt"] is not None:
        prompt, prompt_path = config_input["prompt"], config_input["path"]
    elif recipe.get("prompt_required", True) is False:
        prompt, prompt_path = "", None
    else:
        raise SystemExit("give --prompt-file or --prompt, or use a --config recipe with a prompt")
    if recipe.get("init_image_required") and not init_image_path:
        raise SystemExit(f"recipe {recipe_key!r} needs --init-image")
    # CLI wins, then the config recipe, then the model recipe default. --negative "" clears it.
    if args.negative_file:
        negative = Path(args.negative_file).read_text(encoding="utf-8")
    else:
        negative = (args.negative if args.negative is not None else
                    config_input["negative"] if config_input and config_input["negative"] is not None else
                    d.get("negative", ""))
    negative = negative.strip()
    if args.seeds and args.count:
        raise SystemExit("give --seeds (literal seeds) or --count (random seeds), not both")
    if args.seeds:
        seeds = parse_seeds(args.seeds)
    elif args.count:
        seeds = [random.randint(1, 2**32 - 2) for _ in range(args.count)]
    elif config_input and base.get("seed") is not None:
        seeds = [int(base["seed"])]
    else:
        seeds = [random.randint(1, 2**32 - 2)]
    if not args.out and not args.estimate_only:
        raise SystemExit("give --out DIR")
    out_dir = Path(args.out or ".")
    if not args.estimate_only:
        out_dir.mkdir(parents=True, exist_ok=True)
    name = (args.name or (config_input["name"] if config_input else None) or
            (Path(prompt_path).stem if prompt_path else None) or
            (f"{Path(init_image_path).stem}-upscaled" if init_image_path else "render"))
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "render"
    export_recipe = {
        "name": (config_input["name"] if config_input else None) or name,
        "raw": copy.deepcopy(config_input["raw"] if config_input else {}),
    }

    init_image = None
    init_info = None
    if init_image_path:
        if args.estimate_only:
            source_width, source_height = source_image_size(init_image_path)
            init_source = Path(init_image_path).expanduser().resolve()
            init_info = {
                "source": str(init_source), "sha256": sha256_file(init_source),
                "source_size": [source_width, source_height], "canvas_size": [width, height],
                "fit": args.init_fit, "prepared_file": "init-image.png",
            }
        else:
            init_image, init_info = prepare_init_image(init_image_path, width, height, args.init_fit)

    if not args.estimate_only and prompt:  # keep the exact non-empty prompt with the renders
        prompt_name = "prompt.json" if prompt.lstrip().startswith("{") else "prompt.txt"
        (out_dir / prompt_name).write_text(prompt + "\n", encoding="utf-8")
        if negative:
            (out_dir / "negative.txt").write_text(negative + "\n", encoding="utf-8")

    tokens, exact = qwen_tokens.count(prompt)
    print(f"{spec['file']} {width}x{height} steps {settings['steps']} cfg {settings['cfg']} shift {settings['shift']} "
          f"{settings['sampler']} | {len(prompt.split())} words, {tokens} tokens ({'exact' if exact else 'estimate'}) | seeds {seeds}")
    if init_info:
        print(f"init image: {init_info['source_size'][0]}x{init_info['source_size'][1]} -> {width}x{height} "
              f"with {args.init_fit} (sha256 {init_info['sha256'][:12]})")
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

    # Resume: the same command run again against the same --out renders only what is missing.
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_path = out_dir / "run.json"
    plain_settings = {k: v for k, v in settings.items() if k != "loras"}
    plain_configuration = copy.deepcopy(base)
    plain_configuration.pop("seed", None)  # each image carries its own seed
    done: dict[int, dict] = {}
    prior = None
    if run_path.exists():
        try:
            prior = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prior = None
    same_run = bool(prior) and all((
        prior.get("model") == spec["file"], prior.get("name") == name, prior.get("prompt_sha256") == sha256(prompt),
        prior.get("negative", "") == negative, prior.get("settings") == plain_settings,
        prior.get("configuration") == plain_configuration,
        prior.get("init_image") == init_info,
        [list(x) for x in prior.get("loras", [])] == [list(x) for x in settings["loras"]],
    ))
    if same_run and not args.overwrite:
        if not args.seeds:  # --count: keep the random seeds drawn the first time
            earlier = prior.get("seeds") or [e["seed"] for e in prior.get("images", [])]
            seeds = (earlier + seeds)[:max(len(seeds), len(earlier))]
        done = {e["seed"]: {**e, "resumed": True} for e in prior.get("images", [])
                if e.get("status") == "ok" and e.get("file") and Path(e["file"]).exists() and e["seed"] in seeds}
        started = prior.get("started", started)
        if done:
            print(f"resuming {run_path}: {len(done)} of {len(seeds)} seeds already rendered")
    elif not args.overwrite:
        clash = [s for s in seeds if (out_dir / f"{name}-s{s}.png").exists()]
        if clash:
            print(f"{out_dir} already holds {name} renders of seeds {clash} made with other settings or another prompt; "
                  "use a new --out, or pass --overwrite to replace them", file=sys.stderr)
            return 5

    if init_image is not None:
        init_image.to_file(out_dir / "init-image.png")

    run = {
        "started": started, "run_dir": str(out_dir), "name": name, "recipe": recipe_key, "model": spec["file"], "spec": spec,
        "config_file": config_input["path"] if config_input else None, "configuration": plain_configuration,
        "prompt_file": prompt_path, "prompt_sha256": sha256(prompt), "prompt_words": len(prompt.split()), "prompt_chars": len(prompt),
        "prompt_tokens": tokens, "prompt_tokens_exact": exact,
        "prompt": prompt, "negative": negative, "settings": plain_settings,
        "init_image": init_info,
        "loras": settings["loras"], "note": args.note, "host": f"{args.host}:{args.port}", "compute_units": units,
        "seeds": seeds, "images": [], "sheet": None,
    }

    def save(entries: list[dict]) -> None:
        run["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        run["images"] = [{k: v for k, v in e.items() if k != "resumed"} for e in entries]
        tmp = run_path.with_name("run.json.part")
        tmp.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(run_path)

    todo = [s for s in seeds if s not in done]
    if len(todo) > args.max_images:
        print(f"{len(todo)} images to render, more than --max-images {args.max_images}; raise it if that is intended",
              file=sys.stderr)
        return 7
    worst = len(todo) * (args.retries + 1) * args.passes
    eta = "" if units is None else f", roughly {len(todo) * (30 + units * 0.005) / 60:.0f} min if nothing fails"
    print(f"plan: {len(todo)} image(s), at most {worst} requests{eta}")
    print(f"to stop: Ctrl-C, kill {os.getpid()}, or touch {out_dir / 'STOP'} (or {GLOBAL_STOP} for every run)")

    def on_term(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_term)
    state: dict = {}
    try:
        entries = asyncio.run(render_all(args, spec, settings, base, export_recipe,
                                         prompt, negative, seeds, init_image, out_dir, name, done, save, state))
    except KeyboardInterrupt:
        print(f"\ninterrupted after {state.get('requests', 0)} requests; finished seeds are in {run_path}; "
              "run the same command again to resume", file=sys.stderr)
        return 130
    run["requests"] = state.get("requests", 0)
    run["stopped"] = state.get("stop")

    sheet = None if args.no_sheet else contact_sheet(entries, out_dir / f"{name}-sheet.jpg", args.thumb)
    run["sheet"] = str(sheet) if sheet else None
    save(entries)
    if args.log:
        log_path = Path(args.log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            for e in (e for e in entries if not e.get("resumed")):
                line = {"ts": started, "run_dir": str(out_dir), "name": name, "recipe": recipe_key, "model": spec["file"],
                        "prompt_file": prompt_path, "prompt_sha256": run["prompt_sha256"], "prompt_words": run["prompt_words"], "prompt_tokens": tokens,
                        "width": width, "height": height, "steps": settings["steps"], "cfg": settings["cfg"], "shift": settings["shift"],
                        "sampler": settings["sampler"], "rds": settings["resolution_dependent_shift"], "zero_negative": settings["zero_negative"], "loras": settings["loras"],
                        "init_image": init_info,
                        "compute_units": units, "seed": e["seed"], "status": e["status"], "seconds": e["seconds"], "first_step_seconds": e["first_step_seconds"],
                        "file": e["file"], "error": e["error"], "note": args.note}
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    ok = [e for e in entries if e["status"] == "ok"]
    print(f"\n{len(ok)}/{len(seeds)} images in {out_dir} ({state.get('requests', 0)} requests sent)")
    if sheet:
        print(f"contact sheet: {sheet}")
    elif ok:
        print(f"image: {ok[0]['file']}")
    if args.json:
        print(json.dumps(run, ensure_ascii=False))
    if state.get("stop"):
        print("run the same command again to resume once the cause is fixed")
        return 6
    return 0 if len(ok) == len(seeds) else 1


if __name__ == "__main__":
    sys.exit(main())
