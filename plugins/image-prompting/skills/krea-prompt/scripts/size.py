#!/usr/bin/env python3
"""Pick a width and height for Krea 2 at a given aspect ratio.

Usage:
    size.py 3:2                # 1K (about 1 megapixel), multiples of 64 and 16
    size.py 3:2 --2k           # 2K (about 4 megapixels, the open-weights Turbo ceiling)
    size.py 16:9 --max-width 2048
    size.py 2.35:1 --mp 2.5    # target megapixels
    size.py --table            # the eight hosted ratios at 1K and 2K
Facts used (Krea README, sampling.py, Draw Things community issue 105):
  - the reference code pads sizes up to a multiple of 16; Draw Things' size fields step by 64
  - Turbo generates 1K to 2K; Raw is trained to 1K; the hosted API is 1K only
  - Draw Things' 8-bit Turbo needs tiled decode above about 2.9 MP (fails at 1728x1728, works at 2048x1408)
"""
import argparse
import math
import sys

HOSTED = {"1:1": (1024, 1024), "4:3": (1184, 896), "3:2": (1248, 832), "16:9": (1376, 768),
          "2.35:1": (1568, 672), "4:5": (928, 1152), "2:3": (832, 1248), "9:16": (768, 1376)}
DECODE_OK = 2048 * 1408      # works without tiling (issue 105)
DECODE_FAIL = 1728 * 1728    # fails without tiling (issue 105)


def parse_ratio(s: str) -> float:
    if ":" in s:
        a, b = s.split(":", 1)
        return float(a) / float(b)
    if "x" in s.lower():
        a, b = s.lower().split("x", 1)
        return float(a) / float(b)
    return float(s)


def best(ratio: float, mp: float, step: int, max_w=None, max_h=None):
    """Smallest-error size on a `step` grid near `mp` megapixels, capped at 2048 per side."""
    target = mp * 1_000_000
    cap_w = min(max_w or 2048, 2048)
    cap_h = min(max_h or 2048, 2048)
    cands = []
    for w in range(256, cap_w + 1, step):
        for h in {round(w / ratio / step) * step, math.floor(w / ratio / step) * step, math.ceil(w / ratio / step) * step}:
            if h < 256 or h > cap_h:
                continue
            err_ratio = abs((w / h) / ratio - 1)
            err_mp = abs(w * h / target - 1)
            cands.append((err_ratio * 3 + err_mp, -w * h, w, h))
    if not cands:
        return None
    cands.sort()
    return cands[0][2], cands[0][3]


def note(w, h):
    px = w * h
    if px >= DECODE_FAIL:
        return "tiled decode needed on Draw Things 8-bit (above ~2.9 MP)"
    if px > DECODE_OK:
        return "near the ~2.9 MP Draw Things 8-bit decode threshold; tiled decode if the output bands"
    return "under the ~2.9 MP Draw Things 8-bit decode threshold, tiled decode off"


def fmt(w, h):
    return f"{w} x {h} ({w*h/1e6:.2f} MP, {w/h:.3f})"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ratio", nargs="?", help="W:H such as 3:2, or a decimal")
    ap.add_argument("--2k", dest="two_k", action="store_true", help="target 2K (about 4 MP) instead of 1K")
    ap.add_argument("--mp", type=float, help="target megapixels")
    ap.add_argument("--max-width", type=int)
    ap.add_argument("--max-height", type=int)
    ap.add_argument("--table", action="store_true", help="print the eight hosted ratios at 1K and 2K")
    a = ap.parse_args(argv)
    if a.table:
        print(f"{'ratio':8} {'hosted 1K':14} {'1K /64':14} {'2K /64':14} note")
        for r, (hw, hh) in HOSTED.items():
            k1 = best(parse_ratio(r), 1.0, 64)
            k2 = best(parse_ratio(r), 4.194, 64)
            print(f"{r:8} {hw}x{hh:<9} {k1[0]}x{k1[1]:<9} {k2[0]}x{k2[1]:<9} {note(*k2)}")
        return 0
    if not a.ratio:
        ap.print_help()
        return 2
    try:
        ratio = parse_ratio(a.ratio)
    except ValueError:
        print("error: ratio must look like 3:2, 1.5 or 1248x832", file=sys.stderr)
        return 2
    mp = a.mp or (4.194 if a.two_k else 1.0)
    print(f"aspect {a.ratio} = {ratio:.4f}, target {mp:.2f} MP")
    w0 = math.sqrt(mp * 1_000_000 * ratio)
    h0 = w0 / ratio
    cap_w = min(a.max_width or 2048, 2048)
    cap_h = min(a.max_height or 2048, 2048)
    if w0 > cap_w or h0 > cap_h:
        print(f"  the {cap_w if w0 > cap_w else cap_h} px ceiling on the {'long' if w0 > cap_w else 'short'} side limits this ratio below the target; sizes below are the largest that fit")
    if a.ratio in HOSTED and not a.two_k and not a.mp:
        print(f"  hosted Krea 2 (app/API, 1K): {fmt(*HOSTED[a.ratio])}")
    for step in (64, 16):
        r = best(ratio, mp, step, a.max_width, a.max_height)
        if r:
            print(f"  multiples of {step:2}: {fmt(*r)}  <- {note(*r)}")
    if mp > 1.2:
        print("  Raw is trained to 1K; use 2K sizes with Turbo only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
