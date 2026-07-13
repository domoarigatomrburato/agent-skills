#!/usr/bin/env python3
"""Draft a compact reviewer packet for a Santommaso adversarial pass."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional


class GitCommandError(RuntimeError):
    """Raised when packet generation cannot obtain trustworthy Git data."""


def run_git(repo: Optional[Path], args: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
        )
    except FileNotFoundError:
        return 127, "", "git executable not found"
    return result.returncode, result.stdout.rstrip(), result.stderr.rstrip()


def find_repo(cwd: Path) -> Optional[Path]:
    args = ["rev-parse", "--show-toplevel"]
    code, stdout, stderr = run_git(cwd, args)
    if code == 0 and stdout:
        return Path(stdout)
    if "not a git repository" in stderr.lower():
        return None
    detail = stderr or stdout or "unknown error"
    raise GitCommandError(f"git {shell_join(args)} failed: {detail}")


def path_args(scope: list[str]) -> list[str]:
    return ["--", *scope] if scope else []


def shell_join(args: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(args)
    return " ".join(shlex.quote(arg) for arg in args)


def git_output(repo: Path, args: list[str]) -> str:
    code, stdout, stderr = run_git(repo, args)
    if code == 0:
        return stdout or "(none)"
    detail = stderr or stdout or "unknown error"
    raise GitCommandError(f"git {shell_join(args)} failed: {detail}")


def resolve_base(repo: Path, requested_base: Optional[str]) -> str:
    if not requested_base:
        raise ValueError(
            "--base is required inside a Git repository; choose HEAD for "
            "uncommitted work or the actual branch/release base for committed work"
        )
    code, stdout, stderr = run_git(
        repo,
        ["rev-parse", "--verify", "--end-of-options", f"{requested_base}^{{commit}}"],
    )
    if code != 0 or not stdout:
        detail = stderr or stdout or "unknown revision"
        raise ValueError(f"invalid --base {requested_base!r}: {detail}")
    return stdout


def desired_output_lines() -> list[str]:
    return [
        "- Report correctness and evidence findings by severity, with concrete evidence, or explicitly state that none were found.",
        "- Return exactly one of: Applied safe cleanup, No safe cleanup, or Report-only opportunities.",
        "- Under Review-only authority, make no edits and return Report-only opportunities when cleanup exists.",
        "- If applying changes, list changed files, why behavior is preserved, and validation run.",
        "- If skipping opportunities, explain the behavior risk or missing coverage.",
    ]


def changed_files_from_status(status: str) -> list[str]:
    files: list[str] = []
    for line in status.splitlines():
        if not line.strip() or line == "(none)":
            continue
        path = line[3:] if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def untracked_files_from_status(status: str) -> list[str]:
    return [
        line[3:]
        for line in status.splitlines()
        if line.startswith("?? ") and len(line) > 3
    ]


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def truncate_lines(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    hidden = len(lines) - max_lines
    return "\n".join(
        [
            *lines[:max_lines],
            f"... truncated {hidden} lines; run the diff command above for the full diff.",
        ]
    )


def fenced(text: str) -> str:
    return f"```text\n{text.rstrip()}\n```"


def flatten_scope(scope_groups: list[list[str]]) -> list[str]:
    return [
        item
        for group in scope_groups
        for item in group
    ]


def build_packet(args: argparse.Namespace) -> str:
    cwd = Path(args.cwd).resolve()
    repo = find_repo(cwd)
    if repo is None:
        scope_lines = [f"- `{item}`" for item in args.scope] or [
            "- TODO: describe the exact files/modules to review."
        ]
        return "\n".join(
            [
                "# Santommaso Adversarial Reviewer Packet",
                "",
                f"Repository: `{cwd}`",
                "",
                "Scope:",
                *scope_lines,
                "",
                "Authority:",
                "- TODO: choose Review-only, Implementation-authorized, or Cleanup-authorized.",
                "",
                "Primary sources:",
                "- TODO: identify the original request/specification and governing docs.",
                "",
                "Changed files:",
                "- TODO: this directory is not inside a git repository.",
                "",
                "Behavior contract:",
                "- TODO: state requested behavior and invariants outside the change.",
                "",
                "Local constraints and validation expectations:",
                "- TODO",
                "",
                "Diff summary:",
                "- TODO: provide the relevant diff or file paths manually.",
                "",
                "Tests or commands already run:",
                "- TODO",
                "",
                "Known risk areas:",
                "- TODO",
                "",
                "Desired reviewer output:",
                *desired_output_lines(),
            ]
        )

    scope = args.scope
    scoped = path_args(scope)
    base = resolve_base(repo, args.base)
    status_args = ["status", "--short", "--untracked-files=all", *scoped]
    names_args = ["diff", "--name-only", base, *scoped]
    stat_args = ["diff", "--stat", base, *scoped]
    diff_args = ["diff", f"--unified={args.unified}", base, *scoped]

    status = git_output(repo, status_args)
    names = git_output(repo, names_args)
    stat = git_output(repo, stat_args)
    changed = unique(
        [
            *changed_files_from_status(status),
            *[line for line in names.splitlines() if line and line != "(none)"],
        ]
    )

    scope_lines = [f"- `{item}`" for item in scope] or [
        "- TODO: replace with the exact review boundary."
    ]
    changed_lines = [f"- `{item}`" for item in changed] or ["- (none detected)"]
    untracked = unique(untracked_files_from_status(status))
    untracked_lines = [f"- `{item}`" for item in untracked]
    summary = "\n\n".join(
        [
            f"$ git {shell_join(status_args)}\n{status}",
            f"$ git {shell_join(stat_args)}\n{stat}",
        ]
    )

    output = [
        "# Santommaso Adversarial Reviewer Packet",
        "",
        f"Repository: `{repo}`",
        "",
        "Scope:",
        *scope_lines,
        "",
        "Authority:",
        "- TODO: choose Review-only, Implementation-authorized, or Cleanup-authorized.",
        "",
        "Primary sources:",
        "- TODO: identify the original request/specification and governing docs.",
        "",
        "Changed files:",
        *changed_lines,
        "",
        "Behavior contract:",
        "- TODO: state requested behavior plus public APIs, side effects, ordering, persistence, defaults, and error semantics that must remain unchanged.",
        "",
        "Local constraints and validation expectations:",
        "- TODO: list relevant AGENTS.md, contribution docs, nearby package docs, and required checks.",
        "",
        "Diff summary:",
        fenced(summary),
        "",
        "Tracked diff command for reviewer:",
        f"`git {shell_join(diff_args)}`",
        "",
        "Untracked files to inspect directly:",
        *(untracked_lines or ["- (none)"]),
        "",
        "Tests or commands already run:",
        "- TODO",
        "",
        "Known risk areas:",
        "- TODO",
        "",
        "Desired reviewer output:",
        *desired_output_lines(),
    ]

    if args.include_diff:
        diff = git_output(repo, diff_args)
        output.extend(
            [
                "",
                "Included diff:",
                fenced(truncate_lines(diff, args.max_diff_lines)),
            ]
        )

    return "\n".join(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Draft a compact Markdown packet for a Santommaso reviewer."
    )
    parser.add_argument(
        "--base",
        help=(
            "Explicit Git revision to diff against. Required inside a Git repository; "
            "use HEAD only for uncommitted work."
        ),
    )
    parser.add_argument(
        "--scope",
        nargs="*",
        action="append",
        default=[],
        help=(
            "Optional files or directories that bound the reviewer scope. "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--include-diff",
        action="store_true",
        help="Include a truncated diff. Omit when the reviewer can inspect the workspace.",
    )
    parser.add_argument(
        "--max-diff-lines",
        type=int,
        default=240,
        help="Maximum diff lines when --include-diff is used.",
    )
    parser.add_argument(
        "--unified",
        type=int,
        default=3,
        help="Unified context lines for the diff command. Defaults to 3.",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Directory used to locate the git repository. Defaults to current directory.",
    )
    args = parser.parse_args()
    args.scope = flatten_scope(args.scope)
    return args


def main() -> None:
    try:
        print(build_packet(parse_args()))
    except (GitCommandError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
