#!/usr/bin/env python3
"""Portable disk-blackboard runtime for the agents-roundtable skill."""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


OUTPUT_FORMATS = {"auto", "text", "json", "stream-json"}
INPUT_MODES = {"stdin", "argument", "file", "none"}
TURN_MODES = {"discuss", "apply", "final"}
PROVIDERS = {"command", "mock"}
PRIORITY_KEYS = [
    "result",
    "text",
    "response",
    "output",
    "content",
    "message",
    "delta",
    "summary",
]
DEFAULT_DIRTY_PATTERNS = [
    "i'll look at",
    "i will look at",
    "now let me",
    "i have everything i need",
    "dimmi se vuoi che lo salvo",
    "tell me if you want me to save it",
]
FINAL_TRANSCRIPT_FOOTER = re.compile(r"\n+# Final Output\n\nSee `final\.md`\.\s*\Z")
IGNORED_DIRS = {
    ".git",
    ".roundtable",
    "__pycache__",
    ".venv",
    "node_modules",
    "dist",
    "build",
}


class RoundtableError(Exception):
    """Expected user-facing runtime error."""


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    argv: List[str]
    cwd: Path


@dataclass
class NormalizedOutput:
    text: str
    dirty: bool = False
    marker_extracted: bool = False
    failed: bool = False
    notes: List[str] = field(default_factory=list)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "run":
            return command_run(args)
        if args.command == "turn":
            return command_turn(args)
        if args.command == "finalize":
            return command_finalize(args)
        if args.command == "inspect":
            return command_inspect(args)
        if args.command == "pack":
            return command_pack(args)
        raise RoundtableError(f"unknown command: {args.command}")
    except RoundtableError as error:
        print(f"roundtable: error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("roundtable: interrupted", file=sys.stderr)
        return 130


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run and recover a disk-blackboard agents roundtable."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="start a new roundtable run")
    source = run_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--preset", help="preset name from assets/presets")
    source.add_argument("--config", help="path to a JSON config")
    brief = run_parser.add_mutually_exclusive_group(required=True)
    brief.add_argument("--topic", help="topic used to create brief.md")
    brief.add_argument("--brief", help="path to a Markdown brief")
    run_parser.add_argument("--out", required=True, help="output root")
    run_parser.add_argument(
        "--workdir",
        default=os.getcwd(),
        help="project root for artifact snapshots and apply turns",
    )
    run_parser.add_argument(
        "--allow-apply",
        action="store_true",
        help="allow config turns with mode=apply after human approval",
    )

    turn_parser = subparsers.add_parser("turn", help="run a manual recovery turn")
    turn_parser.add_argument("--run-dir", required=True)
    turn_parser.add_argument("--agent", required=True)
    turn_parser.add_argument("--role", required=True)
    turn_parser.add_argument("--name", default="")
    turn_parser.add_argument("--instruction", default="")
    turn_parser.add_argument(
        "--prompt-file",
        help="use this exact prompt for the manual turn instead of rebuilding context",
    )
    turn_parser.add_argument("--mode", default="discuss", choices=sorted(TURN_MODES))
    turn_parser.add_argument("--round", type=int, default=None)
    turn_parser.add_argument("--reason", default="manual recovery turn")
    turn_parser.add_argument("--allow-apply", action="store_true")

    final_parser = subparsers.add_parser("finalize", help="run or restore final.md")
    final_parser.add_argument("--run-dir", required=True)
    final_parser.add_argument("--agent", default="")
    final_parser.add_argument("--role", default="synthesizer")
    final_parser.add_argument("--name", default="final-synthesis")
    final_parser.add_argument("--instruction", default="")
    final_parser.add_argument("--force", action="store_true")
    final_parser.add_argument("--reason", default="manual finalization")
    final_parser.add_argument("--allow-apply", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="summarize a run")
    inspect_parser.add_argument("--run-dir", required=True)

    pack_parser = subparsers.add_parser("pack", help="zip a run directory")
    pack_parser.add_argument("--run-dir", required=True)
    pack_parser.add_argument("--dest", required=True)
    pack_parser.add_argument("--force", action="store_true")

    return parser.parse_args(argv)


def command_run(args: argparse.Namespace) -> int:
    workdir = resolve_path(args.workdir)
    output_root = resolve_path(args.out)
    assert_dir(workdir, "workdir")

    config_path = preset_path(args.preset) if args.preset else resolve_path(args.config)
    config = load_config(config_path)
    validate_apply_policy(config, args.allow_apply)

    brief_text = load_brief(args.topic, args.brief)
    run_dir = make_run_dir(output_root)
    ensure_run_dirs(run_dir)
    write_text(run_dir / "brief.md", brief_text)
    write_json(run_dir / "config.json", config)

    artifacts_manifest = snapshot_artifacts(
        workdir, run_dir / "artifacts", config["artifacts"]["include"]
    )
    transcript_path = run_dir / "transcript.md"
    write_text(transcript_path, initial_transcript(config, config_path, run_dir))

    final_response = ""
    turn_number = 0
    for round_index in range(1, config["max_rounds"] + 1):
        for turn in config["turns"]:
            turn_number += 1
            final_response = execute_turn(
                config=config,
                turn=turn,
                round_index=round_index,
                turn_number=turn_number,
                total_turns=turn_number - 1,
                run_dir=run_dir,
                workdir=workdir,
                transcript_path=transcript_path,
                artifacts_manifest=artifacts_manifest,
            ).text

    if config.get("final"):
        turn_number += 1
        final_response = execute_turn(
            config=config,
            turn=config["final"],
            round_index=None,
            turn_number=turn_number,
            total_turns=turn_number - 1,
            run_dir=run_dir,
            workdir=workdir,
            transcript_path=transcript_path,
            artifacts_manifest=artifacts_manifest,
        ).text

    final_path = run_dir / "final.md"
    write_text(final_path, final_document(config, transcript_path, final_response))
    append_text(transcript_path, f"\n\n# Final Output\n\nSee `{final_path.name}`.\n")
    print(f"Run complete: {run_dir}")
    print(f"Transcript: {transcript_path}")
    print(f"Final output: {final_path}")
    return 0


def command_turn(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    config = load_run_config(run_dir)
    validate_apply_policy({"turns": [], "final": {"mode": args.mode, "name": args.name}}, args.allow_apply)
    agent = config["agents"].get(args.agent)
    if not agent:
        raise RoundtableError(f"unknown agent `{args.agent}` in run config")

    turn = {
        "agent": args.agent,
        "role": args.role,
        "name": args.name or f"manual-{slug(args.role)}",
        "mode": args.mode,
        "instruction": args.instruction
        or (
            "Recover or extend the roundtable as this role. Review the brief, "
            "transcript, and prior turns. Produce only the substantive markdown response."
        ),
    }
    workdir = run_dir
    transcript_path = ensure_completed_transcript(run_dir)
    artifacts_manifest = read_optional(run_dir / "artifacts" / "manifest.md")
    turn_number = next_turn_number(run_dir)
    round_index = args.round if args.round is not None else config["max_rounds"]
    prompt_override = read_text(resolve_path(args.prompt_file)) if args.prompt_file else None
    result = execute_turn(
        config=config,
        turn=turn,
        round_index=round_index,
        turn_number=turn_number,
        total_turns=turn_number - 1,
        run_dir=run_dir,
        workdir=workdir,
        transcript_path=transcript_path,
        artifacts_manifest=artifacts_manifest,
        recovery=True,
        recovery_reason=args.reason,
        prompt_override=prompt_override,
    )
    append_recovery_note(
        run_dir,
        [
            f"- Recovery action: ran manual turn `{turn['agent']} / {turn['role']}`.",
            f"- Reason: {args.reason}",
            *(
                [f"- Prompt override: `{resolve_path(args.prompt_file)}`"]
                if args.prompt_file
                else []
            ),
            f"- Output: `turns/{result.turn_path.name}`",
            f"- Completed transcript: `transcript.completed.md`",
        ],
    )
    print(f"Manual turn complete: {result.turn_path}")
    print(f"Completed transcript: {transcript_path}")
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    final_path = run_dir / "final.md"
    if final_path.exists() and not args.force:
        print(f"Final output already exists: {final_path}")
        print("Use --force to run a new final synthesis.")
        return 0

    config = load_run_config(run_dir)
    if args.agent:
        if args.agent not in config["agents"]:
            raise RoundtableError(f"unknown agent `{args.agent}` in run config")
        turn = {
            "agent": args.agent,
            "role": args.role,
            "name": args.name,
            "mode": "final",
            "instruction": args.instruction or default_final_instruction(),
        }
    elif config.get("final"):
        turn = dict(config["final"])
    else:
        raise RoundtableError("run config has no final turn; pass --agent to finalize")

    validate_apply_policy({"turns": [], "final": turn}, args.allow_apply)
    transcript_path = ensure_completed_transcript(run_dir)
    artifacts_manifest = read_optional(run_dir / "artifacts" / "manifest.md")
    turn_number = next_turn_number(run_dir)
    result = execute_turn(
        config=config,
        turn=turn,
        round_index=None,
        turn_number=turn_number,
        total_turns=turn_number - 1,
        run_dir=run_dir,
        workdir=run_dir,
        transcript_path=transcript_path,
        artifacts_manifest=artifacts_manifest,
        recovery=True,
        recovery_reason=args.reason,
    )
    write_text(final_path, final_document(config, transcript_path, result.text))
    append_text(transcript_path, f"\n\n# Final Output\n\nSee `{final_path.name}`.\n")
    append_recovery_note(
        run_dir,
        [
            f"- Recovery action: ran final synthesis `{turn['agent']} / {turn['role']}`.",
            f"- Reason: {args.reason}",
            f"- Output: `final.md`",
            f"- Completed transcript: `transcript.completed.md`",
        ],
    )
    print(f"Final output: {final_path}")
    print(f"Completed transcript: {transcript_path}")
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    turn_files = sorted(
        path
        for path in (run_dir / "turns").glob("*.md")
        if not path.name.endswith(".prompt.md")
    )
    print(f"Run: {run_dir}")
    print(f"Brief: {exists_label(run_dir / 'brief.md')}")
    print(f"Config: {exists_label(run_dir / 'config.json')}")
    print(f"Transcript: {exists_label(run_dir / 'transcript.md')}")
    print(f"Completed transcript: {exists_label(run_dir / 'transcript.completed.md')}")
    print(f"Recovery notes: {exists_label(run_dir / 'RECOVERY.md')}")
    print(f"Final: {exists_label(run_dir / 'final.md')}")
    print(f"Turns: {len(turn_files)}")
    for path in turn_files:
        meta = read_turn_metadata(path)
        exit_code = meta.get("exit_code", "?")
        dirty = meta.get("dirty", "false")
        role = meta.get("name", path.stem)
        print(f"- {path.name}: exit={exit_code}, dirty={dirty}, name={role}")
    return 0


def command_pack(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    dest = resolve_path(args.dest)
    if dest.suffix == ".zip":
        zip_path = dest
        zip_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        dest.mkdir(parents=True, exist_ok=True)
        zip_path = dest / f"{run_dir.name}.zip"
    if zip_path.exists():
        if not args.force:
            raise RoundtableError(f"pack destination already exists: {zip_path}")
        zip_path.unlink()
    archive_base = str(zip_path.with_suffix(""))
    shutil.make_archive(
        archive_base,
        "zip",
        root_dir=str(run_dir.parent),
        base_dir=run_dir.name,
    )
    print(f"Packed run: {zip_path}")
    return 0


@dataclass
class TurnResult:
    text: str
    turn_path: Path


def execute_turn(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    round_index: Optional[int],
    turn_number: int,
    total_turns: int,
    run_dir: Path,
    workdir: Path,
    transcript_path: Path,
    artifacts_manifest: str,
    recovery: bool = False,
    recovery_reason: str = "",
    prompt_override: Optional[str] = None,
) -> TurnResult:
    agent = config["agents"].get(turn["agent"])
    if not agent:
        raise RoundtableError(f"unknown agent `{turn['agent']}`")

    if prompt_override is not None:
        prompt = prompt_override
    else:
        prompt = build_turn_prompt(
            config=config,
            turn=turn,
            agent=agent,
            round_index=round_index,
            turn_number=turn_number,
            total_turns=total_turns,
            brief=read_text(run_dir / "brief.md"),
            transcript=read_optional(transcript_path),
            artifacts_manifest=artifacts_manifest,
            run_dir=run_dir,
        )
    paths = turn_paths(run_dir, turn_number, round_index, turn, recovery)
    write_text(paths["prompt"], prompt)

    cwd = workdir if turn["mode"] == "apply" else run_dir
    try:
        argv, stdin_text = prepare_command(agent, prompt, paths["prompt"], run_dir, workdir, transcript_path)
        env = build_child_env(agent, workdir, run_dir, turn)
        result = run_provider(
            agent=agent,
            turn=turn,
            prompt=prompt,
            argv=argv,
            stdin_text=stdin_text,
            cwd=cwd,
            env=env,
            timeout_seconds=config["budget"]["turn_timeout_seconds"],
        )
    except RoundtableError as error:
        result = CommandResult(
            exit_code=1,
            stdout="",
            stderr=str(error),
            argv=["<prepare-command>"],
            cwd=cwd,
        )

    write_text(paths["stdout"], result.stdout)
    write_text(paths["stderr"], result.stderr)
    normalized = normalize_for_turn(result.stdout, agent, paths["stdout"])
    turn_markdown = turn_markdown_document(
        config=config,
        turn=turn,
        turn_number=turn_number,
        round_index=round_index,
        result=result,
        prompt_path=paths["prompt"],
        stdout_path=paths["stdout"],
        stderr_path=paths["stderr"],
        normalized=normalized,
        recovery=recovery,
        recovery_reason=recovery_reason,
        prompt_source="custom" if prompt_override is not None else "generated",
    )
    write_text(paths["turn"], turn_markdown)
    append_text(transcript_path, f"\n{turn_markdown}")

    if result.exit_code != 0:
        stderr_preview = result.stderr.strip()[-2000:] or "(no stderr)"
        raise RoundtableError(
            f"turn {turn_number} failed with exit code {result.exit_code}: "
            f"{turn['agent']} / {turn['role']}\n{stderr_preview}"
        )
    return TurnResult(text=normalized.text, turn_path=paths["turn"])


def run_provider(
    *,
    agent: Dict[str, Any],
    turn: Dict[str, Any],
    prompt: str,
    argv: List[str],
    stdin_text: Optional[str],
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: int,
) -> CommandResult:
    if agent["provider"] == "mock":
        stdout = mock_stdout(agent, turn, prompt)
        return CommandResult(
            exit_code=0,
            stdout=stdout,
            stderr="",
            argv=["<mock-provider>", agent["name"], turn["role"]],
            cwd=cwd,
        )
    return run_subprocess(argv, stdin_text, cwd, env, timeout_seconds)


def run_subprocess(
    argv: List[str],
    stdin_text: Optional[str],
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: int,
) -> CommandResult:
    if not argv:
        raise RoundtableError("cannot run an empty command")
    if not command_resolves(argv[0], cwd):
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=f"command not found: {argv[0]}",
            argv=argv,
            cwd=cwd,
        )
    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            argv=argv,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as error:
        stdout = to_text(error.stdout)
        stderr = to_text(error.stderr)
        stderr = f"{stderr}\n[roundtable timeout after {timeout_seconds} seconds]".strip()
        return CommandResult(
            exit_code=124,
            stdout=stdout,
            stderr=stderr,
            argv=argv,
            cwd=cwd,
        )
    except OSError as error:
        return CommandResult(
            exit_code=1,
            stdout="",
            stderr=str(error),
            argv=argv,
            cwd=cwd,
        )


def command_resolves(command: str, cwd: Path) -> bool:
    if os.sep in command or (os.altsep and os.altsep in command):
        path = Path(command).expanduser()
        if not path.is_absolute():
            path = cwd / path
        return path.exists()
    return shutil.which(command) is not None


def mock_stdout(agent: Dict[str, Any], turn: Dict[str, Any], prompt: str) -> str:
    role = turn["role"].lower()
    prompt_size = len(prompt)
    if "evidence" in role:
        response = f"""# Mock Evidence Matrix

| Item | Category | Support | Deployment | Data Exposure | Integration | Source | Confidence |
|---|---|---|---|---|---|---|---|
| Mock Tool A | deterministic | supported | CI job | repository diff | merge request report | https://example.invalid/tool-a | medium |
| Mock Tool B | AI reviewer | unknown | SaaS or self-hosted unknown | unknown | merge request comments | unknown | low |

## Open Questions
- Mock Tool B requires source-backed deployment and data-flow verification.

_mock prompt chars: {prompt_size}_"""
    elif "auditor" in role:
        response = f"""# Mock Source Audit

## Corrections
- Keep Mock Tool B as `unknown`; do not infer self-hosted support without a source.
- Preserve source URLs beside each claim.

## Completion Status
- The dossier is usable as a format smoke test.
- The dossier is not complete research because mock sources are not evidence.

_mock prompt chars: {prompt_size}_"""
    elif "critic" in role:
        response = f"""# Mock Critique

## Agreements
- The blackboard should remain the durable source of truth.
- Raw stdout and stderr must be preserved for every turn.

## Risks
- Dirty provider output can look clean unless markers and dirty-pattern checks are used.
- Recovery should extend `transcript.completed.md` instead of rewriting the original transcript.

## Recommendation
Keep the first slice deterministic, inspectable, and boring enough to trust.

_mock prompt chars: {prompt_size}_"""
    elif "synth" in role or "final" in role:
        response = f"""# Mock Final Synthesis

## Agreement
- Use a run-local blackboard with prompt, raw logs, normalized turns, transcript, and final output.
- Treat normalization as best effort and raw logs as the source of truth.

## Disagreement
- No automatic consensus should be inferred from a bounded mock run.

## Final Proposal
Ship the skill with JSON presets, a stdlib Python runtime, explicit recovery commands, and mock validation.

## Next Action
Run the real preset only after the host agent has inspected the mock run layout.

_mock prompt chars: {prompt_size}_"""
    else:
        response = f"""# Mock Draft

## Proposal
- Create `<output-root>/runs/<timestamp>/` with brief, config, transcript, turns, and artifacts.
- Execute bounded writer, critic, and synthesizer turns through configured providers.
- Preserve raw output and keep normalized markdown clean enough for final synthesis.

## Assumptions
- The host agent remains responsible for retries, caveats, and final judgment.
- Apply turns stay disabled unless explicitly approved.

_mock prompt chars: {prompt_size}_"""

    output_format = agent["output_format"]
    if output_format == "json":
        return json.dumps({"text": response, "agent": agent["name"], "role": turn["role"]})
    if output_format == "stream-json":
        lines = response.splitlines()
        first = "\n".join(lines[: max(1, len(lines) // 2)])
        second = "\n".join(lines[max(1, len(lines) // 2) :])
        return "\n".join(
            [
                json.dumps({"type": "message", "text": first}),
                json.dumps({"type": "message", "text": second}),
            ]
        )
    return response


def load_config(path: Path) -> Dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise RoundtableError("config root must be a JSON object")
    return parse_config(raw)


def parse_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    config = {
        "name": string_value(raw.get("name", "roundtable"), "name"),
        "max_rounds": positive_int(raw.get("max_rounds"), "max_rounds"),
        "stop_condition": required_string(raw.get("stop_condition"), "stop_condition"),
        "budget": parse_budget(raw.get("budget")),
        "agents": parse_agents(raw.get("agents")),
        "artifacts": parse_artifacts(raw.get("artifacts", {})),
        "turns": parse_turns(raw.get("turns")),
        "final": parse_turn(raw["final"], "final", default_mode="final")
        if "final" in raw
        else None,
    }
    validate_turn_agents(config)
    return config


def parse_budget(raw: Any) -> Dict[str, int]:
    record = require_record(raw, "budget")
    return {
        "turn_timeout_seconds": positive_int(
            record.get("turn_timeout_seconds"), "budget.turn_timeout_seconds"
        ),
        "max_prompt_chars": positive_int(
            record.get("max_prompt_chars"), "budget.max_prompt_chars"
        ),
    }


def parse_agents(raw: Any) -> Dict[str, Dict[str, Any]]:
    record = require_record(raw, "agents")
    if not record:
        raise RoundtableError("agents must not be empty")
    return {name: parse_agent(name, value) for name, value in record.items()}


def parse_agent(name: str, raw: Any) -> Dict[str, Any]:
    record = require_record(raw, f"agents.{name}")
    provider = string_value(record.get("provider", "command"), f"agents.{name}.provider")
    if provider not in PROVIDERS:
        raise RoundtableError(f"agents.{name}.provider must be one of {format_set(PROVIDERS)}")
    command = string_list(
        record.get("command", []),
        f"agents.{name}.command",
        allow_empty=provider == "mock",
    )
    input_mode = string_value(record.get("input", "stdin"), f"agents.{name}.input")
    if input_mode not in INPUT_MODES:
        raise RoundtableError(f"agents.{name}.input must be one of {format_set(INPUT_MODES)}")
    output_format = string_value(
        record.get("output_format", "auto"), f"agents.{name}.output_format"
    )
    if output_format not in OUTPUT_FORMATS:
        raise RoundtableError(
            f"agents.{name}.output_format must be one of {format_set(OUTPUT_FORMATS)}"
        )
    return {
        "name": name,
        "provider": provider,
        "command": command,
        "input": input_mode,
        "output_format": output_format,
        "extract_paths": string_list(
            record.get("extract_paths", []),
            f"agents.{name}.extract_paths",
            allow_empty=True,
        ),
        "markers": parse_markers(record.get("markers", {}), f"agents.{name}.markers"),
        "dirty_patterns": string_list(
            record.get("dirty_patterns", DEFAULT_DIRTY_PATTERNS),
            f"agents.{name}.dirty_patterns",
            allow_empty=True,
        ),
        "env": string_record(record.get("env", {}), f"agents.{name}.env"),
    }


def parse_markers(raw: Any, field_name: str) -> Dict[str, str]:
    if raw in ({}, None):
        return {}
    record = require_record(raw, field_name)
    start = required_string(record.get("start"), f"{field_name}.start")
    end = required_string(record.get("end"), f"{field_name}.end")
    return {"start": start, "end": end}


def parse_artifacts(raw: Any) -> Dict[str, List[str]]:
    record = require_record(raw, "artifacts")
    return {
        "include": string_list(
            record.get("include", []), "artifacts.include", allow_empty=True
        )
    }


def parse_turns(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise RoundtableError("turns must be a non-empty list")
    return [parse_turn(value, f"turns[{index}]") for index, value in enumerate(raw)]


def parse_turn(raw: Any, field_name: str, default_mode: str = "discuss") -> Dict[str, Any]:
    record = require_record(raw, field_name)
    mode = string_value(record.get("mode", default_mode), f"{field_name}.mode")
    if mode not in TURN_MODES:
        raise RoundtableError(f"{field_name}.mode must be one of {format_set(TURN_MODES)}")
    return {
        "agent": required_string(record.get("agent"), f"{field_name}.agent"),
        "role": required_string(record.get("role"), f"{field_name}.role"),
        "name": string_value(record.get("name", ""), f"{field_name}.name"),
        "mode": mode,
        "instruction": required_string(record.get("instruction"), f"{field_name}.instruction"),
    }


def validate_turn_agents(config: Dict[str, Any]) -> None:
    for turn in [*config["turns"], *([config["final"]] if config.get("final") else [])]:
        if turn["agent"] not in config["agents"]:
            raise RoundtableError(
                f"{turn['role']} references unknown agent `{turn['agent']}`"
            )


def validate_apply_policy(config: Dict[str, Any], allow_apply: bool) -> None:
    apply_turns = [
        *[turn for turn in config.get("turns", []) if turn.get("mode") == "apply"],
        *(
            [config["final"]]
            if config.get("final") and config["final"].get("mode") == "apply"
            else []
        ),
    ]
    if apply_turns and not allow_apply:
        labels = ", ".join(turn.get("name") or turn.get("role", "apply") for turn in apply_turns)
        raise RoundtableError(
            f"config contains apply turn(s): {labels}. Re-run with --allow-apply after human approval."
        )


def build_turn_prompt(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    agent: Dict[str, Any],
    round_index: Optional[int],
    turn_number: int,
    total_turns: int,
    brief: str,
    transcript: str,
    artifacts_manifest: str,
    run_dir: Path,
) -> str:
    round_label = "final" if round_index is None else f"{round_index}/{config['max_rounds']}"
    marker_contract = ""
    if agent["markers"]:
        marker_contract = f"""
If possible, put the entire substantive response between these exact markers and write no preamble outside them:

{agent['markers']['start']}
...
{agent['markers']['end']}
"""
    header = f"""# Agents Roundtable Turn

## Collaboration Brief
{brief.strip()}

## Run State
- round: {round_label}
- turn_number: {turn_number}
- total_turns_so_far: {total_turns}
- agent: {turn['agent']}
- role: {turn['role']}
- mode: {turn['mode']}
- run_dir: {run_dir}
- max_rounds: {config['max_rounds']}
- stop_condition: {config['stop_condition']}
- budget.turn_timeout_seconds: {config['budget']['turn_timeout_seconds']}
- budget.max_prompt_chars: {config['budget']['max_prompt_chars']}

## Safety Rule
For discuss/final turns, do not modify files outside the run directory. Work only
through the blackboard: transcript, turn notes, and artifacts copied under
`artifacts/`. Only a turn with mode `apply`, explicitly allowed by the human
runner, may change project files.

## Artifacts Manifest
{artifacts_manifest.strip() or "No artifacts were configured for this run."}

## Instructions For This Turn
{turn['instruction'].strip()}

## Output Contract
Write a self-contained markdown response for Alessandro. Be concrete, include
assumptions, and say what should happen next. Do not claim consensus
automatically; name disagreements if they remain.{marker_contract}
"""
    prompt = f"""{header}
## Blackboard Transcript So Far
{transcript.strip() or "No transcript yet."}
"""
    max_chars = config["budget"]["max_prompt_chars"]
    if len(prompt) <= max_chars:
        return prompt
    reserved = len(header) + 500
    transcript_budget = max(max_chars - reserved, 0)
    trimmed = transcript[-transcript_budget:] if transcript_budget else ""
    return f"""{header}
## Blackboard Transcript So Far
[Transcript trimmed from the beginning because max_prompt_chars was reached.]
{trimmed.strip() or "No transcript available after trimming."}
"""


def prepare_command(
    agent: Dict[str, Any],
    prompt: str,
    prompt_path: Path,
    run_dir: Path,
    workdir: Path,
    transcript_path: Path,
) -> Tuple[List[str], Optional[str]]:
    if agent["provider"] == "mock":
        return [], None
    raw_tokens = agent["command"]
    tokens = [
        expand_token(
            token,
            prompt=prompt,
            prompt_path=prompt_path,
            run_dir=run_dir,
            workdir=workdir,
            transcript_path=transcript_path,
        )
        for token in raw_tokens
    ]
    has_prompt = any("{prompt}" in token for token in raw_tokens)
    has_prompt_file = any("{prompt_file}" in token for token in raw_tokens)
    if agent["input"] == "stdin":
        return tokens, prompt
    if agent["input"] == "argument" and not has_prompt:
        return [*tokens, prompt], None
    if agent["input"] == "file" and not has_prompt_file:
        return [*tokens, str(prompt_path)], None
    return tokens, None


def build_child_env(
    agent: Dict[str, Any], workdir: Path, run_dir: Path, turn: Dict[str, Any]
) -> Dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "AGENTS_ROUNDTABLE_RUN_DIR": str(run_dir),
            "AGENTS_ROUNDTABLE_WORKDIR": str(workdir),
            "AGENTS_ROUNDTABLE_TURN_MODE": turn["mode"],
            "AGENTS_ROUNDTABLE_ROLE": turn["role"],
        }
    )
    for key, value in agent["env"].items():
        env[key] = expand_token(
            value,
            prompt="",
            prompt_path=run_dir / "prompt.md",
            run_dir=run_dir,
            workdir=workdir,
            transcript_path=run_dir / "transcript.md",
        )
    return env


def expand_token(
    value: str,
    *,
    prompt: str,
    prompt_path: Path,
    run_dir: Path,
    workdir: Path,
    transcript_path: Path,
) -> str:
    replacements = {
        "{prompt}": prompt,
        "{prompt_file}": str(prompt_path),
        "{run_dir}": str(run_dir),
        "{workdir}": str(workdir),
        "{transcript_file}": str(transcript_path),
        "{skill_dir}": str(skill_dir()),
        "{script_dir}": str(script_dir()),
        "{python}": sys.executable,
    }
    expanded = value
    for token, replacement in replacements.items():
        expanded = expanded.replace(token, replacement)

    def replace_env(match: re.Match[str]) -> str:
        name = match.group(1)
        env_value = os.environ.get(name)
        if env_value is None:
            raise RoundtableError(
                f"environment variable `{name}` is required by the config but is not set"
            )
        return env_value

    expanded = re.sub(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", replace_env, expanded)
    return str(Path(expanded).expanduser()) if expanded.startswith("~") else expanded


def normalize_for_turn(stdout: str, agent: Dict[str, Any], stdout_path: Path) -> NormalizedOutput:
    try:
        normalized = normalize_output(stdout, agent)
    except RoundtableError as error:
        return NormalizedOutput(
            text=(
                f"[Normalization failed: {error}]\n\n"
                f"Raw stdout is saved in `{stdout_path.name}`."
            ),
            failed=True,
            notes=[str(error)],
        )
    if not normalized.text.strip():
        normalized.text = "[No normalized response]"
    return normalized


def normalize_output(stdout: str, agent: Dict[str, Any]) -> NormalizedOutput:
    text = normalize_by_format(stdout, agent["output_format"], agent["extract_paths"]).strip()
    notes: List[str] = []
    marker_extracted = False
    markers = agent["markers"]
    if markers:
        marked, found = extract_marked_text(text, markers["start"], markers["end"])
        if found:
            text = marked.strip()
            marker_extracted = True
            notes.append("marker-delimited output extracted")
        else:
            notes.append("configured output markers were not found")

    dirty = has_dirty_output(text, agent["dirty_patterns"])
    if dirty:
        cleaned = clean_dirty_lines(text, agent["dirty_patterns"])
        if cleaned != text:
            text = cleaned
            notes.append("dirty provider narration removed from normalized output")
        else:
            notes.append("dirty provider narration detected")
    return NormalizedOutput(
        text=text,
        dirty=dirty,
        marker_extracted=marker_extracted,
        notes=notes,
    )


def normalize_by_format(stdout: str, output_format: str, extract_paths: List[str]) -> str:
    if output_format == "text":
        return stdout.strip()
    if output_format == "json":
        return normalize_json(stdout, extract_paths)
    if output_format == "stream-json":
        return normalize_stream_json(stdout, extract_paths)
    stripped = stdout.strip()
    if not stripped:
        return ""
    for parser in (normalize_json, normalize_stream_json):
        try:
            return parser(stripped, extract_paths)
        except RoundtableError:
            pass
    return stripped


def normalize_json(stdout: str, extract_paths: List[str]) -> str:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise RoundtableError(f"failed to parse JSON output: {error}")
    extracted = extract_from_payload(payload, extract_paths).strip()
    return extracted or json.dumps(payload, indent=2, ensure_ascii=False)


def normalize_stream_json(stdout: str, extract_paths: List[str]) -> str:
    parts: List[str] = []
    parsed_any = False
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise RoundtableError(f"failed to parse stream JSON output: {error}")
        parsed_any = True
        extracted = extract_from_payload(payload, extract_paths).strip()
        if extracted:
            parts.append(extracted)
    if not parsed_any:
        return ""
    return dedupe_join(parts)


def extract_from_payload(payload: Any, extract_paths: List[str]) -> str:
    for path in extract_paths:
        value = get_path(payload, path)
        extracted = extract_text(value, 0)
        if extracted.strip():
            return extracted
    return extract_text(payload, 0)


def get_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def extract_text(value: Any, depth: int) -> str:
    if value is None or depth > 8 or isinstance(value, (int, float, bool)):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return dedupe_join([extract_text(item, depth + 1) for item in value])
    if isinstance(value, dict):
        for key in PRIORITY_KEYS:
            if key in value:
                extracted = extract_text(value[key], depth + 1)
                if extracted.strip():
                    return extracted
    return ""


def extract_marked_text(text: str, start: str, end: str) -> Tuple[str, bool]:
    start_index = text.find(start)
    if start_index < 0:
        return text, False
    body_start = start_index + len(start)
    end_index = text.find(end, body_start)
    if end_index < 0:
        return text, False
    return text[body_start:end_index], True


def has_dirty_output(text: str, patterns: List[str]) -> bool:
    lower = text.lower()
    return any(pattern.lower() in lower for pattern in patterns)


def clean_dirty_lines(text: str, patterns: List[str]) -> str:
    lowered = [pattern.lower() for pattern in patterns]
    kept = [
        line
        for line in text.splitlines()
        if not any(pattern in line.lower() for pattern in lowered)
    ]
    cleaned = "\n".join(kept).strip()
    return cleaned or text


def turn_paths(
    run_dir: Path,
    turn_number: int,
    round_index: Optional[int],
    turn: Dict[str, Any],
    recovery: bool,
) -> Dict[str, Path]:
    slug_text = turn_slug(turn_number, round_index, turn, recovery)
    turns_dir = run_dir / "turns"
    return {
        "prompt": turns_dir / f"{slug_text}.prompt.md",
        "stdout": turns_dir / f"{slug_text}.stdout",
        "stderr": turns_dir / f"{slug_text}.stderr",
        "turn": turns_dir / f"{slug_text}.md",
    }


def turn_slug(
    turn_number: int,
    round_index: Optional[int],
    turn: Dict[str, Any],
    recovery: bool,
) -> str:
    round_part = "final" if round_index is None else f"r{round_index:02d}"
    if recovery:
        round_part = f"manual-{round_part}"
    label = turn.get("name") or turn["role"]
    return "-".join(
        [
            f"{turn_number:03d}",
            round_part,
            slug(turn["agent"], keep_underscore=True),
            slug(label),
        ]
    )


def turn_markdown_document(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    turn_number: int,
    round_index: Optional[int],
    result: CommandResult,
    prompt_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    normalized: NormalizedOutput,
    recovery: bool,
    recovery_reason: str,
    prompt_source: str,
) -> str:
    round_label = "final" if round_index is None else str(round_index)
    lines = [
        f"## Turn {turn_number}: {turn['agent']} / {turn['role']}",
        "",
        f"- round: {round_label}",
        f"- name: {turn.get('name') or turn['role']}",
        f"- mode: {turn['mode']}",
    ]
    if recovery:
        lines.extend(["- recovery: manual", f"- reason: {recovery_reason}"])
    lines.extend(
        [
            f"- cwd: {result.cwd}",
            f"- exit_code: {result.exit_code}",
            f"- dirty: {str(normalized.dirty).lower()}",
            f"- marker_extracted: {str(normalized.marker_extracted).lower()}",
            f"- normalization_failed: {str(normalized.failed).lower()}",
            f"- prompt: {prompt_path.name}",
            f"- prompt_source: {prompt_source}",
            f"- raw_stdout: {stdout_path.name}",
            f"- raw_stderr: {stderr_path.name}",
            f"- command: `{shlex.join(result.argv)}`",
        ]
    )
    if normalized.notes:
        lines.extend(["", "### Normalization Notes", ""])
        lines.extend(f"- {note}" for note in normalized.notes)
    lines.extend(["", "### Normalized Response", "", normalized.text.strip(), ""])
    return "\n".join(lines)


def initial_transcript(config: Dict[str, Any], config_path: Path, run_dir: Path) -> str:
    return f"""# Agents Roundtable Transcript

- name: {config['name']}
- config: {config_path}
- run_dir: {run_dir}
- max_rounds: {config['max_rounds']}
- stop_condition: {config['stop_condition']}

"""


def final_document(config: Dict[str, Any], transcript_path: Path, final_response: str) -> str:
    return f"""# Final Output

- roundtable: {config['name']}
- transcript: {transcript_path.name}
- max_rounds: {config['max_rounds']}
- stop_condition: {config['stop_condition']}

{final_response.strip() or "No final response was produced."}
"""


def default_final_instruction() -> str:
    return (
        "Produce the final Markdown document for the user. Incorporate the brief, "
        "transcript, manual recovery turns, and unresolved disagreements. Include "
        "a recovery note when the run did not complete cleanly."
    )


def snapshot_artifacts(workdir: Path, artifacts_dir: Path, patterns: List[str]) -> str:
    files_dir = artifacts_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest_lines = ["# Artifacts Manifest", ""]
    if not patterns:
        manifest = "# Artifacts Manifest\n\nNo artifacts configured.\n"
        write_text(artifacts_dir / "manifest.md", manifest)
        return manifest

    copied: List[str] = []
    for pattern in patterns:
        matches = artifact_matches(workdir, pattern)
        if not matches:
            manifest_lines.append(f"- `{pattern}`: no matches")
            continue
        for match in matches:
            if should_ignore_artifact(workdir, match):
                continue
            relative = match.resolve().relative_to(workdir.resolve())
            destination = files_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(match, destination)
            copied.append(relative.as_posix())
    if copied:
        for item in sorted(set(copied)):
            manifest_lines.append(f"- `artifacts/files/{item}`")
    else:
        manifest_lines.append("No artifact files copied.")
    manifest = "\n".join(manifest_lines) + "\n"
    write_text(artifacts_dir / "manifest.md", manifest)
    return manifest


def artifact_matches(workdir: Path, pattern: str) -> List[Path]:
    if Path(pattern).is_absolute():
        raise RoundtableError(f"artifact pattern must be relative: {pattern}")
    raw_matches = glob.glob(str(workdir / pattern), recursive=True)
    matches: List[Path] = []
    root = workdir.resolve()
    for raw in raw_matches:
        path = Path(raw)
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not is_relative_to(resolved, root):
            continue
        matches.append(path)
    return sorted(matches)


def should_ignore_artifact(workdir: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(workdir.resolve())
    except ValueError:
        return True
    return any(part in IGNORED_DIRS for part in relative.parts)


def ensure_completed_transcript(run_dir: Path) -> Path:
    completed = run_dir / "transcript.completed.md"
    original = run_dir / "transcript.md"
    source = completed if completed.exists() else original
    if not source.exists():
        raise RoundtableError(f"transcript not found: {original}")
    text = strip_final_transcript_footer(read_text(source))
    write_text(completed, text)
    return completed


def strip_final_transcript_footer(text: str) -> str:
    stripped = FINAL_TRANSCRIPT_FOOTER.sub("", text).rstrip()
    return f"{stripped}\n" if stripped else ""


def append_recovery_note(run_dir: Path, bullets: List[str]) -> None:
    path = run_dir / "RECOVERY.md"
    if not path.exists():
        write_text(path, "# Manual Recovery Notes\n\n")
    append_text(path, "\n".join(bullets) + "\n")


def next_turn_number(run_dir: Path) -> int:
    numbers: List[int] = []
    for path in (run_dir / "turns").glob("*.md"):
        if path.name.endswith(".prompt.md"):
            continue
        match = re.match(r"^(\d{3})-", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def read_turn_metadata(path: Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- ") or ": " not in line:
            continue
        key, value = line[2:].split(": ", 1)
        metadata[key] = value
    return metadata


def load_run_config(run_dir: Path) -> Dict[str, Any]:
    return load_config(run_dir / "config.json")


def load_brief(topic: Optional[str], brief_path: Optional[str]) -> str:
    if brief_path:
        return read_text(resolve_path(brief_path))
    if not topic or not topic.strip():
        raise RoundtableError("--topic must not be empty")
    return f"""# Roundtable Brief

## Topic
{topic.strip()}

## Desired Output
Produce a clear final Markdown document for the user.

## Host Notes
Use bounded rounds, preserve disagreement, and name assumptions or missing evidence.
"""


def make_run_dir(output_root: Path) -> Path:
    runs_root = output_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = runs_root / timestamp
    suffix = 1
    while candidate.exists():
        candidate = runs_root / f"{timestamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def ensure_run_dirs(run_dir: Path) -> None:
    (run_dir / "turns").mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts" / "files").mkdir(parents=True, exist_ok=True)


def preset_path(name: str) -> Path:
    path = skill_dir() / "assets" / "presets" / f"{name}.json"
    if not path.exists():
        available = ", ".join(
            sorted(item.stem for item in (skill_dir() / "assets" / "presets").glob("*.json"))
        )
        raise RoundtableError(f"unknown preset `{name}`. Available presets: {available}")
    return path


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def read_json(path: Path) -> Any:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as error:
        raise RoundtableError(f"failed to parse JSON {path}: {error}")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RoundtableError(f"file not found: {path}")
    except OSError as error:
        raise RoundtableError(f"failed to read {path}: {error}")


def read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def assert_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise RoundtableError(f"{label} not found or not a directory: {path}")


def exists_label(path: Path) -> str:
    return "yes" if path.exists() else "no"


def require_record(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RoundtableError(f"{field_name} must be an object")
    return value


def required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoundtableError(f"{field_name} must be a non-empty string")
    return value


def string_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise RoundtableError(f"{field_name} must be a string")
    return value


def string_list(value: Any, field_name: str, allow_empty: bool = False) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RoundtableError(f"{field_name} must be a list of strings")
    if not allow_empty and not value:
        raise RoundtableError(f"{field_name} cannot be empty")
    return list(value)


def string_record(value: Any, field_name: str) -> Dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise RoundtableError(f"{field_name} must be an object of strings")
    return dict(value)


def positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise RoundtableError(f"{field_name} must be a positive integer")
    return value


def format_set(values: Iterable[str]) -> str:
    return ", ".join(sorted(values))


def dedupe_join(values: List[str]) -> str:
    seen = set()
    parts: List[str] = []
    for value in values:
        stripped = value.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            parts.append(stripped)
    return "\n".join(parts)


def slug(value: str, keep_underscore: bool = False) -> str:
    pattern = r"[^a-z0-9_]+" if keep_underscore else r"[^a-z0-9]+"
    lowered = value.lower()
    return re.sub(pattern, "-", lowered).strip("-") or "turn"


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    sys.exit(main())
