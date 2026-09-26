#!/usr/bin/env python3
"""Estimate Draw Things compute units for a job before sending it.

A port of `ComputeUnits.swift` and the per-model instruction counts from
drawthingsai/draw-things-community (Libraries/ModelZoo and
Libraries/SwiftDiffusion/Sources/Models/InstructionCount), for the model
families this skill drives. Units are what the app shows next to the rocket
icon; the cloud refuses a job above the tier limit (10,000 community,
40,000 Draw Things+) instead of charging extra.

    compute_units.py --version krea_2 --size 2048x1344 --steps 8 --cfg 1.0
    compute_units.py --version ideogram_4 --size 2048x1344 --steps 20 --cfg 7
    compute_units.py --version qwen_image --size 2048x1344 --steps 30 --cfg 4
"""
from __future__ import annotations

import argparse
import math
import sys

CALIBRATION = 5.14816e-12          # instruction count -> compute units
THRESHOLDS = {"community": 10_000, "plus": 40_000}
PER_BOOST = 60_000
# Padded text length the server assumes when the spec does not set one
# (ComputeUnits.defaultTokenLength); a spec's padded_text_encoding_length wins.
DEFAULT_TEXT_LENGTH = {"krea_2": 256, "ideogram_4": 512, "z_image": 512, "qwen_image": 512,
                       "flux1": 512, "flux2": 512, "flux2_9b": 512, "flux2_4b": 512, "ernie_image": 512}


def dense(rows: int, inp: int, out: int) -> int:
    return rows * out * inp


def sdpa(batch: int, heads: int, head_dim: int, seq_a: int, seq_b: int) -> int:
    return batch * heads * (2 * head_dim + 5) * seq_a * seq_b


def conv(batch: int, out_h: int, out_w: int, out_ch: int, kh: int, kw: int, in_ch: int, groups: int = 1) -> int:
    return batch * out_h * out_w * out_ch * (kh * kw * (in_ch // groups))


# --- Krea 2 -------------------------------------------------------------------------

def _krea2_attention(batch, token_len, query_len, hidden, heads, kv_heads, segments=()):
    head_dim = hidden // heads
    kv_size = head_dim * kv_heads
    rq, rkv = batch * query_len, batch * token_len
    total = dense(rq, hidden, hidden) + 2 * dense(rkv, hidden, kv_size) + 2 * dense(rq, hidden, hidden)
    if len(segments) > 1:
        total += sum(sdpa(batch, heads, head_dim, s, s) for s in segments)
    else:
        total += sdpa(batch, heads, head_dim, query_len, token_len)
    return total


def _krea2_swiglu(rows, hidden, inter):
    return 2 * dense(rows, hidden, inter) + dense(rows, inter, hidden)


def _krea2_block(batch, token_len, query_len, hidden=6144, heads=48, kv_heads=12, inter=16384):
    return (_krea2_attention(batch, token_len, query_len, hidden, heads, kv_heads)
            + _krea2_swiglu(batch * query_len, hidden, inter))


def _krea2_text_fusion_block(batch, token_len, segments=(), hidden=2560, heads=20, inter=6912):
    return (_krea2_attention(batch, token_len, token_len, hidden, heads, heads, segments)
            + _krea2_swiglu(batch * token_len, hidden, inter))


def krea2_main(batch, height, width, text_len, hidden=6144, layers=28, inter=16384):
    image_len = (height // 2) * (width // 2)
    token_len = image_len + text_len
    total = dense(batch * image_len, 64, hidden)
    for i in range(layers):
        q = image_len if i == layers - 1 else token_len
        total += _krea2_block(batch, token_len, q, hidden, inter=inter)
    total += dense(batch * image_len, hidden, 64)
    return total


def krea2_text_fusion(batch, text_lens, hidden=2560, layerwise=12, layers=2, inter=6912):
    total_text = text_lens[0] + text_lens[1]
    segments = [text_lens[0], text_lens[1]] if text_lens[0] > 0 else []
    total = 0
    for _ in range(layers):
        total += _krea2_text_fusion_block(batch * total_text, layerwise, (), hidden, inter=inter)
    total += dense(batch * total_text * hidden, layerwise, 1)
    for _ in range(layers):
        total += _krea2_text_fusion_block(batch, total_text, segments, hidden, inter=inter)
    return total


def krea2_fixed(batch, timesteps, text_len, text_in=2560, hidden=6144):
    return (dense(batch * text_len, text_in, hidden) + dense(batch * text_len, hidden, hidden)
            + dense(timesteps, 256, hidden) + dense(timesteps, hidden, hidden) + 6 * dense(timesteps, hidden, hidden))


# --- Ideogram 4 ---------------------------------------------------------------------

def _ideogram4_block(batch, q_len, kv_len, channels=4608, head_dim=256, inter=12288):
    rq, rkv = batch * q_len, batch * kv_len
    return (dense(rq, channels, channels) + 2 * dense(rkv, channels, channels) + dense(rq, channels, channels)
            + sdpa(batch, channels // head_dim, head_dim, q_len, kv_len)
            + 2 * dense(rq, channels, inter) + dense(rq, inter, channels))


def ideogram4_main(batch, height, width, text_len, channels=4608, layers=34, inter=12288):
    image_len = (height // 2) * (width // 2)
    total_len = image_len + text_len
    total = dense(batch * image_len, 128, channels)
    for i in range(layers):
        q = image_len if i == layers - 1 else total_len
        total += _ideogram4_block(batch, q, total_len, channels, inter=inter)
    total += dense(batch * image_len, channels, 128)
    return total


def ideogram4_fixed(timesteps, batch, text_len, text_in=4096 * 13, channels=4608, layers=34, mod=512):
    total = dense(batch * text_len, text_in, channels) + 2 * dense(timesteps, channels, channels) + dense(timesteps, channels, mod)
    total += layers * 4 * dense(timesteps, mod, channels)
    total += dense(timesteps, mod, channels)
    return total


# --- Qwen Image (2512 and 1.0; not 2.1) -----------------------------------------------
# Port of QwenImageInstructionCount / QwenImageFixedInstructionCount from the app's
# ComputeUnits sources: 60 joint-attention layers of 3072 channels, 128-wide heads, the last
# layer text-stream pre-only, 2x2 patchify on 16 latent channels, no reference images.

def qwen_image_main(batch, height, width, text_len, channels=3072, layers=60, reference_len=0):
    h, w = height // 2, width // 2
    image_len = h * w
    x_len = image_len + reference_len
    total_len = x_len + text_len
    heads, head_dim = channels // 128, 128
    total = conv(batch, h, w, channels, 2, 2, 16)
    for i in range(layers):
        pre_only = i == layers - 1
        rows_text = batch * text_len
        rows_x_kv = batch * x_len
        rows_x_out = batch * ((x_len - reference_len) if pre_only else x_len)
        total += 3 * dense(rows_text, channels, channels)
        total += 3 * dense(rows_x_kv, channels, channels)
        total += sdpa(batch, heads, head_dim, total_len, total_len)
        if not pre_only:
            total += dense(rows_text, channels, channels)
            total += dense(rows_text, channels, channels * 4)
            total += dense(rows_text, channels * 4, channels)
        total += dense(rows_x_out, channels, channels)
        total += dense(rows_x_out, channels, channels * 4)
        total += dense(rows_x_out, channels * 4, channels)
    total += dense(batch * image_len, channels, 2 * 2 * 16)
    return total


def qwen_image_fixed(timesteps, batch, text_len, channels=3072, layers=60, reference_len=0, text_in=3584):
    total = 0
    if reference_len > 0:
        total += 64 * channels * reference_len
    total += dense(batch * text_len, text_in, channels)
    if layers > 0:
        total += dense(timesteps, 256, channels) + dense(timesteps, channels, channels)
        for i in range(layers):
            pre_only = i == layers - 1
            total += ((2 if pre_only else 6) + 6) * dense(timesteps, channels, channels)
        total += 2 * dense(timesteps, channels, channels)
    return total


# --- estimate -----------------------------------------------------------------------

def estimate(version: str, width: int, height: int, steps: int, cfg: float, batch_size: int = 1,
             strength: float = 1.0, text_length: int | None = None) -> int | None:
    """Compute units for one request, or None when the model family is not ported."""
    text_len = text_length or DEFAULT_TEXT_LENGTH.get(version, 512)
    cfg_channels = 2 if cfg > 1.0 else 1     # no unconditional branch at guidance 1
    batch = max(1, batch_size) * cfg_channels
    lw, lh = width // 8, height // 8          # latent size for these families
    if version == "krea_2":
        main = krea2_main(1, lh, lw, text_len) * batch
        fixed_text = (text_len, text_len) if cfg_channels > 1 else (0, text_len)
        fixed = krea2_text_fusion(1, fixed_text) + krea2_fixed(1, 1, sum(fixed_text)) * batch
    elif version == "ideogram_4":
        main = ideogram4_main(1, lh, lw, text_len) * batch
        fixed = ideogram4_fixed(1, 1, text_len) * batch
    elif version == "qwen_image":
        main = qwen_image_main(1, lh, lw, text_len) * batch
        fixed = qwen_image_fixed(1, 1, text_len) * batch
    else:
        return None
    units = (main * CALIBRATION * steps * max(strength, 0.05)) + fixed * CALIBRATION
    return int(math.ceil(units))


def boosts_needed(units: int, threshold: int) -> int:
    if units <= threshold:
        return 0
    return 1 + math.ceil((units - max(threshold, PER_BOOST)) / PER_BOOST)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True, help="model version string: krea_2, ideogram_4, qwen_image")
    ap.add_argument("--size", required=True, help="WxH")
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--text-length", type=int, help="padded_text_encoding_length of the spec (default: the server's per-family default)")
    ap.add_argument("--tier", choices=list(THRESHOLDS), default="plus")
    a = ap.parse_args()
    w, h = (int(x) for x in a.size.lower().split("x"))
    units = estimate(a.version, w, h, a.steps, a.cfg, a.batch_size, a.strength, a.text_length)
    if units is None:
        print(f"no estimate for version {a.version!r}"); return 2
    limit = THRESHOLDS[a.tier]
    print(f"{units:,} compute units (limit {limit:,} for {a.tier}; {'ok' if units <= limit else 'OVER, needs %d boost(s)' % boosts_needed(units, limit)})")
    return 0 if units <= limit else 1


if __name__ == "__main__":
    sys.exit(main())
