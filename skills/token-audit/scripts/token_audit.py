#!/usr/bin/env python3
"""Measure Claude Code token spend from local transcripts.

Usage:
    token_audit.py audit   [--projects GLOB] [--since T] [--until T] [--skip-session ID]... [--include-current]
                           [--git REPO]... [--issue-key PREFIX[,PREFIX]]... [--author TEXT]...
                           [--replay W1,W2,...] [--reread-calls N]
                           [--label TEXT] [--compare OLD.json] [--root DIR] [--out DIR]
    token_audit.py compare OLD.json NEW.json [--out DIR]
    token_audit.py probe   [--agents LIST] [--model MODEL] [--label TEXT] [--timeout S] [--out DIR]
    token_audit.py probe   --read SESSION_ID|current|latest [--label TEXT] [--root DIR] [--out DIR]
    token_audit.py note    TEXT [--date YYYY-MM-DD[THH:MM]] [--out DIR]

Model: every API call re-sends the whole context. Spend is expressed in input-token
equivalents (ITE) of the same model: input 1x, cache write 1h 2x, cache write 5m 1.25x,
cache read 0.1x, output 5x. An item added before call k is written to cache once and read
by every later call of the same context segment (until compaction).

Standard-library Python 3.8+.
"""
from __future__ import annotations

import argparse
import base64
import bisect
import collections
import datetime as dt
import fnmatch
import glob
import json
import os
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile

SCHEMA = 1
W_IN, W_CW5, W_CW1H, W_CR, W_OUT = 1.0, 1.25, 2.0, 0.1, 5.0
POST = 26_000        # post-compaction prefix used by the replay (system + summary)
SUMMARY_OUT = 6_600  # compaction summary size used by the replay
BANDS = [(0, 50_000), (50_000, 100_000), (100_000, 200_000), (200_000, 300_000),
         (300_000, 400_000), (400_000, None)]
HIGH_CTX = 300_000
REVIEW_RE = re.compile(r"review|simplif|inquisit|qualifier|verif", re.IGNORECASE)
APPLY_RE = re.compile(r"\b(fix|fixes|fixed|fixing|apply|applies)\b", re.IGNORECASE)
REVIEW_GAP = dt.timedelta(minutes=10)
READ_RE = re.compile(r"^\s*(?:cd [^;&]+(?:&&|;)\s*)*(cat|sed|head|tail|nl|awk)\b")
PATH_RE = re.compile(r"((?:/|\./|~/)?[\w.\-/~]+\.(swift|md|mjs|sh|json|yml|yaml|log|txt|jsonl|pbxproj|"
                     r"xcconfig|toml|plist|h|cpp|xcstrings|ips))")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
CLOSE_RE = re.compile(r"\b(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\b:?\s*"
                      r"((?:[\w.-]+/[\w.-]+)?#\d+)", re.IGNORECASE)
ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NOTE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")
CHANGE_LINE_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2})(T\d{2}:\d{2})? (.+)$")
CHANGES_HEADING = "# Configuration changes"
DEFAULT_REPLAY = "600000,400000,300000"
PROBE_PREFIX = "token-audit-probe-"
CURRENT_SESSION_VAR = "CLAUDE_CODE_SESSION_ID"
# Variables a Claude session exports to its tools. A headless probe started from inside a
# session would inherit them and run as that session's mode (Desktop entrypoint, app tools).
PROBE_ENV_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CLAUDE_PREVIEW_", "MCP_")
PROBE_ENV_NAMES = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT")
PROBE_ENV_KEEP = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
                  "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_SKIP_VERTEX_AUTH",
                  "CLAUDE_CODE_SKIP_FOUNDRY_AUTH", "CLAUDE_CODE_OAUTH_TOKEN")
DEFAULT_AGENTS = "reviewer,implementer-opus-medium,general-purpose:opus"
TOP_SESSIONS = 15
TOP_FAMILIES = 25
TOP_RUNS = 20


# ---------------------------------------------------------------- paths and time

def default_root():
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        return os.path.join(cfg, "projects")
    return os.path.expanduser("~/.claude/projects")


def default_out():
    return os.path.expanduser("~/.claude/token-audit")


def parse_ts(value):
    """Parse a transcript or command-line timestamp into an aware datetime (naive = local)."""
    if not isinstance(value, str) or not value:
        return None
    s = value.strip()
    if s[-1:] in ("Z", "z"):
        s = s[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)(.*)$", s)
        if not m:
            return None
        try:
            d = dt.datetime.fromisoformat(m.group(1) + "." + (m.group(2) + "000000")[:6] + m.group(3))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.astimezone()
    return d


def parse_bound(text, end):
    """Return (datetime, whole_day) for a --since / --until value."""
    if DATE_RE.match(text):
        day = dt.datetime.strptime(text, "%Y-%m-%d")
        if end:
            return (day + dt.timedelta(days=1)).astimezone() - dt.timedelta(microseconds=1), True
        return day.astimezone(), True
    value = parse_ts(text)
    if value is None:
        raise SystemExit("not a date or ISO timestamp: %r" % text)
    return value, False


def iso(d):
    return d.isoformat() if d is not None else None


def local_date(d):
    return d.astimezone().strftime("%Y-%m-%d")


def write_atomic(path, text):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------- item model

def png_tokens(b64):
    try:
        raw = base64.b64decode(b64[:200] + "=" * (-len(b64[:200]) % 4))
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", raw[16:24])
        else:
            return 1600
        # API downscales to <=1568 long edge / ~1.15MP
        scale = min(1.0, 1568 / max(w, h), (1_150_000 / (w * h)) ** 0.5)
        return int(w * scale * h * scale / 750)
    except Exception:
        return 1600


def bash_category(cmd):
    c = cmd.strip()
    c = re.sub(r"^(cd [^&;]+(&&|;)\s*)+", "", c)
    first = c.split()[0] if c.split() else ""
    if re.search(r"scripts/(precommit|test|build|lint|deadcode|format)\.sh", c):
        return "gate:" + re.search(r"scripts/(\w+)\.sh", c).group(1)
    if "scripts/run.sh" in c:
        return "app:run.sh"
    if re.search(r"\b(xcodebuild|swift (build|test))\b", c):
        return "build:xcodebuild/swift"
    if first in ("git",):
        sub = c.split()[1] if len(c.split()) > 1 else ""
        return "git " + sub
    if first == "gh":
        return "gh"
    if first in ("grep", "rg", "egrep") or re.match(r"^(grep|rg)\b", c):
        return "search:grep/rg"
    if first in ("find", "fd", "ls", "tree"):
        return "search:find/ls"
    if first in ("ast-grep", "sg"):
        return "search:ast-grep"
    if first in ("cat", "sed", "head", "tail", "nl", "awk", "wc"):
        return "read:cat/sed/head"
    if first in ("screencapture", "osascript", "swift") or "screencapture" in c or "osascript" in c:
        return "app:drive/screenshot"
    if first in ("codex",) or "codex exec" in c:
        return "codex"
    if first in ("node", "npm", "npx"):
        return "node"
    if first in ("python3", "python", "jq"):
        return "script:python/jq"
    if first in ("log", "plutil", "defaults", "ps", "lsof", "pgrep", "kill", "pkill", "sqlite3"):
        return "sys:inspect"
    return "other:" + first[:20]


def tool_label(name, inp):
    if name == "Bash":
        return "Bash/" + bash_category(str(inp.get("command", "")))
    if name.startswith("mcp__"):
        parts = name.split("__")
        extra = ""
        if len(parts) > 2 and parts[1] in ("codebase-memory-mcp", "Claude_Browser"):
            extra = "/" + parts[2]
        return "MCP/" + (parts[1] if len(parts) > 1 else "") + extra
    if name == "LSP":
        return "LSP/" + str(inp.get("operation", "?"))
    return name


def content_chars(content):
    """Return (text_chars, image_tokens) of a tool_result / message content."""
    if content is None:
        return 0, 0
    if isinstance(content, str):
        return len(content), 0
    chars, img = 0, 0
    for b in content:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            chars += len(b.get("text", ""))
        elif t == "image":
            img += png_tokens((b.get("source") or {}).get("data", ""))
        elif t == "tool_result":
            c, i = content_chars(b.get("content"))
            chars += c
            img += i
        elif t == "tool_reference":
            chars += 200
        else:
            chars += len(json.dumps(b))
    return chars, img


def ctx(c):
    return c["inp"] + c["cw"] + c["cr"]


def cw5m_of(c):
    # Without a cache_creation split, all of cache_creation_input_tokens counts as 5m.
    return c["cw5m"] if (c["cw1h"] + c["cw5m"]) else c["cw"]


def call_parts(c):
    return dict(input=c["inp"] * W_IN,
                cache_write=c["cw1h"] * W_CW1H + cw5m_of(c) * W_CW5,
                cache_read=c["cr"] * W_CR,
                output=c["out"] * W_OUT)


def call_ite(c):
    p = call_parts(c)
    return p["input"] + p["cache_write"] + p["cache_read"] + p["output"]


def call_input_ite(c):
    p = call_parts(c)
    return p["input"] + p["cache_write"] + p["cache_read"]


def first_ctx_call(calls):
    return next((c for c in calls if ctx(c) > 0), None)


# ---------------------------------------------------------------- transcripts

def read_meta(path):
    meta = path[:-len(".jsonl")] + ".meta.json"
    if os.path.exists(meta):
        try:
            with open(meta) as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def collect_files(root, projects="*", skips=()):
    """Main and subagent transcripts under root, deduplicated by basename as tokens.py does."""
    files = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    for name in names:
        proj = os.path.join(root, name)
        if not os.path.isdir(proj) or not fnmatch.fnmatchcase(name, projects):
            continue
        if PROBE_PREFIX in name:  # the headless probe's scratch folder: never part of an audit
            continue
        for f in sorted(glob.glob(os.path.join(proj, "*.jsonl"))):
            if any(s in f for s in skips):
                continue
            files.append((f, "main", {}))
        for f in sorted(glob.glob(os.path.join(proj, "*", "subagents", "*.jsonl"))):
            if any(s in f for s in skips):
                continue
            meta = read_meta(f)
            files.append((f, "sub:" + str(meta.get("agentType", "?")), meta))
    best = {}
    for f, k, meta in files:
        b = os.path.basename(f)
        if b not in best or best[b][1].endswith("?") or (k == "main" and best[b][1] != "main"):
            best[b] = (f, k, meta)
    return list(best.values())


def parse_transcript(path, kind, meta=None, since=None, until=None, select=True):
    """Parse one transcript. With select, return None unless its first timestamp is in
    [since, until]; events after until are ignored (custom titles stay)."""
    calls, items, pending, reads, edits = [], [], [], [], []
    tool_names, uses, seen = {}, {}, {}
    # Two segment counters. `seg` advances on every compact_boundary event, as tokens.py does;
    # the item model, calibration and replay use it, so they reproduce the lab baseline.
    # `comp_seg` advances only on a boundary uuid not seen before: some transcripts re-append
    # earlier boundaries (and the old messages after them), and those replayed copies are
    # not compactions. Compaction counts and re-reads use `comp_seg`.
    seg = comp_seg = 0
    boundary_ids = set()
    # File reads and edits are keyed by tool_use id, first occurrence wins: replayed copies
    # keep their ids, and counting them again would inflate re-reads and rework hints.
    # The item model above deliberately keeps tokens.py's behaviour.
    read_ids, edit_ids = set(), set()
    duplicate_boundaries = 0
    first_ts = last_ts = None
    title = version = entrypoint = None
    cut = False
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if not isinstance(e, dict):
                continue
            t = e.get("type")
            ts = parse_ts(e.get("timestamp")) if e.get("timestamp") else None
            if first_ts is None and ts is not None:
                first_ts = ts
                if select and ((since is not None and ts < since) or (until is not None and ts > until)):
                    return None
            if t == "custom-title":
                if e.get("customTitle"):
                    title = e["customTitle"]
                continue
            if until is not None:
                if ts is not None and ts > until:
                    cut = True
                    continue
                if ts is None and cut:
                    continue
            if ts is not None:
                last_ts = ts
            if version is None and e.get("version"):
                version = e["version"]
            if entrypoint is None and e.get("entrypoint"):
                entrypoint = e["entrypoint"]
            if t == "system" and e.get("subtype") == "compact_boundary":
                seg += 1
                bid = e.get("uuid")
                if bid and bid in boundary_ids:
                    duplicate_boundaries += 1
                else:
                    if bid:
                        boundary_ids.add(bid)
                    comp_seg += 1
                continue
            if t == "assistant":
                m = e.get("message") or {}
                mid = m.get("id") or e.get("uuid")
                u = m.get("usage") or {}
                cc = u.get("cache_creation") or {}
                if mid not in seen:
                    for it in pending:
                        it["call_idx"] = len(calls)
                    items.extend(pending)
                    pending = []
                    calls.append(dict(
                        inp=u.get("input_tokens", 0) or 0,
                        cw=u.get("cache_creation_input_tokens", 0) or 0,
                        cw1h=cc.get("ephemeral_1h_input_tokens", 0) or 0,
                        cw5m=cc.get("ephemeral_5m_input_tokens", 0) or 0,
                        cr=u.get("cache_read_input_tokens", 0) or 0,
                        out=u.get("output_tokens", 0) or 0,
                        model=m.get("model", "?"), seg=seg, comp_seg=comp_seg))
                    seen[mid] = len(calls) - 1
                    pending.append(dict(cat="assistant_output", label="assistant_output", chars=0, img=0))
                else:
                    c = calls[seen[mid]]
                    for k2, v2 in (("out", u.get("output_tokens")), ("inp", u.get("input_tokens")),
                                   ("cw", u.get("cache_creation_input_tokens")),
                                   ("cr", u.get("cache_read_input_tokens")),
                                   ("cw1h", cc.get("ephemeral_1h_input_tokens")),
                                   ("cw5m", cc.get("ephemeral_5m_input_tokens"))):
                        c[k2] = max(c[k2], v2 or 0)
                ci = seen[mid]
                for b in m.get("content") or []:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    name = b.get("name", "?")
                    inp = b.get("input") or {}
                    if not isinstance(inp, dict):
                        inp = {}
                    tid = b.get("id")
                    tool_names[tid] = tool_label(name, inp)
                    uses[tid] = (name, inp, ci)
                    if name == "Read":
                        tool_names[str(tid) + ":path"] = inp.get("file_path", "")
                    if name in EDIT_TOOLS:
                        target = inp.get("file_path") or inp.get("notebook_path")
                        if isinstance(target, str) and target and (tid is None or tid not in edit_ids):
                            edit_ids.add(tid)
                            edits.append(dict(path=os.path.normpath(target), call=ci))
                continue
            if t == "user":
                m = e.get("message") or {}
                c = m.get("content")
                if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            tid = b.get("tool_use_id")
                            ch, im = content_chars(b.get("content"))
                            lab = tool_names.get(tid, "?")
                            it = dict(cat="tool_result", label=lab, chars=ch, img=im)
                            if lab == "Read":
                                it["path"] = tool_names.get(str(tid) + ":path", "")
                            pending.append(it)
                            name, inp, ci = uses.get(tid, (None, {}, None))
                            target = None
                            if name == "Read":
                                target = inp.get("file_path", "")
                            elif name == "Bash":
                                cmd = inp.get("command", "")
                                if isinstance(cmd, str) and READ_RE.match(cmd):
                                    found = PATH_RE.findall(cmd)
                                    target = found[-1][0] if found else ""
                            if (isinstance(target, str) and target and ci is not None
                                    and (tid is None or tid not in read_ids)):
                                read_ids.add(tid)
                                reads.append(dict(path=os.path.normpath(target), chars=ch, img=im, call=ci))
                        elif isinstance(b, dict) and b.get("type") == "text":
                            pending.append(dict(cat="user_text", label="reminder/text in tool turn",
                                                chars=len(b.get("text", "")), img=0))
                else:
                    ch, im = content_chars(c)
                    lab = ("compact_summary" if e.get("isCompactSummary")
                           else ("meta" if e.get("isMeta") else "user_prompt"))
                    pending.append(dict(cat="user_text", label=lab, chars=ch, img=im))
                continue
            if t == "attachment":
                a = e.get("attachment") or {}
                at = a.get("type", "?")
                if at in ("prompt_snapshot",):
                    continue  # the system prompt itself: measured as baseline
                slim = {k: v for k, v in a.items() if k not in (
                    "names", "addedNames", "systemPrompt", "displayPath", "filename", "toolInputCopies")}
                pending.append(dict(cat="attachment", label="att/" + at, chars=len(json.dumps(slim)), img=0))
    if select and first_ts is None:
        return None
    meta = meta or {}
    base = os.path.basename(path)[:-len(".jsonl")]
    parts = os.path.normpath(path).split(os.sep)
    is_sub = kind != "main"
    parent = parts[-3] if is_sub and len(parts) >= 3 else None
    project = parts[-4] if is_sub and len(parts) >= 4 else (parts[-2] if len(parts) >= 2 else "")
    return dict(path=path, kind=kind, session=base, parent=parent, project=project,
                description=meta.get("description"), calls=calls, items=items, reads=reads, edits=edits,
                compactions=comp_seg, duplicate_boundaries=duplicate_boundaries, first_ts=first_ts, last_ts=last_ts, title=title, version=version,
                entrypoint=entrypoint)


def load_transcripts(root, projects, skips, since, until):
    out = []
    for f, k, meta in collect_files(root, projects, skips):
        s = parse_transcript(f, k, meta, since, until, select=True)
        if s is not None:
            out.append(s)
    return out


# ---------------------------------------------------------------- calibration and attribution

def calibrate(transcripts):
    """chars/token from intervals whose new content is only text tool results.
    Returns (R, intervals, p25, p75); R = 3.5 when no interval qualifies."""
    ratios = []
    for s in transcripts:
        calls, items = s["calls"], s["items"]
        by_call = collections.defaultdict(list)
        for it in items:
            by_call[it["call_idx"]].append(it)
        for k in range(1, len(calls)):
            if calls[k]["seg"] != calls[k - 1]["seg"]:
                continue
            its = [i for i in by_call[k] if i["cat"] != "assistant_output"]
            its = [i for i in its if i["cat"] != "attachment"]
            if not its or any(i["cat"] != "tool_result" or i["img"] for i in its):
                continue
            ch = sum(i["chars"] for i in its)
            d = ctx(calls[k]) - ctx(calls[k - 1]) - calls[k - 1]["out"]
            if ch > 4000 and d > 500:
                ratios.append(ch / d)
    if not ratios:
        return 3.5, 0, 3.5, 3.5
    r = statistics.median(ratios)
    if len(ratios) < 2:
        return r, len(ratios), r, r
    q = statistics.quantiles(ratios, n=4)
    return r, len(ratios), q[0], q[2]


def attribute(transcripts, r):
    """Lifetime ITE per (category, label), as tokens.py does."""
    agg = collections.defaultdict(collections.Counter)
    for s in transcripts:
        calls, items = s["calls"], s["items"]
        if not calls:
            continue
        seg_calls = collections.defaultdict(list)
        for i, c in enumerate(calls):
            seg_calls[c["seg"]].append(i)
        out_total = 0.0
        out_tok = 0
        for c in calls:
            out_total += c["out"] * W_OUT
            out_tok += c["out"]
        for it in items:
            k = it["call_idx"]
            if it["cat"] == "assistant_output":
                tok = calls[k - 1]["out"] if k > 0 else 0
            else:
                tok = it["chars"] / r + it["img"]
            idxs = seg_calls[calls[k]["seg"]]
            reads = len(idxs) - bisect.bisect_left(idxs, k)
            if reads == 0:
                continue
            ite = tok * (W_CW1H + W_CR * (reads - 1))
            v = agg[(it["cat"], it["label"])]
            v["ite"] += ite
            v["tok"] += tok
            v["n"] += 1
        first_items = collections.defaultdict(float)
        for i in items:
            if i["cat"] != "assistant_output":
                first_items[i["call_idx"]] += i["chars"] / r + i["img"]
        for seg, idxs in seg_calls.items():
            c0 = calls[idxs[0]]
            base = max(0, ctx(c0) - first_items.get(idxs[0], 0.0))
            ite = base * (W_CR * len(idxs)) + base * (W_CW1H - W_CR)
            key = ("baseline", "system+tools+CLAUDE.md (seg start)" if seg == 0 else "post-compaction prefix")
            agg[key]["ite"] += ite
            agg[key]["tok"] += base
            agg[key]["n"] += 1
        agg[("output", "generated tokens x5")]["ite"] += out_total
        agg[("output", "generated tokens x5")]["tok"] += out_tok
    return agg


def rollup(agg):
    fam = collections.Counter()
    famn = collections.Counter()
    for (cat, lab), v in agg.items():
        if cat == "tool_result":
            f = lab.split("/")[0]
            if lab.startswith("Bash/"):
                f = "Bash/" + lab.split("/")[1].split(":")[0]
        else:
            f = cat
        fam[f] += v["ite"]
        famn[f] += v["n"]
    total = sum(v["ite"] for v in agg.values())
    rows = [dict(family=f, ite=v, n=int(famn[f]), share=(v / total if total else 0.0))
            for f, v in sorted(fam.items(), key=lambda kv: (-kv[1], kv[0]))]
    return rows, total


# ---------------------------------------------------------------- replay

def replay(calls, cap, penalty, post=POST, summary_out=SUMMARY_OUT):
    """Replay observed context growth under an auto-compaction cap (port of simcompact.sim)."""
    cur = None
    spend = 0.0
    ncomp = 0
    prev_seg = None
    prev_ctx = None
    for c in calls:
        real = c["inp"] + c["cw"] + c["cr"]
        if cur is None:
            cur = real
            growth = real
        else:
            g = real - prev_ctx if c["seg"] == prev_seg else 0  # observed compaction: keep simulated ctx
            growth = max(0, g)
            cur += growth
        prev_ctx, prev_seg = real, c["seg"]
        if cur > cap:
            ncomp += 1
            spend += cur * 0.1 + summary_out * 5 + post * 2  # summarise, write new prefix
            cur = post + penalty
            growth = penalty
        spend += (cur - growth) * 0.1 + growth * 2 + c["out"] * 5
    return spend, ncomp


# ---------------------------------------------------------------- statistics helpers

def stats_of(values):
    if not values:
        return None
    return dict(n=len(values), median=statistics.median(values), min=min(values), max=max(values))


def ratio(a, b):
    return a / b if b else 0.0


def transcript_summary(s):
    calls = s["calls"]
    fc = first_ctx_call(calls)
    return dict(ite=sum(call_ite(c) for c in calls), calls=len(calls),
                ctx_sum=sum(ctx(c) for c in calls), first_ctx=ctx(fc) if fc else None, first_call=fc)


def is_review_agent(s):
    """agentType `reviewer`, or a review-like description on an agent that does not implement
    or apply the findings (implementer types and "fix"/"apply" descriptions are excluded)."""
    agent_type = s["kind"][len("sub:"):]
    if agent_type == "reviewer":
        return True
    desc = s["description"] or ""
    return bool(REVIEW_RE.search(desc)) and "implement" not in agent_type.lower() and not APPLY_RE.search(desc)


def compaction_rows(s, r, n_calls):
    calls = s["calls"]
    seg_start = {}
    for i, c in enumerate(calls):
        seg_start.setdefault(c["comp_seg"], i)

    def pos(ci):
        return ci - seg_start[calls[ci]["comp_seg"]]

    rows = []
    for b in range(1, s["compactions"] + 1):
        before_reads = {x["path"] for x in s["reads"] if calls[x["call"]]["comp_seg"] < b}
        before_edits = {x["path"] for x in s["edits"] if calls[x["call"]]["comp_seg"] < b}
        seg_reads = [x for x in s["reads"] if calls[x["call"]]["comp_seg"] == b and x["path"] in before_reads]
        window = sum(x["chars"] / r + x["img"] for x in seg_reads if pos(x["call"]) < n_calls)
        segment = sum(x["chars"] / r + x["img"] for x in seg_reads)
        rework = sum(1 for x in s["edits"] if calls[x["call"]]["comp_seg"] == b and pos(x["call"]) < n_calls
                     and x["path"] in before_edits)
        post = first_ctx_call([c for c in calls if c["comp_seg"] == b])
        rows.append(dict(session=s["session"], kind=s["kind"], boundary=b, reread_window=window,
                         reread_segment=segment, rework_hint=rework,
                         post_prefix=ctx(post) if post else None,
                         has_calls=any(c["comp_seg"] == b for c in calls)))
    return rows


def parse_issue_keys(values):
    """Flatten repeatable, comma-separated --issue-key values into validated prefixes."""
    keys = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if not ISSUE_KEY_RE.match(part):
                raise SystemExit("--issue-key %r is not a ticket prefix (uppercase letter, then "
                                 "uppercase letters, digits or _): e.g. --issue-key IDP" % part)
            if part not in keys:
                keys.append(part)
    if values and not keys:
        raise SystemExit("--issue-key needs at least one prefix")
    return keys


def git_window(transcripts, since, until, until_given):
    """Bounds for git log: a missing bound comes from the selected transcripts (None if none)."""
    if since is None:
        firsts = [s["first_ts"] for s in transcripts if s["first_ts"] is not None]
        since = min(firsts) if firsts else None
    if not until_given:
        lasts = [s["last_ts"] or s["first_ts"] for s in transcripts if (s["last_ts"] or s["first_ts"]) is not None]
        until = max(lasts) if lasts else None
    return since, until


def git_metrics(repos, since, until, authors=(), issue_keys=()):
    """Count commits on HEAD between since and until (both required: None runs no git log)."""
    commits = closing = ticket_commits = 0
    issues = set()
    tickets = set()
    key_re = (re.compile(r"\b(?:" + "|".join(re.escape(k) for k in issue_keys) + r")-\d+\b")
              if issue_keys else None)
    for repo in repos if since is not None and until is not None else []:
        cmd = ["git", "-C", repo, "log", "HEAD", "--format=%H%x00%cI%x00%B%x1e"]
        cmd.append("--since=" + since.replace(microsecond=0).isoformat())
        cmd.append("--until=" + until.replace(microsecond=0).isoformat())
        cmd.extend("--author=" + a for a in authors)
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if proc.returncode != 0:
            raise SystemExit("git log failed in %s: %s" % (repo, proc.stderr.strip()))
        for rec in proc.stdout.split("\x1e"):
            rec = rec.strip("\n")
            if not rec.strip():
                continue
            parts = rec.split("\x00", 2)
            body = parts[2] if len(parts) > 2 else ""
            commits += 1
            refs = CLOSE_RE.findall(body)
            if refs:
                closing += 1
            for ref in refs:
                issues.add((os.path.abspath(repo) if ref.startswith("#") else "", ref.lower()))
            if key_re is not None:
                keys = key_re.findall(body)
                if keys:
                    ticket_commits += 1
                    tickets.update(keys)  # a ticket key is global: deduplicated across repositories
    out = dict(repos=[os.path.abspath(r) for r in repos], since=iso(since), until=iso(until),
               authors=list(authors), issue_keys=list(issue_keys), commits=commits, closing_commits=closing,
               closed_issues=len(issues), issues=sorted([list(x) for x in issues]),
               tickets_touched=None, ticket_commits=None, tickets=None)
    if key_re is not None:
        out.update(tickets_touched=len(tickets), ticket_commits=ticket_commits, tickets=sorted(tickets))
    return out


# ---------------------------------------------------------------- audit

def report_name(since, until, until_whole, label):
    s = "all" if since is None else local_date(since)
    u = local_date(until)
    if not until_whole:
        u += until.astimezone().strftime("T%H%M")
    return s + "_" + u + ("_" + label if label else "")


def build_report(transcripts, args, since, until, until_whole):
    r, n_int, p25, p75 = calibrate(transcripts)
    summ = {id(s): transcript_summary(s) for s in transcripts}
    mains = [s for s in transcripts if s["kind"] == "main"]
    subs = [s for s in transcripts if s["kind"] != "main"]

    def group(ss):
        g = collections.Counter()
        for s in ss:
            for c in s["calls"]:
                for k, v in call_parts(c).items():
                    g[k] += v
                g["calls"] += 1
                g["ctx_sum"] += ctx(c)
        ite = g["input"] + g["cache_write"] + g["cache_read"] + g["output"]
        return dict(ite=ite, input=g["input"], cache_write=g["cache_write"], cache_read=g["cache_read"],
                    output=g["output"], calls=int(g["calls"]), ctx_sum=g["ctx_sum"],
                    avg_ctx=ratio(g["ctx_sum"], g["calls"]),
                    transcripts=sum(1 for s in ss if s["calls"]))

    spend = dict(all=group(transcripts), main=group(mains), sub=group(subs))
    grand = spend["all"]["ite"]

    def bands(ss):
        rows = [dict(lo=lo, hi=hi, calls=0, ite=0.0) for lo, hi in BANDS]
        total = 0.0
        high = 0.0
        for s in ss:
            for c in s["calls"]:
                x, v = ctx(c), call_ite(c)
                total += v
                if x >= HIGH_CTX:
                    high += v
                for row in rows:
                    if x >= row["lo"] and (row["hi"] is None or x < row["hi"]):
                        row["calls"] += 1
                        row["ite"] += v
        for row in rows:
            row["share"] = ratio(row["ite"], total)
        return rows, ratio(high, total)

    band_all, high_all = bands(transcripts)
    band_main, high_main = bands(mains)

    kinds = {}
    by_ep = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in transcripts:
        sm = summ[id(s)]
        k = kinds.setdefault(s["kind"], dict(sessions=0, calls=0, ite=0.0, ctx_sum=0, first=[]))
        if s["calls"]:
            k["sessions"] += 1
        k["calls"] += sm["calls"]
        k["ite"] += sm["ite"]
        k["ctx_sum"] += sm["ctx_sum"]
        if sm["first_ctx"] is not None:
            k["first"].append(sm["first_ctx"])
            by_ep[s["kind"]][s["entrypoint"] or "?"].append(sm["first_ctx"])
    kinds_out = {}
    for kind, k in sorted(kinds.items(), key=lambda kv: -kv[1]["ite"]):
        kinds_out[kind] = dict(sessions=k["sessions"], calls=k["calls"], ite=k["ite"], share=ratio(k["ite"], grand),
                               avg_ctx=ratio(k["ctx_sum"], k["calls"]), first_ctx=stats_of(k["first"]))
    first_by_ep = {kind: {ep: stats_of(v) for ep, v in sorted(eps.items())} for kind, eps in sorted(by_ep.items())}

    # compactions
    n_calls = args.reread_calls
    comp_rows = []
    for s in mains:
        comp_rows.extend(compaction_rows(s, r, n_calls))
    with_calls = [x for x in comp_rows if x["has_calls"]]
    windows = [x["reread_window"] for x in with_calls]
    post = [x["post_prefix"] for x in comp_rows if x["post_prefix"] is not None]
    main_with_calls = [s for s in mains if s["calls"]]
    compactions = dict(
        total=sum(s["compactions"] for s in transcripts),
        main=sum(s["compactions"] for s in mains),
        sub=sum(s["compactions"] for s in subs),
        main_sessions_with=sum(1 for s in mains if s["compactions"]),
        duplicates_ignored=sum(s["duplicate_boundaries"] for s in transcripts),
        per_main_session=ratio(sum(s["compactions"] for s in main_with_calls), len(main_with_calls)),
        post_prefix_median=statistics.median(post) if post else None,
        reread=dict(calls_window=n_calls, n=len(with_calls),
                    median=statistics.median(windows) if windows else None,
                    mean=statistics.mean(windows) if windows else None,
                    max=max(windows) if windows else None,
                    segment_mean=statistics.mean([x["reread_segment"] for x in with_calls]) if with_calls else None,
                    rework_total=sum(x["rework_hint"] for x in comp_rows)),
        list=comp_rows)

    # review runs
    review_agents = [s for s in subs if is_review_agent(s)]
    by_parent = collections.defaultdict(list)
    for s in review_agents:
        by_parent[s["parent"]].append(s)
    runs = []
    for parent, agents in by_parent.items():
        agents.sort(key=lambda s: s["first_ts"])
        current = None
        for s in agents:
            if current is None or s["first_ts"] > current["latest"] + REVIEW_GAP:
                current = dict(parent=parent, start=s["first_ts"], latest=s["last_ts"] or s["first_ts"], members=[])
                runs.append(current)
            current["members"].append(s)
            current["latest"] = max(current["latest"], s["last_ts"] or s["first_ts"])
    run_rows = []
    for run in sorted(runs, key=lambda x: x["start"]):
        ite = prefix = 0.0
        types = collections.Counter()
        for s in run["members"]:
            sm = summ[id(s)]
            ite += sm["ite"]
            types[s["kind"][4:]] += 1
            fc = sm["first_call"]
            if fc is not None:
                prefix += call_input_ite(fc) + W_CR * ctx(fc) * (sm["calls"] - 1)
        run_rows.append(dict(parent=run["parent"], start=iso(run["start"]), agents=len(run["members"]),
                             types=dict(types), ite=ite, prefix=prefix, prefix_share=ratio(prefix, ite)))
    run_ite = [x["ite"] for x in run_rows]
    review = dict(runs=run_rows, summary=dict(
        runs=len(run_rows), ite=sum(run_ite), share=ratio(sum(run_ite), grand),
        median=statistics.median(run_ite) if run_ite else None,
        mean=statistics.mean(run_ite) if run_ite else None,
        max=max(run_ite) if run_ite else None,
        prefix_share=ratio(sum(x["prefix"] for x in run_rows), sum(run_ite))))

    # replay
    replay_windows = [int(w) for w in args.replay.split(",") if w.strip()]
    penalties = [0, 30_000, 60_000]
    if compactions["reread"]["median"] is not None:
        measured = int(round(compactions["reread"]["median"]))
        if measured not in penalties:
            penalties.append(measured)
    main_ite = spend["main"]["ite"]
    rows = []
    for penalty in penalties:
        ref = None
        for w in replay_windows:
            cap = int(round(0.95 * w))
            res = [replay(s["calls"], cap, penalty) for s in main_with_calls]
            ite = sum(x[0] for x in res)
            if ref is None:
                ref = ite
            rows.append(dict(window=w, cap=cap, penalty=penalty, ite=ite, compactions=sum(x[1] for x in res),
                             delta_main=ratio(ite - ref, main_ite), delta_total=ratio(ite - ref, grand)))
    replay_out = dict(reference=replay_windows[0] if replay_windows else None, windows=replay_windows,
                      penalties=penalties, post=POST, summary_out=SUMMARY_OUT, rows=rows)

    agg = attribute(transcripts, r)
    families, attributed = rollup(agg)
    attribution = dict(chars_per_token=r, calibrated=n_int > 0, intervals=n_int, p25=p25, p75=p75,
                       attributed_total=attributed, families=families)

    git = None
    if args.git:
        git_since, git_until = git_window(transcripts, since, until, bool(args.until))
        git = git_metrics(args.git, git_since, git_until, args.author, args.issue_keys)
        git["ite_per_commit"] = grand / git["commits"] if git["commits"] else None
        git["ite_per_issue"] = grand / git["closed_issues"] if git["closed_issues"] else None
        git["ite_per_ticket"] = grand / git["tickets_touched"] if git["tickets_touched"] else None

    main_rows = []
    comp_by_session = collections.Counter()
    for s in sorted(main_with_calls, key=lambda s: -summ[id(s)]["ite"]):
        sm = summ[id(s)]
        comp_by_session[s["session"]] = s["compactions"]
        main_rows.append(dict(session=s["session"], project=s["project"], title=s["title"],
                              first=iso(s["first_ts"]), last=iso(s["last_ts"]),
                              first_date=local_date(s["first_ts"]), entrypoint=s["entrypoint"],
                              version=s["version"], ite=sm["ite"], share=ratio(sm["ite"], grand),
                              calls=sm["calls"], avg_ctx=ratio(sm["ctx_sum"], sm["calls"]),
                              compactions=s["compactions"]))

    first_seen = [s["first_ts"] for s in transcripts]
    eff_since = since if since is not None else (min(first_seen) if first_seen else until)
    days = max((until - eff_since).total_seconds() / 86400.0, 0.0)
    selection = dict(
        projects=args.projects, skip_sessions=list(args.skip_session),
        transcripts=dict(sorted(collections.Counter(s["kind"] for s in transcripts).items())),
        versions=dict(sorted(collections.Counter(s["version"] or "?" for s in mains).items())),
        entrypoints=dict(sorted(collections.Counter(s["entrypoint"] or "?" for s in mains).items())))
    return dict(
        schema=SCHEMA, created=dt.datetime.now().astimezone().isoformat(), host=platform.node(),
        name=report_name(since, until, until_whole, args.label),
        window=dict(since=iso(since), until=iso(until), until_whole_day=until_whole,
                    since_date=local_date(since) if since is not None else None,
                    until_date=local_date(until), days=days),
        args=dict(projects=args.projects, since=args.since, until=args.until, skip_session=list(args.skip_session),
                  include_current=args.include_current, git=list(args.git), author=list(args.author),
                  issue_key=list(args.issue_key), replay=args.replay, reread_calls=args.reread_calls, label=args.label,
                  root=args.root, compare=args.compare),
        selection=selection, spend=spend,
        bands=dict(all=band_all, main=band_main), share_300k=dict(all=high_all, main=high_main),
        kinds=kinds_out, first_ctx_by_entrypoint=first_by_ep, review=review, compactions=compactions,
        replay=replay_out, attribution=attribution, git=git, main_sessions=main_rows)


# ---------------------------------------------------------------- rendering

def tok(v):
    if v is None:
        return "-"
    a = abs(v)
    if a >= 1e6:
        return "%.1fM" % (v / 1e6)
    if a >= 1e3:
        return "%.1fk" % (v / 1e3)
    return "%.0f" % v


def pct(v):
    return "-" if v is None else "%.1f%%" % (v * 100)


def counts(d):
    return ", ".join("%s %s" % (k, v) for k, v in d.items()) or "none"


def band_label(lo, hi):
    return "%dk-%s" % (lo // 1000, "%dk" % (hi // 1000) if hi is not None else "")


def render_report(rep):
    w = rep["window"]
    sel = rep["selection"]
    L = []
    L.append("Token audit %s" % rep["name"])
    L.append("Window: %s .. %s (%.1f days)" % (w["since"] or "unbounded", w["until"], w["days"]))
    L.append("Projects: %s" % sel["projects"])
    L.append("Skipped sessions: %s" % (", ".join(sel["skip_sessions"]) or "none"))
    L.append("Transcripts selected: %s" % counts(sel["transcripts"]))
    L.append("CLI versions (main sessions): %s" % counts(sel["versions"]))
    L.append("Entrypoints (main sessions): %s" % counts(sel["entrypoints"]))

    sp = rep["spend"]
    L.append("")
    L.append("== Direct spend (ITE = input-token equivalents) ==")
    L.append("cost model: input 1x, cache write 1h 2x, cache write 5m 1.25x, cache read 0.1x, output 5x")
    for grp in ("all", "main", "sub"):
        g = sp[grp]
        L.append("%-5s calls %7d  spend %8s  input %7s  cache_write %7s  cache_read %7s  output %7s  avg ctx %7s"
                 % (grp, g["calls"], tok(g["ite"]), tok(g["input"]), tok(g["cache_write"]), tok(g["cache_read"]),
                    tok(g["output"]), tok(g["avg_ctx"])))
    L.append("total spend %s ITE" % tok(sp["all"]["ite"]))

    L.append("")
    L.append("== Spend by context size at the call ==")
    L.append("%-10s %15s %15s" % ("band", "all", "main"))
    for a, m in zip(rep["bands"]["all"], rep["bands"]["main"]):
        L.append("%-10s %6d %7s %6d %7s" % (band_label(a["lo"], a["hi"]), a["calls"], pct(a["share"]),
                                            m["calls"], pct(m["share"])))
    L.append("share of spend at context >= 300k: all %s, main %s"
             % (pct(rep["share_300k"]["all"]), pct(rep["share_300k"]["main"])))

    L.append("")
    L.append("== Top main sessions ==")
    for s in rep["main_sessions"][:TOP_SESSIONS]:
        L.append("%8s %6s  calls %5d  avg ctx %7s  compactions %2d  %s  %-14s  %s"
                 % (tok(s["ite"]), pct(s["share"]), s["calls"], tok(s["avg_ctx"]), s["compactions"],
                    s["first_date"], (s["entrypoint"] or "?")[:14], (s["title"] or s["session"])[:60]))

    L.append("")
    L.append("== Per agent type ==")
    L.append("%-32s %5s %6s %8s %6s %8s  first-call context median / min / max" %
             ("kind", "sess", "calls", "ITE", "share", "avg ctx"))
    for kind, k in rep["kinds"].items():
        fc = k["first_ctx"]
        first = "%s / %s / %s" % (tok(fc["median"]), tok(fc["min"]), tok(fc["max"])) if fc else "-"
        L.append("%-32s %5d %6d %8s %6s %8s  %s" % (kind[:32], k["sessions"], k["calls"], tok(k["ite"]),
                                                   pct(k["share"]), tok(k["avg_ctx"]), first))
    L.append("first-call context by entrypoint:")
    for kind, eps in rep["first_ctx_by_entrypoint"].items():
        for ep, st in eps.items():
            L.append("  %-32s %-16s n=%-4d median %7s  min %7s  max %7s"
                     % (kind[:32], ep[:16], st["n"], tok(st["median"]), tok(st["min"]), tok(st["max"])))

    rv = rep["review"]
    rs = rv["summary"]
    L.append("")
    L.append("== Review runs ==")
    L.append("runs %d, ITE %s (%s of total), per run median %s, mean %s, max %s; prefix share %s"
             % (rs["runs"], tok(rs["ite"]), pct(rs["share"]), tok(rs["median"]), tok(rs["mean"]), tok(rs["max"]),
                pct(rs["prefix_share"])))
    for run in sorted(rv["runs"], key=lambda x: -x["ite"])[:TOP_RUNS]:
        types = ", ".join("%s x%d" % (t, n) for t, n in sorted(run["types"].items()))
        L.append("  %s  %s  agents %3d  ITE %8s  prefix %6s  %s"
                 % (run["start"][:16], run["parent"], run["agents"], tok(run["ite"]), pct(run["prefix_share"]), types))

    cp = rep["compactions"]
    rr = cp["reread"]
    L.append("")
    L.append("== Compactions and post-compaction re-reads ==")
    L.append("compactions %d (main %d, sub %d); main sessions with one %d; per main session %.2f; "
             "median post-compaction prefix %s" % (cp["total"], cp["main"], cp["sub"], cp["main_sessions_with"],
                                                   cp["per_main_session"], tok(cp["post_prefix_median"])))
    L.append("replayed (duplicate) compact boundaries ignored: %d" % cp["duplicates_ignored"])
    L.append("re-read per main compaction, first %d calls (%d compactions with a following call): median %s, "
             "mean %s, max %s; whole segment mean %s; rework hints %d"
             % (rr["calls_window"], rr["n"], tok(rr["median"]), tok(rr["mean"]), tok(rr["max"]),
                tok(rr["segment_mean"]), rr["rework_total"]))
    for x in cp["list"]:
        L.append("  %s  #%d  re-read %7s  segment %7s  rework %d  post prefix %7s"
                 % (x["session"], x["boundary"], tok(x["reread_window"]), tok(x["reread_segment"]),
                    x["rework_hint"], tok(x["post_prefix"])))

    rp = rep["replay"]
    L.append("")
    L.append("== Compaction replay (main sessions; cap = 0.95 x window; post prefix %s, summary %s) =="
             % (tok(rp["post"]), tok(rp["summary_out"])))
    L.append("reference window %s; change in %% of main ITE and of grand total" % tok(rp["reference"]))
    for x in rp["rows"]:
        L.append("  window %6s  cap %6s  penalty %6s  ITE %8s  compactions %4d  %+6.1f%% main  %+6.1f%% total"
                 % (tok(x["window"]), tok(x["cap"]), tok(x["penalty"]), tok(x["ite"]), x["compactions"],
                    x["delta_main"] * 100, x["delta_total"] * 100))

    at = rep["attribution"]
    L.append("")
    L.append("== Content attribution ==")
    if at["calibrated"]:
        L.append("chars/token calibration: median %.2f over %d intervals (p25 %.2f, p75 %.2f)"
                 % (at["chars_per_token"], at["intervals"], at["p25"], at["p75"]))
    else:
        L.append("chars/token calibration: uncalibrated, using %.2f" % at["chars_per_token"])
    L.append("attributed total %s (lifetime ITE of items) vs direct spend %s"
             % (tok(at["attributed_total"]), tok(sp["all"]["ite"])))
    L.append("Rollup by tool family:")
    for f in at["families"][:TOP_FAMILIES]:
        L.append("%6.2f%%  %8.2fM  n=%6d  %s" % (f["share"] * 100, f["ite"] / 1e6, f["n"], f["family"]))

    L.append("")
    L.append("== Git ==")
    g = rep["git"]
    if g is None:
        L.append("no --git repository given")
    else:
        L.append("HEAD commits from %s to %s; author filter: %s"
                 % (g.get("since") or "-", g.get("until") or "-",
                    ", ".join(g.get("authors") or []) or "none"))
        L.append("commits %d, closing commits %d, distinct closed issues %d"
                 % (g["commits"], g["closing_commits"], g["closed_issues"]))
        if g.get("issue_keys"):
            L.append("tickets touched %d (prefixes %s), commits mentioning one %d"
                     % (g["tickets_touched"], ", ".join(g["issue_keys"]), g["ticket_commits"]))
        if g["ite_per_commit"] is not None:
            L.append("ITE per commit %s" % tok(g["ite_per_commit"]))
        if g["ite_per_issue"] is not None:
            L.append("ITE per closed issue %s" % tok(g["ite_per_issue"]))
        if g.get("ite_per_ticket") is not None:
            L.append("ITE per ticket touched %s" % tok(g["ite_per_ticket"]))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- changes log and compare

def read_changes(out):
    path = os.path.join(out, "changes.md")
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as fh:
        for line in fh:
            m = CHANGE_LINE_RE.match(line.rstrip("\n"))
            if not m:
                continue
            try:
                day = dt.date.fromisoformat(m.group(1))
            except ValueError:
                continue
            entries.append((day, m.group(1) + (m.group(2) or ""), m.group(3)))
    return entries


def metrics(rep):
    """Ordered label -> (value, unit) used by compare; unit is 'n', 'ratio' or 'share'."""
    out = collections.OrderedDict()
    sp = rep["spend"]
    out["ITE per day of window"] = (ratio(sp["all"]["ite"], rep["window"]["days"]) if rep["window"]["days"] else None, "n")
    out["ITE per main session"] = (ratio(sp["main"]["ite"], sp["main"]["transcripts"]) if sp["main"]["transcripts"] else None, "n")
    out["ITE per subagent"] = (ratio(sp["sub"]["ite"], sp["sub"]["transcripts"]) if sp["sub"]["transcripts"] else None, "n")
    g = rep.get("git")
    out["ITE per commit"] = (g["ite_per_commit"] if g else None, "n")
    out["ITE per closed issue"] = (g["ite_per_issue"] if g else None, "n")
    if g and g.get("issue_keys"):
        out["ITE per ticket touched"] = (g.get("ite_per_ticket"), "n")
    out["average main context"] = (sp["main"]["avg_ctx"] if sp["main"]["calls"] else None, "n")
    out["share >= 300k (all)"] = (rep["share_300k"]["all"], "share")
    out["share >= 300k (main)"] = (rep["share_300k"]["main"], "share")
    for kind, k in rep["kinds"].items():
        if k["first_ctx"]:
            out["median first-call context %s" % kind] = (k["first_ctx"]["median"], "n")
    for kind, eps in rep["first_ctx_by_entrypoint"].items():
        for ep, st in eps.items():
            out["median first-call context %s @ %s" % (kind, ep)] = (st["median"], "n")
    rs = rep["review"]["summary"]
    out["review-run median ITE"] = (rs["median"], "n")
    out["review prefix share"] = (rs["prefix_share"] if rs["runs"] else None, "share")
    cp = rep["compactions"]
    out["compactions per main session"] = (cp["per_main_session"] if sp["main"]["transcripts"] else None, "ratio")
    out["median re-read per compaction"] = (cp["reread"]["median"], "n")
    for x in rep["replay"]["rows"]:
        out["replay %s penalty %s (%% of total)" % (tok(x["window"]), tok(x["penalty"]))] = (x["delta_total"], "share")
    return out


def change_text(old, new, unit):
    if old == new:
        return "0"
    if unit == "share":
        return "%+.1f pt" % ((new - old) * 100)
    if old:
        return "%+.1f%%" % ((new - old) / abs(old) * 100)
    return "n/a"


def value_text(v, unit):
    if unit == "share":
        return pct(v)
    if unit == "ratio":
        return "%.2f" % v
    return tok(v)


def git_filters(rep):
    g = rep.get("git") or {}
    return (tuple(sorted(g.get("repos") or [])), tuple(sorted(g.get("authors") or [])),
            tuple(sorted(g.get("issue_keys") or [])))


def git_filters_text(rep):
    repos, authors, keys = git_filters(rep)
    return "repos %s, authors %s, issue keys %s" % (", ".join(repos) or "none", ", ".join(authors) or "none",
                                                     ", ".join(keys) or "none")


def compare_reports(old, new, changes):
    """Return (text, rows) where rows are (label, old, new) for metrics present in both."""
    L = ["Comparison: %s -> %s" % (old.get("name"), new.get("name"))]
    if old.get("host") != new.get("host"):
        L.append("WARNING: reports come from different hosts (%s, %s): compare like with like."
                 % (old.get("host"), new.get("host")))
    oe, ne = old["selection"]["entrypoints"], new["selection"]["entrypoints"]
    if set(oe) != set(ne):
        L.append("WARNING: main-session entrypoint mixes differ (old: %s; new: %s): compare like with like."
                 % (counts(oe), counts(ne)))
    if git_filters(old) != git_filters(new):
        L.append("WARNING: git repositories, author filters or issue-key prefixes differ (old: %s; new: %s): "
                 "compare like with like." % (git_filters_text(old), git_filters_text(new)))
    om, nm = metrics(old), metrics(new)
    rows = []
    L.append("%-52s %10s %10s %10s" % ("metric", "old", "new", "change"))
    for label, (nv, unit) in nm.items():
        if label not in om:
            continue
        ov = om[label][0]
        if ov is None or nv is None:
            continue
        rows.append((label, ov, nv))
        L.append("%-52s %10s %10s %10s" % (label[:52], value_text(ov, unit), value_text(nv, unit),
                                          change_text(ov, nv, unit)))
    lo = dt.date.fromisoformat(old["window"]["until_date"])
    hi = dt.date.fromisoformat(new["window"]["until_date"])
    since = new["window"].get("since_date")
    since = dt.date.fromisoformat(since) if since else None
    listed = [(d, stamp, text) for d, stamp, text in changes if lo <= d <= hi]
    L.append("")
    L.append("Configuration changes between the reports:")
    if not listed:
        L.append("  none recorded")
    for d, stamp, text in sorted(listed, key=lambda x: x[1]):
        mark = "  (inside new window)" if since is None or d >= since else ""
        L.append("  - %s %s%s" % (stamp, text, mark))
    return "\n".join(L) + "\n", rows


def load_report(path):
    with open(path) as fh:
        rep = json.load(fh)
    if rep.get("schema") != SCHEMA:
        raise SystemExit("%s: unsupported report schema %r" % (path, rep.get("schema")))
    return rep


# ---------------------------------------------------------------- probe

def probe_prompt(agents):
    parts = []
    for a in agents:
        if ":" in a:
            t, m = a.split(":", 1)
            parts.append("%s with model %s" % (t, m))
        else:
            parts.append(a)
    return ("Call the Agent tool once per type, in parallel: " + ", ".join(parts) +
            ". Give each exactly this prompt: 'Reply with the single word OK. Use no tools.' Then reply DONE.")


def probe_mode(entrypoint):
    if entrypoint == "claude-desktop":
        return "desktop"
    if entrypoint and entrypoint.startswith("sdk-"):
        return "headless"
    return entrypoint or "unknown"


def find_session(root, session_id):
    found = sorted(glob.glob(os.path.join(root, "*", session_id + ".jsonl")))
    return found[0] if found else None


def first_timestamp(path):
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            ts = parse_ts(e.get("timestamp")) if isinstance(e, dict) else None
            if ts is not None:
                return ts
    return None


def latest_session(root):
    """The main transcript with a subagents folder whose first event is the newest. Not the
    newest mtime: the session running this command is the most recently modified one."""
    best = None
    for f in glob.glob(os.path.join(root, "*", "*.jsonl")):
        if not os.path.isdir(f[:-len(".jsonl")] + os.sep + "subagents"):
            continue
        ts = first_timestamp(f)
        if ts is not None and (best is None or ts > best[0]):
            best = (ts, f)
    return best[1] if best else None


def probe_session(main_path):
    main = parse_transcript(main_path, "main", select=False)
    fc = first_ctx_call(main["calls"])
    agents = []
    sub_dir = os.path.join(main_path[:-len(".jsonl")], "subagents")
    for f in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl"))):
        meta = read_meta(f)
        s = parse_transcript(f, "sub:" + str(meta.get("agentType", "?")), meta, select=False)
        sc = first_ctx_call(s["calls"])
        agents.append(dict(type=str(meta.get("agentType", "?")), description=meta.get("description"),
                           model=sc["model"] if sc else None, prefix=ctx(sc) if sc else None,
                           calls=len(s["calls"]), ite=sum(call_ite(c) for c in s["calls"])))
    return dict(session=main["session"], project=main["project"], version=main["version"],
                entrypoint=main["entrypoint"], mode=probe_mode(main["entrypoint"]),
                first=iso(main["first_ts"]), main_prefix=ctx(fc) if fc else None,
                main_model=fc["model"] if fc else None, agents=agents)


def probe_env(environ):
    """Return (env, removed_names): environ without the running session's variables.
    Provider and authentication settings stay."""
    env, removed = {}, []
    for name, value in environ.items():
        if name not in PROBE_ENV_KEEP and (name in PROBE_ENV_NAMES or name.startswith(PROBE_ENV_PREFIXES)):
            removed.append(name)
        else:
            env[name] = value
    return env, sorted(removed)


def run_headless_probe(agents, model, timeout, root):
    prompt = probe_prompt(agents)
    if shutil.which("claude") is None:
        raise SystemExit("the claude CLI is not on PATH")
    scratch = tempfile.mkdtemp(prefix=PROBE_PREFIX)
    try:
        cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--allowedTools=Agent"]
        env, removed = probe_env(os.environ)
        proc = subprocess.run(cmd, input=prompt, cwd=scratch, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout, env=env)
        if proc.returncode != 0:
            raise SystemExit("claude -p failed (%d): %s" % (proc.returncode, proc.stderr.strip()[-2000:]))
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            raise SystemExit("claude -p did not print JSON: %s" % proc.stdout[-2000:])
        if isinstance(data, list):
            data = next((x for x in data if isinstance(x, dict) and x.get("session_id")), {})
        session_id = data.get("session_id") if isinstance(data, dict) else None
        if not session_id:
            raise SystemExit("no session_id in the claude -p output")
        path = find_session(root, session_id)
        if path is None:
            raise SystemExit("transcript of session %s not found under %s" % (session_id, root))
        return path, removed
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def render_probe(p):
    L = ["Probe %s  mode %s  CLI %s  entrypoint %s  session %s" % (
        p["date"][:19], p["mode"], p["version"], p["entrypoint"], p["session"])]
    L.append("%-32s %-24s %10s %6s %10s" % ("agent type", "model", "prefix", "calls", "ITE"))
    L.append("%-32s %-24s %10s %6s %10s" % ("(main session)", (p["main_model"] or "-")[:24], tok(p["main_prefix"]), "", ""))
    for a in p["agents"]:
        L.append("%-32s %-24s %10s %6d %10s" % (a["type"][:32], (a["model"] or "-")[:24], tok(a["prefix"]),
                                               a["calls"], tok(a["ite"])))
    if p.get("missing"):
        L.append("missing (requested but no subagent): %s" % ", ".join(p["missing"]))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- commands

def cmd_audit(args):
    args.issue_keys = parse_issue_keys(args.issue_key)
    since = None
    if args.since:
        since, _ = parse_bound(args.since, end=False)
    if args.until:
        until, until_whole = parse_bound(args.until, end=True)
    else:
        until, until_whole = dt.datetime.now().astimezone(), False
    if since is not None and since > until:
        raise SystemExit("--since is after --until")
    current = os.environ.get(CURRENT_SESSION_VAR)
    if current and not args.include_current and current not in args.skip_session:
        args.skip_session = list(args.skip_session) + [current]  # never count the running session
    transcripts = load_transcripts(args.root, args.projects, args.skip_session, since, until)
    rep = build_report(transcripts, args, since, until, until_whole)
    text = render_report(rep)
    reports = os.path.join(args.out, "reports")
    txt_path = os.path.join(reports, rep["name"] + ".txt")
    json_path = os.path.join(reports, rep["name"] + ".json")
    write_atomic(json_path, json.dumps(rep, indent=1, sort_keys=False) + "\n")
    write_atomic(txt_path, text)
    sys.stdout.write(text)
    if args.compare:
        old = load_report(args.compare)
        ctext, _ = compare_reports(old, rep, read_changes(args.out))
        cpath = os.path.join(reports, rep["name"] + ".compare.txt")
        write_atomic(cpath, ctext)
        sys.stdout.write("\n" + ctext)
        print("comparison: %s" % cpath)
    print("report: %s" % txt_path)
    print("data:   %s" % json_path)
    return 0


def cmd_compare(args):
    old, new = load_report(args.old), load_report(args.new)
    text, _ = compare_reports(old, new, read_changes(args.out))
    sys.stdout.write(text)
    return 0


def cmd_note(args):
    if args.date:
        if not NOTE_DATE_RE.match(args.date):
            raise SystemExit("--date must be YYYY-MM-DD or YYYY-MM-DDTHH:MM")
        stamp = args.date
    else:
        stamp = dt.date.today().isoformat()
    text = " ".join(args.text.split())
    if not text:
        raise SystemExit("empty note")
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "changes.md")
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a") as fh:
        if new_file:
            fh.write(CHANGES_HEADING + "\n\n")
        fh.write("- %s %s\n" % (stamp, text))
    print("noted in %s: - %s %s" % (path, stamp, text))
    return 0


def cmd_probe(args):
    requested = None
    removed = None
    if args.read:
        if args.read == "current":
            current = os.environ.get(CURRENT_SESSION_VAR)
            if not current:
                raise SystemExit("--read current needs %s, which is not set" % CURRENT_SESSION_VAR)
            path = find_session(args.root, current)
        elif args.read == "latest":
            path = latest_session(args.root)
        else:
            path = find_session(args.root, args.read)
        if path is None:
            raise SystemExit("no matching session under %s" % args.root)
    else:
        requested = [a.strip() for a in args.agents.split(",") if a.strip()]
        path, removed = run_headless_probe(requested, args.model, args.timeout, args.root)
    p = probe_session(path)
    now = dt.datetime.now().astimezone()
    p.update(schema=SCHEMA, date=now.isoformat(), host=platform.node(), label=args.label, requested=requested,
             model=args.model if requested else None, env_removed=removed)
    if requested:
        got = {a["type"] for a in p["agents"]}
        p["missing"] = [r.split(":", 1)[0] for r in requested if r.split(":", 1)[0] not in got]
    else:
        p["missing"] = []
    name = now.strftime("%Y%m%d-%H%M%S") + "_" + p["mode"] + ("_" + args.label if args.label else "")
    out_path = os.path.join(args.out, "probes", name + ".json")
    write_atomic(out_path, json.dumps(p, indent=1) + "\n")
    sys.stdout.write(render_probe(p))
    if requested and p["mode"] != "headless":
        print("WARNING: the probe session recorded mode %r, not headless: run it from a plain terminal."
              % p["mode"])
    print("probe: %s" % out_path)
    return 0


def parser():
    ap = argparse.ArgumentParser(description="Measure Claude Code token spend from local transcripts.")
    sub = ap.add_subparsers(dest="command")
    sub.required = True

    a = sub.add_parser("audit", help="audit a window of transcripts and save a report")
    a.add_argument("--projects", default="*", help="fnmatch glob on project folder names (default *)")
    a.add_argument("--since", help="YYYY-MM-DD (local 00:00) or ISO timestamp")
    a.add_argument("--until", help="YYYY-MM-DD (end of that local day) or ISO timestamp; default now")
    a.add_argument("--skip-session", action="append", default=[], metavar="ID",
                   help="drop transcripts whose path contains ID (repeatable)")
    a.add_argument("--include-current", action="store_true",
                   help="count the running session (%s), which is skipped by default" % CURRENT_SESSION_VAR)
    a.add_argument("--git", action="append", default=[], metavar="REPO",
                   help="git repository for commit metrics, HEAD only (repeatable); a missing --since / "
                        "--until is taken from the selected transcripts")
    a.add_argument("--issue-key", action="append", default=[], metavar="PREFIX",
                   help="ticket-key prefix such as IDP, counts tickets touched as PREFIX-123 "
                        "(repeatable or comma list)")
    a.add_argument("--author", action="append", default=[], metavar="TEXT",
                   help="count only commits whose author matches TEXT, passed to git log --author (repeatable)")
    a.add_argument("--replay", default=DEFAULT_REPLAY, help="autoCompactWindow values; the first is the reference")
    a.add_argument("--reread-calls", type=int, default=20, metavar="N",
                   help="calls after a compaction counted for re-reads (default 20)")
    a.add_argument("--label", help="suffix for the report name")
    a.add_argument("--compare", metavar="OLD.json", help="compare with a saved report")
    a.add_argument("--root", default=default_root(), help="transcripts root")
    a.add_argument("--out", default=default_out(), help="output folder (default ~/.claude/token-audit)")
    a.set_defaults(func=cmd_audit)

    c = sub.add_parser("compare", help="compare two saved reports")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--out", default=default_out())
    c.set_defaults(func=cmd_compare)

    p = sub.add_parser("probe", help="measure each agent type's first-call prefix")
    p.add_argument("--agents", default=DEFAULT_AGENTS, help="comma list of type or type:model")
    p.add_argument("--model", default="opus", help="main session model (default opus)")
    p.add_argument("--timeout", type=float, default=900, help="seconds (default 900)")
    p.add_argument("--read", metavar="SESSION_ID|current|latest",
                   help="read an existing session instead (current = %s)" % CURRENT_SESSION_VAR)
    p.add_argument("--label")
    p.add_argument("--root", default=default_root())
    p.add_argument("--out", default=default_out())
    p.set_defaults(func=cmd_probe)

    n = sub.add_parser("note", help="append an entry to the changes log")
    n.add_argument("text")
    n.add_argument("--date", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM (default today)")
    n.add_argument("--out", default=default_out())
    n.set_defaults(func=cmd_note)
    return ap


def join_dash_values(argv):
    """Project folder names start with '-', which argparse would take for an option:
    turn `--projects -Users-x*` into `--projects=-Users-x*`."""
    out = []
    i = 0
    while i < len(argv):
        if argv[i] == "--projects" and i + 1 < len(argv):
            out.append("--projects=" + argv[i + 1])
            i += 2
            continue
        out.append(argv[i])
        i += 1
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(join_dash_values(argv))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
