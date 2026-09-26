#!/usr/bin/env python3
"""Exact Qwen3 token counts for prompts, shared with the krea-prompt linter.

Uses the Qwen3-VL tokenizer files (vocab.json and merges.txt from
Qwen/Qwen3-VL-4B-Instruct, Apache-2.0) when they are in the cache folder the
krea-prompt skill also uses, and a calibrated estimate otherwise.

    qwen_tokens.py prompt.txt          # prints the count and whether it is exact
    qwen_tokens.py --fetch-tokenizer   # downloads the two files once (about 4.4 MB)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

TOKENIZER_FILES = ("vocab.json", "merges.txt")
TOKENIZER_URL = "https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct/resolve/main/"
ENV_TOKENIZER_DIR = "KREA_TOKENIZER_DIR"
ESTIMATE_FACTOR = 1.07

class BPE:
    """Byte-level BPE token counter for GPT-2-family and Qwen2-family vocabularies, stdlib only."""
    GPT2_PAT = re.compile(r"""'s|'t|'re|'ve|'m|'ll|'d| ?[^\W\d_]+| ?\d+| ?(?:[^\s\w]|_)+|\s+(?!\S)|\s+""")
    QWEN_PAT = re.compile(r"""(?i:'s|'t|'re|'ve|'m|'ll|'d)|(?:[^\r\n\w]|_)?[^\W\d_]+|\d| ?(?:[^\s\w]|_)+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+""")

    def __init__(self, vocab_path, merges_path):
        vocab = json.load(open(vocab_path, encoding="utf-8"))
        qwen = len(vocab) > 100000
        self.pat = self.QWEN_PAT if qwen else self.GPT2_PAT
        self.label = "qwen vocab, exact" if qwen else "gpt-2 vocab, close to Qwen's but not exact"
        self.short = "bpe, qwen vocab" if qwen else "bpe, gpt-2 vocab"
        lines = [l for l in open(merges_path, encoding="utf-8").read().split("\n") if l and not l.startswith("#")]
        self.ranks = {tuple(l.split()): i for i, l in enumerate(lines)}
        bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
        cs = bs[:]
        n = 0
        for b in range(256):
            if b not in bs:
                bs.append(b)
                cs.append(256 + n)
                n += 1
        self.byte_enc = dict(zip(bs, [chr(c) for c in cs]))
        self.cache = {}

    def _bpe(self, token):
        if token in self.cache:
            return self.cache[token]
        word = tuple(token)
        while len(word) > 1:
            pairs = [(word[i], word[i + 1]) for i in range(len(word) - 1)]
            best = min(pairs, key=lambda p: self.ranks.get(p, float("inf")))
            if best not in self.ranks:
                break
            a, b = best
            new, i = [], 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
                    new.append(a + b)
                    i += 2
                else:
                    new.append(word[i])
                    i += 1
            word = tuple(new)
        self.cache[token] = word
        return word

    def count(self, text):
        n = 0
        for m in self.pat.findall(text):
            n += len(self._bpe("".join(self.byte_enc[b] for b in m.encode("utf-8"))))
        return n


ESTIMATE_FACTOR = 1.07  # Qwen tokens per piece, mean over Krea's 20 example prompts
ESTIMATE_BAND = 7  # percent: the largest error the estimate showed on those prompts


def estimate_tokens(text: str) -> int:
    """Estimate from pieces: letter runs, single digits (Qwen tokenizes numbers digit by digit) and
    punctuation marks, times ESTIMATE_FACTOR. Calibrated against the Qwen3-VL tokenizer on Krea's
    20 example prompts; single prompts land within ESTIMATE_BAND percent of the exact count."""
    pieces = re.findall(r"[A-Za-z]+|\d|[^\sA-Za-z\d]", text)
    return int(round(len(pieces) * ESTIMATE_FACTOR))


def count_tokens(text: str, bpe=None):
    """Return (tokens, short_label, long_label)."""
    if bpe is not None:
        return bpe.count(text), bpe.short, bpe.label
    return estimate_tokens(text), "estimated", "estimated from words"


def default_tokenizer_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "krea-prompt", "tokenizer")


def find_tokenizer_dir(explicit=None):
    """The first folder holding vocab.json and merges.txt among --tokenizer, $KREA_TOKENIZER_DIR, the cache."""
    for d in (explicit, os.environ.get(ENV_TOKENIZER_DIR), default_tokenizer_dir()):
        if d and all(os.path.isfile(os.path.join(d, f)) for f in TOKENIZER_FILES):
            return d
        if d == explicit and explicit:
            raise OSError(f"no vocab.json and merges.txt in {explicit}")
    return None


def fetch_tokenizer(dest=None):
    """Download Qwen3-VL's vocab.json and merges.txt into dest (default: the cache folder). Returns dest."""
    import urllib.request
    dest = dest or default_tokenizer_dir()
    os.makedirs(dest, exist_ok=True)
    for f in TOKENIZER_FILES:
        urllib.request.urlretrieve(TOKENIZER_URL + f, os.path.join(dest, f))
    return dest


def load_bpe(vocab=None, merges=None, tokenizer_dir=None, auto=True):
    """A BPE counter from an explicit pair, else from a tokenizer folder (flag, env, cache), else None."""
    if vocab and merges:
        return BPE(vocab, merges)
    d = find_tokenizer_dir(tokenizer_dir) if (auto or tokenizer_dir) else None
    if d:
        return BPE(os.path.join(d, "vocab.json"), os.path.join(d, "merges.txt"))
    return None




def count(text: str):
    """Return (tokens, exact) using the tokenizer files when present, else the estimate."""
    try:
        bpe = load_bpe()
    except Exception:  # noqa: BLE001
        bpe = None
    if bpe is None:
        return estimate_tokens(text), False
    n = bpe.count(text)
    return (n[0] if isinstance(n, tuple) else n), True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="text or JSON file (JSON is minified before counting)")
    ap.add_argument("--fetch-tokenizer", nargs="?", const="", metavar="DIR", help="download the tokenizer files")
    a = ap.parse_args()
    if a.fetch_tokenizer is not None:
        dest = fetch_tokenizer(a.fetch_tokenizer or None)
        print(f"tokenizer files in {dest}")
        return 0
    if not a.path:
        ap.error("give a file or --fetch-tokenizer")
    text = Path(a.path).read_text(encoding="utf-8").strip()
    if a.path.endswith(".json"):
        text = json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
    n, exact = count(text)
    print(f"{n} tokens ({'exact, Qwen3 tokenizer' if exact else 'estimate, within about 7%'}), {len(text.split())} words, {len(text)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
