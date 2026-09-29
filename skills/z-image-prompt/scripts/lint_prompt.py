#!/usr/bin/env python3
"""Lint a plain-text prompt for Z-Image Turbo (Tongyi-MAI), English or Chinese.

Usage:
    lint_prompt.py prompt.txt
    lint_prompt.py -            # read stdin
    echo "..." | lint_prompt.py -
Options:
    --max-words N         warn above N words when only the estimate is available (default 380)
    --fetch-tokenizer [DIR]
                          download Z-Image-Turbo's tokenizer (vocab.json and merges.txt, Apache-2.0,
                          about 4.4 MB) from Hugging Face into DIR, default ~/.cache/z-image-prompt/tokenizer, then
                          lint the prompt if one was given
    --tokenizer DIR       folder holding vocab.json and merges.txt for exact counting; without it
                          $ZIMAGE_TOKENIZER_DIR is tried, then the cache folder above
    --vocab V --merges M  an explicit byte-level BPE pair (Qwen2 family gives the true count;
                          a GPT-2-family pair comes close but keeps numbers whole where Qwen
                          splits them into digits)
    --no-bpe              ignore any vocabulary and use the word-based estimate
    --quiet               print only the verdict line
Exit codes: 0 clean, 1 findings, 2 input error.

Without tokenizer files the count is a word-based estimate (calibrated for English prose on the
same Qwen tokenizer, within about 7%); Chinese text is counted at one token per character.

The budget: the reference pipeline (Tongyi-MAI/Z-Image, src/zimage/pipeline.py) wraps the prompt in
Qwen3's chat template as a single user turn, "<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>
assistant\n" (8 tokens), and tokenizes it with max_length 512 and truncation, so the prompt itself
gets 504 tokens and the rest is dropped silently. Draw Things uses the same template without a
length cap, but the model was trained on the 512-token window, so the budget applies there too.

Checks are derived from the official prompt enhancer's system prompt (pe.py in the Tongyi-MAI
Z-Image-Turbo Space), the reference pipeline, and the guidance-free design of the Turbo checkpoint.
Standard library only, Python 3.8+.
"""
import argparse
import json
import os
import re
import sys

PROMPT_BUDGET = 504  # 512-token window minus the 8 tokens of the chat template around the prompt
TOKENIZER_FILES = ("vocab.json", "merges.txt")
TOKENIZER_URL = "https://huggingface.co/Tongyi-MAI/Z-Image-Turbo/resolve/main/tokenizer/"  # Qwen3 tokenizer
ENV_TOKENIZER_DIR = "ZIMAGE_TOKENIZER_DIR"

MEDIUM_WORDS = (
    "photograph", "photo", "photography", "photographic", "polaroid", "film still", "cinematic",
    "illustration", "illustrated", "painting", "painted", "painterly", "watercolor", "watercolour",
    "gouache", "oil on canvas", "acrylic", "ink", "pencil", "charcoal", "sketch", "drawing",
    "line art", "linework", "3d render", "3d rendered", "render", "rendered", "cgi", "octane",
    "anime", "manga", "cel", "cartoon", "comic", "pixel art", "vector", "flat-color", "flat color",
    "collage", "poster", "print", "risograph", "screen print", "screenprint", "woodcut", "linocut",
    "engraving", "etching", "lithograph", "airbrush", "digital painting", "concept art", "matte painting",
    "editorial", "portrait", "macro", "still life", "product shot", "product photo", "diorama",
    "claymation", "stop-motion", "paper cut", "papercraft", "embroidery", "mosaic", "stained glass",
    "logo", "icon", "typography", "infographic", "ui", "isometric", "blueprint", "sculpture", "statue",
    "35mm", "medium format", "kodak", "fuji", "ilford", "polaroid",
    "close-up", "close up", "closeup", "wide shot", "wide-angle", "low-angle", "high-angle", "aerial", "bird's-eye",
    "shot", "scene", "still", "frame", "landscape", "seascape", "cityscape", "stylized", "stylised", "surreal",
    "minimalist", "abstract", "vintage", "retro", "cinematic", "noir", "fantasy", "sci-fi", "brutalist", "baroque",
)
INSTRUCTION_RE = re.compile(
    r"^\s*(please\s+)?(generate|create|make|draw|render|design|produce|give me|show me|i want|i need|"
    r"i'd like|i would like|can you|could you|imagine|picture this|let's|depict)\b", re.I)
META_RE = re.compile(
    r"\b(in this (image|picture|photo|scene|illustration)|this (image|picture|photo|scene) (shows|depicts|features|is)|"
    r"the (image|picture|photo) (shows|depicts|features)|an image (of|showing|depicting)|a picture (of|showing))\b", re.I)
NEGATION_RE = re.compile(r"\b(no|not|without|never|don't|doesn't|isn't|aren't|avoid|nothing|none|free of|lacking)\b", re.I)
HEDGE_RE = re.compile(r"\b(or|maybe|perhaps|possibly|such as|various|some kind of|some sort of|either|etc\.?|and/or|optionally|might)\b", re.I)
WEIGHT_RE = re.compile(r"\(\s*[^()]+:\s*\d+(\.\d+)?\s*\)|\[[^\[\]]+\]|\b\w+\+{2,}|\{[^{}]+\}|<lora:[^>]+>|::\s*-?\d")
NEGATIVE_MARKER_RE = re.compile(r"(negative prompt\s*:|--no\b|--neg\b|\bneg:\s)", re.I)
QUALITY_TAGS = (
    "masterpiece", "杰作", "8k画质", "best quality", "high quality", "highest quality", "ultra detailed", "ultra-detailed",
    "highly detailed", "extremely detailed", "8k", "4k", "16k", "uhd", "hdr",
    "trending on artstation", "artstation", "award winning", "award-winning", "photorealistic masterpiece",
    "ultra realistic", "hyperrealistic", "hyper-realistic", "hyper detailed", "insanely detailed",
    "professional photography", "unreal engine", "octane render 8k", "sharp focus", "perfect composition",
    "stunning", "breathtaking", "beautiful", "gorgeous", "amazing", "epic", "awesome",
)
TEXT_CUE_RE = re.compile(
    r"\b(reads?|reading|says?|saying|titled|title|caption(ed)?|label(l?ed)?|lettering|letters|headline|slogan|"
    r"the words?|the text|text that|written|inscribed|inscription|printed with|sign(age)?|logo|typography|font|typeface|wordmark)\b", re.I)
QUOTED_RE = re.compile(r"[\"“”][^\"“”]{1,80}[\"“”]")
CAPS_RUN_RE = re.compile(r"\b[A-Z][A-Z0-9&'!.\-]{2,}(?:\s+[A-Z][A-Z0-9&'!.\-]{1,})*\b")
PLACEHOLDER_RE = re.compile(r"\[(insert|your|add|tbd|todo)[^\]]*\]|\blorem ipsum\b|\bTBD\b|\bTODO\b|<[^<>]{1,40}>", re.I)
SIMILE_RE = re.compile(r"\b(?:like (?:a|an|the)|as if|as though|resembling|reminiscent of|evoking|evokes)\b|仿佛|宛如|犹如|好像|就像|如同|似的", re.I)
MARKDOWN_RE = re.compile(r"^\s*([-*+]\s|#{1,6}\s|\d+[.)]\s|>\s)", re.M)


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


ESTIMATE_FACTOR = 1.07  # Qwen tokens per piece on English prose (calibrated on 20 prose prompts, same tokenizer)
ESTIMATE_BAND = 7  # percent: the largest error the estimate showed on those prompts


def estimate_tokens(text: str) -> int:
    """Estimate from pieces: letter runs, single digits (Qwen tokenizes numbers digit by digit) and
    punctuation marks, times ESTIMATE_FACTOR, plus one token per Chinese character. Calibrated on
    English prose with the same Qwen tokenizer; Chinese counts are rougher, fetch the tokenizer."""
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    pieces = re.findall(r"[A-Za-z]+|\d|[^\sA-Za-z\d\u3400-\u9fff]", text)
    return int(round(len(pieces) * ESTIMATE_FACTOR)) + cjk


def word_count(text: str) -> int:
    """Space-separated words, with Chinese counted at two characters per word."""
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    return len(re.sub(r"[\u3400-\u9fff]", " ", text).split()) + cjk // 2


def count_tokens(text: str, bpe=None):
    """Return (tokens, short_label, long_label)."""
    if bpe is not None:
        return bpe.count(text), bpe.short, bpe.label
    return estimate_tokens(text), "estimated", "estimated from words"


def default_tokenizer_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "z-image-prompt", "tokenizer")


def find_tokenizer_dir(explicit=None):
    """The first folder holding vocab.json and merges.txt among --tokenizer, $ZIMAGE_TOKENIZER_DIR, the cache."""
    for d in (explicit, os.environ.get(ENV_TOKENIZER_DIR), default_tokenizer_dir()):
        if d and all(os.path.isfile(os.path.join(d, f)) for f in TOKENIZER_FILES):
            return d
        if d == explicit and explicit:
            raise OSError(f"no vocab.json and merges.txt in {explicit}")
    return None


def fetch_tokenizer(dest=None):
    """Download Z-Image-Turbo's vocab.json and merges.txt into dest (default: the cache folder). Returns dest."""
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


def lint(text: str, max_words: int = 380, bpe=None):
    findings, hints = [], []
    text = text.strip()
    if not text:
        return ["prompt is empty"], []
    words = text.split()
    n_words = word_count(text)
    tokens, _, label = count_tokens(text, bpe)
    about = "" if bpe is not None else "about "

    # length
    if tokens > PROMPT_BUDGET:
        findings.append(f"{about}{tokens} tokens ({label}); the prompt gets {PROMPT_BUDGET} of the encoder's 512 tokens, so the reference pipeline drops the tail (~{tokens - PROMPT_BUDGET} tokens) and Draw Things feeds the model more than it was trained on. Cut the middle, keep the closing style attributes.")
    elif bpe is None and tokens > PROMPT_BUDGET - 40:
        hints.append(f"estimate of {tokens} tokens is within 40 of the {PROMPT_BUDGET}-token budget and can be {ESTIMATE_BAND}% off either way. Count exactly with Z-Image's tokenizer (run --fetch-tokenizer once), or trim a sentence.")
    elif bpe is None and n_words > max_words:
        findings.append(f"{n_words} words ({about}{tokens} tokens); above {max_words} you are near the {PROMPT_BUDGET}-token budget. Trim.")
    elif n_words < 4:
        hints.append(f"{n_words} words. Nothing expands the prompt outside the official Space's enhancer, so the model fills the gaps with its own taste; write the full description.")

    # form
    if text.lstrip().startswith(("{", "[")) or re.search(r"\"\s*:\s*[\"\[{\d]", text):
        findings.append("looks like JSON. Z-Image takes a plain description; write it as prose.")
    if MARKDOWN_RE.search(text):
        findings.append("bullets, headings or numbered lines found. The enhancer outputs one continuous description; no bullets or markdown.")
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        hints.append(f"{len(paragraphs)} paragraphs. The official examples are single paragraphs; join them unless a line break is the point.")

    # register
    m = INSTRUCTION_RE.search(text)
    if m:
        findings.append(f"opens with an instruction ('{m.group(0).strip()}'). The encoder reads the prompt as an image description; start with the medium or the subject.")
    m = META_RE.search(text)
    if m:
        (findings if text.lower().startswith(m.group(0).lower()) else hints).append(
            f"meta phrase '{m.group(0)}'. Captions describe the picture directly; an opener like this is the one form to avoid, mid-sentence it is harmless.")
    m = NEGATIVE_MARKER_RE.search(text)
    if m:
        findings.append(f"negative-prompt marker '{m.group(0).strip()}'. Turbo is guidance-free and ignores negatives; state what you want instead.")
    m = WEIGHT_RE.search(text)
    if m:
        findings.append(f"weighting or control syntax '{m.group(0)}'. It is plain text to the Qwen3 encoder; remove it and use word order and emphasis instead.")
    m = PLACEHOLDER_RE.search(text)
    if m:
        findings.append(f"placeholder '{m.group(0)}' left in the prompt.")

    # negation / hedges
    negs = sorted({x.lower() for x in NEGATION_RE.findall(text)})
    if negs:
        hints.append(f"negation words {negs}: there is no negative branch on Turbo, so 'no X' tends to put X in the image. Rephrase positively (an empty road, a clear sky).")
    hedges = sorted({x.lower() for x in HEDGE_RE.findall(text)})
    if hedges:
        hints.append(f"hedge words {hedges}: commit to one value per attribute; the model renders both halves of an 'or', and the enhancer's rule is concrete, unambiguous description.")
    similes = sorted({x.lower() for x in SIMILE_RE.findall(text) if x})
    if similes:
        hints.append(f"simile or metaphor {similes}: the enhancer bans metaphors and emotional rhetoric, and a compared object can appear in the picture. Say what the thing looks like in plain terms.")

    # quality tag soup
    low = text.lower()
    tags = [t for t in QUALITY_TAGS if re.search(r"\b" + re.escape(t) + r"\b", low)]
    if tags:
        hints.append(f"quality or meta tags {tags}: the enhancer forbids tags like '8K' and 'masterpiece'. Replace them with a concrete lens, light, material or process.")

    # text rendering
    quoted = QUOTED_RE.findall(text)
    has_cue = TEXT_CUE_RE.search(text)
    caps = [c for c in CAPS_RUN_RE.findall(text) if len(c) >= 3 and c not in ("HDR", "UHD", "CGI", "LED", "RGB", "USA", "UK", "NYC", "SUV", "DSLR", "ISO", "VHS", "CRT", "LCD", "DIY", "BMX", "MTB", "GPS", "ATM")]
    if has_cue and not quoted:
        findings.append(f"text cue '{has_cue.group(0)}' but nothing is in double quotes. The enhancer's rule: transcribe the words exactly and wrap them in English double quotes.")
    unquoted_caps = [c for c in caps if not any(c in q for q in quoted)]
    if unquoted_caps and not quoted:
        hints.append(f"all-caps run {unquoted_caps[:3]} outside quotes: if that is text to render, quote it; if not, lower-case it so it is not read as signage.")
    for q in quoted:
        inner = q[1:-1]
        if len(inner.split()) > 8:
            hints.append(f"quoted string {q} is {len(inner.split())} words; short strings render more reliably. Split it into separate quoted strings with their own placement.")

    # style early
    if n_words > 40 and not re.search(r"[\u3400-\u9fff]{20}", text):
        head = " ".join(words[:25]).lower()
        if not any(re.search(r"\b" + re.escape(w) + r"\b", head) for w in MEDIUM_WORDS):
            tail = " ".join(words[25:]).lower()
            found_later = any(re.search(r"\b" + re.escape(w) + r"\b", tail) for w in MEDIUM_WORDS)
            if found_later:
                hints.append("no medium or style word in the first 25 words, but there is one later. The official examples name the picture type up front (a medium-shot phone selfie, a vertical digital illustration); move it up.")
            else:
                hints.append("no medium or style word anywhere. Name one (photograph, illustration, 3D render, anime, risograph print...) or the model picks for you.")
    return findings, hints


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="prompt file, or - for stdin")
    ap.add_argument("--max-words", type=int, default=380)
    ap.add_argument("--fetch-tokenizer", nargs="?", const="", metavar="DIR",
                    help="download Z-Image-Turbo's vocab.json and merges.txt into DIR (default: the cache folder)")
    ap.add_argument("--tokenizer", metavar="DIR", help="folder holding vocab.json and merges.txt")
    ap.add_argument("--vocab", help="byte-level BPE vocab.json (GPT-2 or Qwen2 family)")
    ap.add_argument("--merges", help="matching merges.txt")
    ap.add_argument("--no-bpe", action="store_true", help="use the word-based estimate even if a vocabulary is available")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if bool(a.vocab) != bool(a.merges):
        print("error: --vocab and --merges go together", file=sys.stderr)
        return 2
    if a.fetch_tokenizer is not None:
        try:
            dest = fetch_tokenizer(a.fetch_tokenizer or None)
        except Exception as e:
            print(f"error: could not fetch the tokenizer: {e}", file=sys.stderr)
            return 2
        print(f"tokenizer files saved to {dest}")
        if a.path is None:
            return 0
        a.tokenizer = a.tokenizer or dest
    if a.path is None:
        ap.print_usage(file=sys.stderr)
        print("error: a prompt file (or -) is required", file=sys.stderr)
        return 2
    try:
        text = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8").read()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        bpe = None if a.no_bpe else load_bpe(a.vocab, a.merges, a.tokenizer)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    findings, hints = lint(text, a.max_words, bpe)
    n_words = word_count(text)
    tokens, short, _ = count_tokens(text.strip(), bpe)
    if not a.quiet:
        for f in findings:
            print(f"  - {f}")
        if findings and hints:
            print()
        for h in hints:
            print(f"  ~ {h}")
        if findings or hints:
            print()
    verdict = "OK" if not findings else f"{len(findings)} issue(s)"
    legend = "  [- issue to fix, ~ hint to weigh]" if (findings or hints) and not a.quiet else ""
    print(f"{verdict}: {n_words} words, {tokens} tokens ({short}) of the {PROMPT_BUDGET}-token prompt budget ({len(hints)} hint(s)){legend}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
