#!/usr/bin/env python3

"""Thin blackboard helper for the agent-council skill."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shlex
import shutil
import subprocess
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_OUTPUT_ROOT = "/tmp/agent-council"
PROFILES = ("smoke", "budget", "standard", "premium")
EXTERNAL_PROVIDERS = ("shell", "cursor", "copilot")
EXTERNAL_MODES = ("read-only", "unrestricted")
PROMPT_TRANSPORTS = ("auto", "stdin", "argument")


class CouncilError(Exception):
    """User-facing council error."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="council.py",
        description="Create and maintain agent-council run blackboards.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create a run blackboard")
    start.add_argument("--preset", required=True, help="preset name or JSON path")
    start.add_argument("--topic", default="", help="short topic for generated brief.md")
    start.add_argument("--brief-file", default="", help="markdown brief to copy into the run")
    start.add_argument("--workdir", required=True, help="target project directory")
    start.add_argument(
        "--out",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"output root for runs (default: {DEFAULT_OUTPUT_ROOT})",
    )
    start.add_argument(
        "--profile",
        choices=PROFILES,
        default="standard",
        help="run profile: smoke, budget, standard, or premium",
    )
    start.add_argument(
        "--budget",
        action="store_true",
        help="shortcut for --profile budget",
    )
    start.add_argument(
        "--plan-file",
        default="",
        help="confirmed preflight plan to copy into council-plan.md",
    )
    start.set_defaults(handler=command_start)

    scaffold = subparsers.add_parser(
        "scaffold-run",
        help="draft brief, plan, and prompt files from a preset before a run",
    )
    scaffold.add_argument("--preset", required=True, help="preset name or JSON path")
    scaffold.add_argument("--topic", default="", help="short topic for generated brief.md")
    scaffold.add_argument("--brief-file", default="", help="markdown brief to copy into the scaffold")
    scaffold.add_argument("--workdir", required=True, help="target project directory")
    scaffold.add_argument(
        "--out",
        required=True,
        help="directory where scaffold files will be written",
    )
    scaffold.add_argument(
        "--profile",
        choices=PROFILES,
        default="standard",
        help="run profile: smoke, budget, standard, or premium",
    )
    scaffold.add_argument(
        "--budget",
        action="store_true",
        help="shortcut for --profile budget",
    )
    scaffold.add_argument(
        "--extra-context-file",
        action="append",
        default=[],
        help="additional source/context file path to include in every prompt stub",
    )
    scaffold.set_defaults(handler=command_scaffold_run)

    record = subparsers.add_parser("record", help="record a planned turn")
    record.add_argument("--run-dir", required=True, help="run directory from start")
    record.add_argument("--turn", required=True, help="planned turn name")
    record.add_argument("--from-file", required=True, help="markdown/text file to record")
    record.add_argument(
        "--prompt-file",
        default="",
        help="optional prompt file used for the subagent, copied for audit",
    )
    record.add_argument(
        "--model",
        default="",
        help="actual resolved model used for this turn",
    )
    record.set_defaults(handler=command_record)

    run_shell = subparsers.add_parser(
        "run-shell-seat",
        help="execute a planned turn through a shell-backed external seat",
    )
    run_shell.add_argument("--run-dir", required=True, help="run directory from start")
    run_shell.add_argument("--turn", required=True, help="planned turn name")
    run_shell.add_argument(
        "--prompt-file",
        default="",
        help="prompt to send to the external seat; falls back to turn.prompt_file when configured",
    )
    run_shell.add_argument(
        "--provider",
        choices=EXTERNAL_PROVIDERS,
        default="",
        help="external provider adapter; defaults to the seat provider or shell",
    )
    run_shell.add_argument(
        "--command",
        default="",
        help=(
            "shell provider command. If it contains {prompt}, the prompt is "
            "passed as that argument; if it contains {prompt_file}, the "
            "materialized prompt path is passed; otherwise the prompt is sent "
            "on stdin."
        ),
    )
    run_shell.add_argument(
        "--executable",
        default="",
        help="override executable for cursor/copilot providers",
    )
    run_shell.add_argument(
        "--cwd",
        default="",
        help="working directory for the external CLI; defaults to resolved run workdir",
    )
    run_shell.add_argument(
        "--model",
        default="",
        help="provider model slug to request and record when supported",
    )
    run_shell.add_argument(
        "--mode",
        choices=EXTERNAL_MODES,
        default="",
        help="execution posture; defaults to seat mode or read-only",
    )
    run_shell.add_argument(
        "--timeout-seconds",
        type=int,
        default=0,
        help="external CLI timeout; defaults to seat timeout or 1800",
    )
    run_shell.add_argument(
        "--prompt-transport",
        choices=PROMPT_TRANSPORTS,
        default="",
        help="how to pass provider prompts; defaults to seat.prompt_transport or auto",
    )
    run_shell.add_argument(
        "--cursor-trust",
        action="store_true",
        help="pass Cursor Agent --trust; use only after explicit user authorization",
    )
    run_shell.set_defaults(handler=command_run_shell_seat)

    discover = subparsers.add_parser(
        "discover-models",
        help="record external provider model discovery/probe artifacts",
    )
    discover.add_argument("--provider", choices=("cursor", "copilot"), required=True)
    discover.add_argument("--executable", default="", help="override provider executable")
    discover.add_argument("--cwd", default="", help="working directory for provider commands")
    discover.add_argument(
        "--out",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"output root for discovery artifacts (default: {DEFAULT_OUTPUT_ROOT})",
    )
    discover.add_argument(
        "--probe-model",
        default="",
        help="model slug to probe with a tiny read-only prompt",
    )
    discover.add_argument(
        "--ask-list",
        action="store_true",
        help="for Copilot, ask the CLI to list available model IDs as candidate discovery",
    )
    discover.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="timeout for each discovery command",
    )
    discover.set_defaults(handler=command_discover_models)

    finalize = subparsers.add_parser("finalize", help="write final.md from a synthesis file")
    finalize.add_argument("--run-dir", required=True, help="run directory from start")
    finalize.add_argument(
        "--from-file",
        required=True,
        help="markdown file containing the final synthesis",
    )
    finalize.add_argument(
        "--model",
        default="",
        help="actual resolved model used by the chair or final editor",
    )
    finalize.add_argument(
        "--decision-grade",
        default="",
        help="reader-facing decision grade, required outside smoke runs",
    )
    finalize.add_argument(
        "--model-diversity",
        default="",
        help="reader-facing model diversity label, required outside smoke runs",
    )
    finalize.add_argument(
        "--allow-procurement-ready",
        action="store_true",
        help=(
            "allow a procurement-ready decision grade for a budget or "
            "citation-failed research run"
        ),
    )
    finalize.add_argument("--force", action="store_true", help="overwrite existing final.md")
    finalize.set_defaults(handler=command_finalize)

    inspect_parser = subparsers.add_parser("inspect", help="show run completeness and models")
    inspect_parser.add_argument("--run-dir", required=True, help="run directory from start")
    inspect_parser.set_defaults(handler=command_inspect)

    return parser


def command_start(args: argparse.Namespace) -> int:
    config_path = resolve_preset(args.preset)
    config = load_config(config_path)
    profile = resolve_profile(args.profile, args.budget)
    config = apply_profile(config, profile)
    workdir = resolve_path(args.workdir)
    assert_dir(workdir, "workdir")
    output_root = resolve_path(args.out)
    brief = load_brief(topic=args.topic, brief_file=args.brief_file, workdir=workdir)
    plan = load_plan(plan_file=args.plan_file, profile=profile)

    run_dir = make_run_dir(output_root)
    ensure_run_dirs(run_dir)
    write_json(run_dir / "config.json", config)
    write_json(run_dir / "resolved-config.json", resolved_config(config, workdir))
    write_text(run_dir / "brief.md", brief)
    write_text(run_dir / "council-plan.md", plan)
    write_text(run_dir / "transcript.md", transcript_document(config, run_dir))
    write_prompt_stubs(run_dir=run_dir, config=config, extra_context=[])

    print(f"Run started: {run_dir}")
    print(f"Preset: {config_path}")
    print(f"Profile: {profile}")
    for warning in config.get("profile_warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)
    print(f"Plan: {run_dir / 'council-plan.md'}")
    print(f"Brief: {run_dir / 'brief.md'}")
    print(f"Prompt stubs: {run_dir / 'prompts'}")
    print(f"Transcript: {run_dir / 'transcript.md'}")
    print("Planned turns:")
    for index, turn in enumerate(config["turns"], start=1):
        print(
            f"- turn {index}: name={turn['name']} round={turn['round']} "
            f"seat={turn['seat']} role={turn['role']} model_slot={seat_model_slot(config, turn['seat'])}"
        )
    final_turn = config["final"]
    print(
        f"- final: name={final_turn['name']} seat={final_turn['seat']} "
        f"role={final_turn['role']} model_slot={seat_model_slot(config, final_turn['seat'])}"
    )
    return 0


def command_scaffold_run(args: argparse.Namespace) -> int:
    config_path = resolve_preset(args.preset)
    config = load_config(config_path)
    profile = resolve_profile(args.profile, args.budget)
    config = apply_profile(config, profile)
    workdir = resolve_path(args.workdir)
    assert_dir(workdir, "workdir")
    scaffold_dir = resolve_path(args.out)
    scaffold_dir.mkdir(parents=True, exist_ok=True)

    brief = load_brief(topic=args.topic, brief_file=args.brief_file, workdir=workdir)
    plan = draft_plan_document(config=config, profile=profile, workdir=workdir)
    write_json(scaffold_dir / "config.json", config)
    write_json(scaffold_dir / "resolved-config.json", resolved_config(config, workdir))
    write_text(scaffold_dir / "brief.md", brief)
    write_text(scaffold_dir / "council-plan.md", plan)

    prompts_dir = scaffold_dir / "prompts"
    extra_context = [str(resolve_path(value)) for value in args.extra_context_file]
    for turn in config["turns"]:
        write_text(
            prompts_dir / f"{slug(turn['name'])}.prompt.md",
            scaffold_prompt_document(
                config=config,
                turn=turn,
                run_dir_placeholder="<run-dir-after-start>",
                extra_context=extra_context,
            ),
        )

    write_text(
        scaffold_dir / "start-command.txt",
        scaffold_start_command(
            preset_arg=args.preset,
            profile=profile,
            scaffold_dir=scaffold_dir,
            workdir=workdir,
        ),
    )

    print(f"Scaffold written: {scaffold_dir}")
    print(f"Brief: {scaffold_dir / 'brief.md'}")
    print(f"Plan draft: {scaffold_dir / 'council-plan.md'}")
    print(f"Prompt stubs: {prompts_dir}")
    print(f"Start command: {scaffold_dir / 'start-command.txt'}")
    return 0


def command_run_shell_seat(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    config = load_run_config(run_dir)
    turn = planned_turn_by_name(config, args.turn)
    seat = config["seats"][turn["seat"]]
    profile = run_profile(config)

    prompt_source = prompt_file_for_external_seat(args.prompt_file, seat, turn, run_dir)
    if profile != "smoke" and not prompt_source:
        raise CouncilError("non-smoke external seats require --prompt-file or turn.prompt_file")
    if not prompt_source:
        raise CouncilError("pass --prompt-file for external seat execution")
    prompt_text = read_text(prompt_source)
    if not prompt_text.strip():
        raise CouncilError("external seat prompt file is empty")

    provider = args.provider or seat.get("provider", "shell")
    if provider not in EXTERNAL_PROVIDERS:
        raise CouncilError(f"external provider must be one of: {', '.join(EXTERNAL_PROVIDERS)}")
    mode = args.mode or seat.get("mode", "read-only")
    if mode not in EXTERNAL_MODES:
        raise CouncilError(f"external mode must be one of: {', '.join(EXTERNAL_MODES)}")
    timeout_seconds = args.timeout_seconds or int(seat.get("timeout_seconds", 1800))
    if timeout_seconds <= 0:
        raise CouncilError("--timeout-seconds must be > 0")

    cwd = resolve_external_cwd(args.cwd or seat.get("external_cwd", ""), run_dir)
    command = args.command or seat.get("command", "")
    executable_override = args.executable or seat.get("executable", "")
    requested_model = args.model or seat.get("model", "")
    prompt_transport = args.prompt_transport or seat.get("prompt_transport", "auto")
    if prompt_transport not in PROMPT_TRANSPORTS:
        raise CouncilError(f"prompt transport must be one of: {', '.join(PROMPT_TRANSPORTS)}")
    cursor_trust = args.cursor_trust or bool(seat.get("cursor_trust", False))

    external_dir = external_turn_dir(run_dir, turn)
    external_dir.mkdir(parents=True, exist_ok=True)
    external_prompt = external_dir / "prompt.md"
    stdout_path = external_dir / "stdout.txt"
    stderr_path = external_dir / "stderr.txt"
    response_path = external_dir / "response.md"
    metadata_path = external_dir / "metadata.json"
    write_text(external_prompt, ensure_trailing_newline(prompt_text))
    invocation = build_external_invocation(
        provider=provider,
        prompt=prompt_text,
        prompt_path=external_prompt,
        command=command,
        executable_override=executable_override,
        requested_model=requested_model,
        mode=mode,
        prompt_transport=prompt_transport,
        cursor_trust=cursor_trust,
    )

    started_at = dt.datetime.now(dt.timezone.utc)
    started_monotonic = time.monotonic()
    preflight = preflight_external_executable(invocation["argv"][0])
    result: Optional[subprocess.CompletedProcess[str]] = None
    error_message = ""
    if preflight["status"] == "ok":
        try:
            result = subprocess.run(
                invocation["argv"],
                input=invocation["stdin"],
                cwd=str(cwd),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            error_message = f"external seat timed out after {timeout_seconds}s"
            write_text(stdout_path, error.stdout or "")
            write_text(stderr_path, error.stderr or "")
        except OSError as error:
            error_message = f"failed to run external seat: {error}"
    else:
        error_message = preflight["message"]

    finished_at = dt.datetime.now(dt.timezone.utc)
    duration_seconds = round(time.monotonic() - started_monotonic, 3)
    stdout = result.stdout if result else read_text_if_exists(stdout_path)
    stderr = result.stderr if result else read_text_if_exists(stderr_path)
    exit_code = result.returncode if result else None
    response = normalize_external_response(stdout)
    write_text(stdout_path, stdout)
    write_text(stderr_path, stderr)
    write_text(response_path, response)

    metadata = external_run_metadata(
        config=config,
        turn=turn,
        provider=provider,
        mode=mode,
        requested_model=requested_model,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        invocation=invocation,
        preflight=preflight,
        prompt_path=external_prompt,
        prompt_text=prompt_text,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        response_path=response_path,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        exit_code=exit_code,
        error_message=error_message,
        prompt_transport=prompt_transport,
        cursor_trust=cursor_trust,
    )
    write_json(metadata_path, metadata)

    if error_message:
        raise CouncilError(f"{error_message}; metadata written to {metadata_path}")
    if exit_code != 0:
        raise CouncilError(
            f"external seat exited with code {exit_code}; metadata written to {metadata_path}"
        )
    if not response.strip():
        raise CouncilError(f"external seat produced empty stdout; metadata written to {metadata_path}")

    actual_model = requested_model or f"{provider} harness default"
    record_external_turn(
        run_dir=run_dir,
        config=config,
        turn=turn,
        response_path=response_path,
        prompt_path=external_prompt,
        actual_model=actual_model,
    )
    print(f"External seat recorded: {turn_output_path(run_dir, config, turn)}")
    print(f"External metadata: {metadata_path}")
    print(f"External response: {response_path}")
    print(f"Transcript: {run_dir / 'transcript.md'}")
    return 0


def command_discover_models(args: argparse.Namespace) -> int:
    if args.timeout_seconds <= 0:
        raise CouncilError("--timeout-seconds must be > 0")
    executable = args.executable or ("agent" if args.provider == "cursor" else "copilot")
    executable = find_executable(executable) or executable
    cwd = resolve_path(args.cwd) if args.cwd else Path.cwd().resolve()
    assert_dir(cwd, "discovery cwd")

    discovery_dir = make_discovery_dir(resolve_path(args.out), args.provider)
    runs: List[Dict[str, Any]] = []
    preflight = preflight_external_executable(executable)
    write_json(discovery_dir / "preflight.json", preflight)

    if args.provider == "cursor":
        runs.append(
            run_discovery_command(
                name="cursor-models",
                argv=[executable, "models"],
                cwd=cwd,
                timeout_seconds=args.timeout_seconds,
                output_dir=discovery_dir,
            )
        )
    elif args.ask_list:
        runs.append(
            run_discovery_command(
                name="copilot-list-candidate",
                argv=build_copilot_discovery_argv(
                    executable,
                    "List all available model IDs exposed by this local Copilot CLI session. "
                    "Return only model IDs, one per line, and include no prose.",
                    model="",
                ),
                cwd=cwd,
                timeout_seconds=args.timeout_seconds,
                output_dir=discovery_dir,
            )
        )

    if args.probe_model:
        if args.provider == "cursor":
            probe_argv = [
                executable,
                "--print",
                "--output-format",
                "text",
                "--mode",
                "ask",
                "--model",
                args.probe_model,
            ]
            probe_stdin = "Reply exactly: OK"
        else:
            probe_argv = build_copilot_discovery_argv(
                executable,
                "Reply exactly: OK",
                model=args.probe_model,
            )
            probe_stdin = None
        runs.append(
            run_discovery_command(
                name=f"probe-{slug(args.probe_model)}",
                argv=probe_argv,
                cwd=cwd,
                timeout_seconds=args.timeout_seconds,
                output_dir=discovery_dir,
                stdin=probe_stdin,
            )
        )

    write_json(
        discovery_dir / "metadata.json",
        {
            "provider": args.provider,
            "executable": executable,
            "cwd": str(cwd),
            "timeout_seconds": args.timeout_seconds,
            "probe_model": args.probe_model,
            "ask_list": args.ask_list,
            "preflight": preflight,
            "runs": runs,
        },
    )
    print(f"Discovery artifacts: {discovery_dir}")
    for item in runs:
        print(f"- {item['name']}: exit={item['exit_code']} stdout={item['stdout_file']}")
    if not runs:
        print("- no discovery command requested; preflight only")
    return 0


def command_record(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    config = load_run_config(run_dir)
    turn = planned_turn_by_name(config, args.turn)
    profile = run_profile(config)
    if profile != "smoke" and not args.prompt_file:
        raise CouncilError("non-smoke runs require --prompt-file for prompt fidelity")
    if profile != "smoke" and not args.model.strip():
        raise CouncilError("non-smoke runs require --model with the resolved model name")
    source = resolve_path(args.from_file)
    response = read_text(source)
    if not response.strip():
        raise CouncilError("recorded turn file is empty")

    stale_final = run_dir / "final.md"
    removed_stale_final = stale_final.exists()
    if removed_stale_final:
        stale_final.unlink()

    target = turn_output_path(run_dir, config, turn)
    prompt_target = turn_prompt_path(target)
    archive_existing_record(target)
    prompt_name = ""
    if args.prompt_file:
        prompt_source = resolve_path(args.prompt_file)
        prompt_text = read_text(prompt_source)
        write_text(prompt_target, ensure_trailing_newline(prompt_text))
        prompt_name = prompt_target.name
    elif prompt_target.exists():
        prompt_target.unlink()

    actual_model = args.model.strip() or "not-recorded"
    turn_doc = turn_document(
        config=config,
        turn=turn,
        order_index=planned_turn_index(config, turn["name"]),
        actual_model=actual_model,
        prompt_name=prompt_name,
        response=response,
    )
    write_text(target, turn_doc)
    rewrite_transcript(run_dir, config)

    print(f"Recorded turn: {target}")
    print(f"Transcript: {run_dir / 'transcript.md'}")
    if removed_stale_final:
        print("Removed stale final.md; run finalize again.")
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    config = load_run_config(run_dir)
    profile = run_profile(config)
    final_path = run_dir / "final.md"
    if final_path.exists() and not args.force:
        raise CouncilError(f"final output already exists: {final_path} (pass --force to replace it)")

    missing = missing_turns(run_dir, config)
    if missing and not args.force:
        joined = ", ".join(missing)
        raise CouncilError(f"cannot finalize; missing planned turns: {joined}")

    final_turn = config["final"]
    if profile != "smoke":
        if not args.model.strip():
            raise CouncilError("non-smoke finalization requires --model with the chair/final model")
        if not args.decision_grade.strip():
            raise CouncilError("non-smoke finalization requires --decision-grade")
        if not args.model_diversity.strip():
            raise CouncilError("non-smoke finalization requires --model-diversity")
        guard_decision_grade(
            run_dir=run_dir,
            config=config,
            decision_grade=args.decision_grade.strip(),
            allow_procurement_ready=args.allow_procurement_ready,
        )
    response = read_text(resolve_path(args.from_file))
    if not response.strip():
        raise CouncilError("recorded final file is empty")

    actual_model = args.model.strip() or "not-recorded"
    write_text(
        final_path,
        final_document(
            config=config,
            final_turn=final_turn,
            actual_model=actual_model,
            decision_grade=args.decision_grade.strip() or "not-recorded",
            model_diversity=args.model_diversity.strip() or "not-recorded",
            response=response,
        ),
    )
    rewrite_transcript(run_dir, config)

    print(f"Final output: {final_path}")
    print(f"Transcript: {run_dir / 'transcript.md'}")
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    config = load_run_config(run_dir)
    recorded = recorded_turn_names(run_dir, config)
    missing = missing_turns(run_dir, config)

    print(f"Run: {run_dir}")
    print(f"Brief: {exists_label(run_dir / 'brief.md')}")
    print(f"Config: {exists_label(run_dir / 'config.json')}")
    print(f"Transcript: {exists_label(run_dir / 'transcript.md')}")
    print(f"Final: {exists_label(run_dir / 'final.md')}")
    print(f"Rounds: {config['rounds']}")
    print(f"Planned turns: {len(config['turns'])}")
    print(f"Recorded turns: {len(recorded)}")
    print(f"Missing turns: {len(missing)}")
    if missing:
        print(f"- missing: {', '.join(missing)}")

    rounds = turns_by_round(config)
    for round_index in sorted(rounds):
        print(f"Round {round_index}:")
        for turn in rounds[round_index]:
            path = turn_output_path(run_dir, config, turn)
            status = "recorded" if path.exists() else "missing"
            model_slot = seat_model_slot(config, turn["seat"])
            model_label = f"slot:{model_slot}"
            if path.exists():
                meta = read_turn_metadata(path)
                used_model = meta.get("model", "not-recorded")
                model_label = f"{used_model} (slot {model_slot})"
            print(
                f"- [{status}] {turn['name']}: seat={turn['seat']} role={turn['role']} "
                f"model={model_label}"
            )

    final_turn = config["final"]
    final_model_slot = seat_model_slot(config, final_turn["seat"])
    final_model = f"slot:{final_model_slot}"
    final_path = run_dir / "final.md"
    if final_path.exists():
        meta = read_leading_bullets(final_path)
        used_model = meta.get("model", "not-recorded")
        final_model = f"{used_model} (slot {final_model_slot})"
        final_status = "written"
    else:
        final_status = "missing"
    print(
        f"Final: [{final_status}] {final_turn['name']}: seat={final_turn['seat']} "
        f"role={final_turn['role']} model={final_model}"
    )
    return 0


def load_config(path: Path) -> Dict[str, Any]:
    return validate_config(read_json(path), path)


def load_run_config(run_dir: Path) -> Dict[str, Any]:
    return load_config(run_dir / "config.json")


def validate_config(value: Any, source: Path) -> Dict[str, Any]:
    config = require_record(value, f"config `{source}`")
    name = required_string(config.get("name"), "config.name")
    stop_condition = required_string(config.get("stop_condition"), "config.stop_condition")
    rounds = required_int(config.get("rounds"), "config.rounds", minimum=1)

    seats = require_record(config.get("seats"), "config.seats")
    normalized_seats: Dict[str, Dict[str, Any]] = {}
    for seat_name, seat_value in seats.items():
        if not isinstance(seat_name, str) or not seat_name.strip():
            raise CouncilError("config.seats keys must be non-empty strings")
        seat = require_record(seat_value, f"config.seats.{seat_name}")
        normalized_seat: Dict[str, Any] = {
            "model_slot": required_string(
                seat.get("model_slot"), f"config.seats.{seat_name}.model_slot"
            )
        }
        for field_name in (
            "provider",
            "command",
            "executable",
            "model",
            "mode",
            "prompt_file",
            "external_cwd",
            "prompt_transport",
        ):
            optional = optional_string(seat.get(field_name), f"config.seats.{seat_name}.{field_name}")
            if optional:
                normalized_seat[field_name] = optional
        if "provider" in normalized_seat and normalized_seat["provider"] not in EXTERNAL_PROVIDERS:
            raise CouncilError(
                f"config.seats.{seat_name}.provider must be one of: {', '.join(EXTERNAL_PROVIDERS)}"
            )
        if "mode" in normalized_seat and normalized_seat["mode"] not in EXTERNAL_MODES:
            raise CouncilError(
                f"config.seats.{seat_name}.mode must be one of: {', '.join(EXTERNAL_MODES)}"
            )
        if (
            "prompt_transport" in normalized_seat
            and normalized_seat["prompt_transport"] not in PROMPT_TRANSPORTS
        ):
            raise CouncilError(
                f"config.seats.{seat_name}.prompt_transport must be one of: "
                f"{', '.join(PROMPT_TRANSPORTS)}"
            )
        cursor_trust = optional_bool(seat.get("cursor_trust"), f"config.seats.{seat_name}.cursor_trust")
        if cursor_trust is not None:
            normalized_seat["cursor_trust"] = cursor_trust
        timeout = seat.get("timeout_seconds")
        if timeout is not None:
            normalized_seat["timeout_seconds"] = required_int(
                timeout,
                f"config.seats.{seat_name}.timeout_seconds",
                minimum=1,
            )
        normalized_seats[seat_name] = normalized_seat
    if not normalized_seats:
        raise CouncilError("config.seats must not be empty")

    turns_value = config.get("turns")
    if not isinstance(turns_value, list) or not turns_value:
        raise CouncilError("config.turns must be a non-empty array")
    normalized_turns: List[Dict[str, Any]] = []
    seen_names = set()
    for index, raw_turn in enumerate(turns_value, start=1):
        turn = validate_turn(
            raw_turn,
            f"config.turns[{index - 1}]",
            seats=normalized_seats,
            allow_round=True,
            rounds=rounds,
        )
        if turn["name"] in seen_names:
            raise CouncilError(f"duplicate turn name `{turn['name']}` in config.turns")
        seen_names.add(turn["name"])
        normalized_turns.append(turn)

    final_turn = validate_turn(
        config.get("final"),
        "config.final",
        seats=normalized_seats,
        allow_round=False,
        rounds=rounds,
    )
    if final_turn["name"] in seen_names:
        raise CouncilError(f"final turn name `{final_turn['name']}` duplicates a planned turn")

    normalized: Dict[str, Any] = {
        "name": name,
        "stop_condition": stop_condition,
        "rounds": rounds,
        "seats": normalized_seats,
        "turns": normalized_turns,
        "final": final_turn,
    }
    profile = config.get("profile")
    if isinstance(profile, str) and profile.strip():
        if profile.strip() not in PROFILES:
            raise CouncilError(f"config.profile must be one of: {', '.join(PROFILES)}")
        normalized["profile"] = profile.strip()
    warnings = config.get("profile_warnings", [])
    if warnings:
        if not isinstance(warnings, list) or not all(
            isinstance(warning, str) and warning.strip() for warning in warnings
        ):
            raise CouncilError("config.profile_warnings must be an array of non-empty strings")
        normalized["profile_warnings"] = [warning.strip() for warning in warnings]
    return normalized


def validate_turn(
    value: Any,
    label: str,
    *,
    seats: Dict[str, Dict[str, Any]],
    allow_round: bool,
    rounds: int,
) -> Dict[str, Any]:
    turn = require_record(value, label)
    seat = required_string(turn.get("seat"), f"{label}.seat")
    if seat not in seats:
        raise CouncilError(f"{label}.seat references unknown seat `{seat}`")
    role = required_string(turn.get("role"), f"{label}.role")
    name = required_string(turn.get("name"), f"{label}.name")
    instruction = required_string(turn.get("instruction"), f"{label}.instruction")
    normalized: Dict[str, Any] = {
        "name": name,
        "seat": seat,
        "role": role,
        "instruction": instruction,
    }
    prompt_file = optional_string(turn.get("prompt_file"), f"{label}.prompt_file")
    if prompt_file:
        normalized["prompt_file"] = prompt_file
    if allow_round:
        normalized["round"] = required_int(turn.get("round"), f"{label}.round", minimum=1, maximum=rounds)
    return normalized


def load_brief(*, topic: str, brief_file: str, workdir: Path) -> str:
    if brief_file:
        return read_text(resolve_path(brief_file))
    if not topic.strip():
        raise CouncilError("pass --topic or --brief-file")
    return (
        "# Council Brief\n\n"
        "## Topic\n"
        f"{topic.strip()}\n\n"
        "## Workspace\n"
        f"`{workdir}`\n\n"
        "## Deliverable\n"
        "Produce a final Markdown document for the user.\n\n"
        "## Chair Rules\n"
        "- Use the supplied brief and transcript paths, not the chair's private history.\n"
        "- Preserve disagreement instead of smoothing it away.\n"
        "- This is a read-only council: do not modify project files.\n"
    )


def load_plan(*, plan_file: str, profile: str) -> str:
    if plan_file:
        return ensure_trailing_newline(read_text(resolve_path(plan_file)))
    if profile != "smoke":
        raise CouncilError("non-smoke runs require --plan-file with the confirmed preflight plan")
    return (
        "# Council Plan\n\n"
        "- profile: smoke\n"
        "- confirmation: not required for smoke plumbing runs\n"
        "- decision_grade: not decision-grade\n"
    )


def draft_plan_document(*, config: Dict[str, Any], profile: str, workdir: Path) -> str:
    lines = [
        "# Council Plan",
        "",
        "- status: DRAFT - chair must confirm with the user before `start` for non-smoke runs",
        f"- preset: {config['name']}",
        f"- profile: {profile}",
        f"- target_workdir: `{workdir}`",
        f"- stop_condition: {config['stop_condition']}",
        "- decision_grade: TODO",
        "- model_diversity: TODO",
        "- confirmation: TODO",
        "",
        "## Seats",
        "",
    ]
    for seat_name, seat in config["seats"].items():
        provider = seat.get("provider", "chair/subagent")
        model = seat.get("model", "TODO")
        lines.append(f"- `{seat_name}`: slot `{seat['model_slot']}`, provider `{provider}`, model `{model}`")
    lines.extend(["", "## Turns", ""])
    for index, turn in enumerate(config["turns"], start=1):
        lines.append(
            f"{index}. `{turn['name']}`: round {turn['round']}, seat `{turn['seat']}`, "
            f"role `{turn['role']}`"
        )
    final_turn = config["final"]
    lines.extend(
        [
            "",
            "## External Seat Access",
            "",
            "| seat | provider | cwd/access envelope | trust authorization | discovery/probe artifact |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    external_rows = 0
    for seat_name, seat in config["seats"].items():
        provider = seat.get("provider", "")
        if not provider:
            continue
        external_rows += 1
        cwd = seat.get("external_cwd", "TODO")
        trust = "TODO" if provider == "cursor" else "n/a"
        lines.append(f"| `{seat_name}` | `{provider}` | `{cwd}` | {trust} | TODO |")
    if external_rows == 0:
        lines.append("| n/a | n/a | n/a | n/a | n/a |")
    lines.extend(
        [
            "",
            "## Final",
            "",
            f"- `{final_turn['name']}`: seat `{final_turn['seat']}`, role `{final_turn['role']}`",
            "",
            "## Limitations",
            "",
            "- TODO: record model discovery/probe limitations.",
            "- TODO: record external CLI cwd/access envelope if using Cursor, Copilot, or shell seats.",
        ]
    )
    return "\n".join(lines) + "\n"


def scaffold_prompt_document(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    run_dir_placeholder: str,
    extra_context: List[str],
) -> str:
    run_dir = Path(run_dir_placeholder)
    prior_turns = [candidate for candidate in config["turns"] if candidate["round"] < turn["round"]]
    lines = [
        "# Agent Council Seat Prompt",
        "",
        f"You are the `{turn['seat']}` seat for an `agent-council` run.",
        "",
        "## Role",
        "",
        turn["instruction"].strip(),
        "",
        "## Read These Files",
        "",
        f"- Brief: `{run_dir / 'brief.md'}`",
        f"- Transcript: `{run_dir / 'transcript.md'}`",
        f"- Council plan: `{run_dir / 'council-plan.md'}`",
    ]
    if prior_turns:
        lines.append("- Prior turn files:")
        for prior in prior_turns:
            lines.append(f"  - `{turn_output_path(run_dir, config, prior)}`")
    if extra_context:
        lines.append("- Extra context files:")
        lines.extend(f"  - `{path}`" for path in extra_context)
    lines.extend(
        [
            "",
            "## Constraints",
            "",
            "- Read-only: do not modify project files.",
            "- Work from the files listed above, not from private chair context.",
            "- Preserve material uncertainty and disagreement.",
            "- Cite file paths or source URLs for claims that depend on evidence.",
            "",
            "## Output Contract",
            "",
            "- Emit the complete deliverable in this response/stdout.",
            "- Do not save only a separate artifact or session note.",
            "- If evidence is missing, say exactly what is missing and keep the claim downgraded.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_prompt_stubs(*, run_dir: Path, config: Dict[str, Any], extra_context: List[str]) -> Path:
    prompts_dir = run_dir / "prompts"
    for turn in config["turns"]:
        write_text(
            prompts_dir / f"{slug(turn['name'])}.prompt.md",
            scaffold_prompt_document(
                config=config,
                turn=turn,
                run_dir_placeholder=str(run_dir),
                extra_context=extra_context,
            ),
        )
    return prompts_dir


def scaffold_start_command(
    *,
    preset_arg: str,
    profile: str,
    scaffold_dir: Path,
    workdir: Path,
) -> str:
    argv = [
        "python3",
        str(Path(__file__).resolve()),
        "start",
        "--preset",
        preset_arg,
        "--profile",
        profile,
        "--brief-file",
        str(scaffold_dir / "brief.md"),
        "--plan-file",
        str(scaffold_dir / "council-plan.md"),
        "--workdir",
        str(workdir),
        "--out",
        str(scaffold_dir),
    ]
    return shlex.join(argv) + "\n"


def resolve_preset(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.exists():
        return candidate.resolve()

    presets_dir = skill_dir() / "assets" / "presets"
    file_name = value if value.endswith(".json") else f"{value}.json"
    preset = presets_dir / file_name
    if preset.exists():
        return preset.resolve()

    available = ", ".join(sorted(path.stem for path in presets_dir.glob("*.json")))
    raise CouncilError(f"unknown preset `{value}`. Available presets: {available}")


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


def make_discovery_dir(output_root: Path, provider: str) -> Path:
    discovery_root = output_root / "model-discovery"
    discovery_root.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = discovery_root / f"{timestamp}-{provider}"
    suffix = 1
    while candidate.exists():
        candidate = discovery_root / f"{timestamp}-{provider}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def ensure_run_dirs(run_dir: Path) -> None:
    (run_dir / "turns").mkdir(parents=True, exist_ok=True)


def resolve_profile(profile: str, budget: bool) -> str:
    if budget and profile not in ("standard", "budget"):
        raise CouncilError("--budget cannot be combined with --profile other than budget")
    if budget:
        return "budget"
    return profile


def apply_profile(config: Dict[str, Any], profile: str) -> Dict[str, Any]:
    config["profile"] = profile
    warnings = profile_warnings(config["name"], profile)
    if warnings:
        config["profile_warnings"] = warnings
    else:
        config.pop("profile_warnings", None)
    return config


def resolved_config(config: Dict[str, Any], workdir: Path) -> Dict[str, Any]:
    value = json.loads(json.dumps(config))
    value["workdir"] = str(workdir)
    value["resolved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return value


def profile_warnings(preset_name: str, profile: str) -> List[str]:
    warnings: List[str] = []
    if profile == "budget" and preset_name == "research-dossier":
        warnings.append(
            "budget profile is using full research-dossier; consider "
            "research-dossier-budget unless the user intentionally asked for "
            "the fuller workflow"
        )
    if profile in ("standard", "premium") and preset_name == "research-dossier-budget":
        warnings.append(
            f"{profile} profile is using research-dossier-budget; consider "
            "research-dossier when the user wants fuller critique coverage"
        )
    if profile == "smoke" and preset_name != "selftest":
        warnings.append(
            "smoke profile is intended for plumbing checks; substantive output "
            "from this run is not decision-grade"
        )
    return warnings


def run_profile(config: Dict[str, Any]) -> str:
    profile = config.get("profile", "standard")
    if profile not in PROFILES:
        raise CouncilError(f"run profile must be one of: {', '.join(PROFILES)}")
    return profile


def transcript_document(config: Dict[str, Any], run_dir: Path) -> str:
    sections = [
        "# Agent Council Transcript",
        "",
        f"- council: {config['name']}",
        f"- run_dir: {run_dir}",
        f"- profile: {run_profile(config)}",
        f"- rounds: {config['rounds']}",
        f"- stop_condition: {config['stop_condition']}",
        "- council_plan: council-plan.md",
    ]
    warnings = config.get("profile_warnings", [])
    if warnings:
        sections.append("- profile_warnings:")
        sections.extend(f"  - {warning}" for warning in warnings)
    sections.extend(["", ""])
    for turn in config["turns"]:
        path = turn_output_path(run_dir, config, turn)
        if path.exists():
            sections.extend([read_text(path).rstrip(), ""])
    final_path = run_dir / "final.md"
    if final_path.exists():
        sections.extend(["# Final Output", "", f"See `{final_path.name}`.", ""])
    return "\n".join(sections).rstrip() + "\n"


def rewrite_transcript(run_dir: Path, config: Dict[str, Any]) -> None:
    write_text(run_dir / "transcript.md", transcript_document(config, run_dir))


def final_document(
    *,
    config: Dict[str, Any],
    final_turn: Dict[str, Any],
    actual_model: str,
    decision_grade: str,
    model_diversity: str,
    response: str,
) -> str:
    model_slot = seat_model_slot(config, final_turn["seat"])
    lines = [
        "# Final Output",
        "",
        f"- council: {config['name']}",
        f"- profile: {run_profile(config)}",
        f"- decision_grade: {decision_grade}",
        f"- model_diversity: {model_diversity}",
        f"- name: {final_turn['name']}",
        f"- seat: {final_turn['seat']}",
        f"- role: {final_turn['role']}",
        f"- model_slot: {model_slot}",
        f"- model: {actual_model}",
        "- confirmed_plan: council-plan.md",
        "- transcript: transcript.md",
        "",
        response.rstrip(),
        "",
    ]
    return "\n".join(lines)


def guard_decision_grade(
    *,
    run_dir: Path,
    config: Dict[str, Any],
    decision_grade: str,
    allow_procurement_ready: bool,
) -> None:
    if not claims_procurement_ready(decision_grade):
        return
    if allow_procurement_ready:
        return
    if run_profile(config) == "budget":
        raise CouncilError(
            "budget runs must not finalize as procurement-ready without "
            "--allow-procurement-ready"
        )
    if (
        is_research_dossier(config)
        and citation_audit_failed(run_dir, config)
        and not citation_reaudit_passed(run_dir, config)
    ):
        raise CouncilError(
            "research dossier recorded CITATION_INTEGRITY: FAIL without a "
            "clean re-audit pass; do not finalize as procurement-ready without "
            "--allow-procurement-ready"
        )


def claims_procurement_ready(decision_grade: str) -> bool:
    normalized = re.sub(r"[\s_-]+", " ", decision_grade.lower()).strip()
    if re.search(r"\bnot\s+procurement\s+ready\b", normalized):
        return False
    return bool(
        re.search(r"\bprocurement\s+ready\b", normalized)
        or re.search(r"\bpurchase\s+ready\b", normalized)
        or re.search(r"\brollout\s+ready\b", normalized)
    )


def is_research_dossier(config: Dict[str, Any]) -> bool:
    return config["name"].startswith("research-dossier")


def citation_audit_failed(run_dir: Path, config: Dict[str, Any]) -> bool:
    for turn in config["turns"]:
        if turn["name"] != "citation-audit" and turn["role"] != "citation_auditor":
            continue
        path = turn_output_path(run_dir, config, turn)
        if path.exists() and "CITATION_INTEGRITY: FAIL" in turn_response_text(path):
            return True
    return False


def citation_reaudit_passed(run_dir: Path, config: Dict[str, Any]) -> bool:
    for turn in config["turns"]:
        if not is_reaudit_turn(turn):
            continue
        path = turn_output_path(run_dir, config, turn)
        if not path.exists():
            continue
        content = turn_response_text(path)
        if "CITATION_INTEGRITY: PASS" in content and "CITATION_INTEGRITY: FAIL" not in content:
            return True
    return False


def is_reaudit_turn(turn: Dict[str, Any]) -> bool:
    name = turn["name"].lower()
    role = turn["role"].lower()
    return (
        "reaudit" in name
        or "re-audit" in name
        or "reauditor" in role
        or "re-auditor" in role
    )


def turn_response_text(path: Path) -> str:
    text = read_text(path)
    marker = "\n### Response\n\n"
    if marker not in text:
        return text
    return text.split(marker, 1)[1]


def turn_document(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    order_index: int,
    actual_model: str,
    prompt_name: str,
    response: str,
) -> str:
    model_slot = seat_model_slot(config, turn["seat"])
    lines = [
        f"## Turn {order_index}: {turn['seat']} / {turn['role']}",
        "",
        f"- round: {turn['round']}",
        f"- name: {turn['name']}",
        f"- seat: {turn['seat']}",
        f"- role: {turn['role']}",
        f"- model_slot: {model_slot}",
        f"- model: {actual_model}",
        f"- prompt: {prompt_name or 'not-recorded'}",
        f"- recorded_at: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        "",
        "### Instruction",
        "",
        turn["instruction"].strip(),
        "",
        "### Response",
        "",
        response.rstrip(),
        "",
    ]
    return "\n".join(lines)


def record_external_turn(
    *,
    run_dir: Path,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    response_path: Path,
    prompt_path: Path,
    actual_model: str,
) -> None:
    stale_final = run_dir / "final.md"
    if stale_final.exists():
        stale_final.unlink()

    target = turn_output_path(run_dir, config, turn)
    prompt_target = turn_prompt_path(target)
    archive_existing_record(target)
    response = read_text(response_path)
    prompt_text = read_text(prompt_path)
    write_text(prompt_target, ensure_trailing_newline(prompt_text))
    write_text(
        target,
        turn_document(
            config=config,
            turn=turn,
            order_index=planned_turn_index(config, turn["name"]),
            actual_model=actual_model,
            prompt_name=prompt_target.name,
            response=response,
        ),
    )
    rewrite_transcript(run_dir, config)


def planned_turn_by_name(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    for turn in config["turns"]:
        if turn["name"] == name:
            return turn
    available = ", ".join(turn["name"] for turn in config["turns"])
    raise CouncilError(f"unknown turn `{name}`. Planned turns: {available}")


def planned_turn_index(config: Dict[str, Any], name: str) -> int:
    for index, turn in enumerate(config["turns"], start=1):
        if turn["name"] == name:
            return index
    raise CouncilError(f"unknown turn `{name}`")


def turns_by_round(config: Dict[str, Any]) -> Dict[int, List[Dict[str, Any]]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for turn in config["turns"]:
        grouped.setdefault(turn["round"], []).append(turn)
    return grouped


def missing_turns(run_dir: Path, config: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for turn in config["turns"]:
        if not turn_output_path(run_dir, config, turn).exists():
            missing.append(turn["name"])
    return missing


def recorded_turn_names(run_dir: Path, config: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for turn in config["turns"]:
        if turn_output_path(run_dir, config, turn).exists():
            names.append(turn["name"])
    return names


def turn_output_path(run_dir: Path, config: Dict[str, Any], turn: Dict[str, Any]) -> Path:
    order_index = planned_turn_index(config, turn["name"])
    seat_part = slug(turn["seat"])
    role_part = slug(turn["role"])
    return run_dir / "turns" / f"{order_index:03d}-r{turn['round']:02d}-{seat_part}-{role_part}.md"


def turn_prompt_path(turn_path: Path) -> Path:
    return turn_path.with_name(turn_path.stem + ".prompt.md")


def external_turn_dir(run_dir: Path, turn: Dict[str, Any]) -> Path:
    return run_dir / "external" / slug(turn["name"])


def seat_model_slot(config: Dict[str, Any], seat_name: str) -> str:
    return config["seats"][seat_name]["model_slot"]


def archive_existing_record(target: Path) -> None:
    prompt_target = turn_prompt_path(target)
    existing = [path for path in (target, prompt_target) if path.exists()]
    if not existing:
        return
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    attempts_dir = target.parent / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    for path in existing:
        if path == prompt_target:
            archive_name = f"{target.stem}-{timestamp}.prompt.md"
        else:
            archive_name = f"{target.stem}-{timestamp}.md"
        path.rename(attempts_dir / archive_name)


def read_turn_metadata(path: Path) -> Dict[str, str]:
    return read_leading_bullets(path)


def read_leading_bullets(path: Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    in_block = False
    for line in read_text(path).splitlines():
        is_bullet = line.startswith("- ")
        if not in_block:
            if is_bullet:
                in_block = True
            else:
                continue
        if not is_bullet:
            break
        if ": " in line:
            key, value = line[2:].split(": ", 1)
            metadata[key] = value
    return metadata


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def prompt_file_for_external_seat(
    prompt_file: str,
    seat: Dict[str, Any],
    turn: Dict[str, Any],
    run_dir: Path,
) -> Optional[Path]:
    value = prompt_file or turn.get("prompt_file", "") or seat.get("prompt_file", "")
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        run_candidate = run_dir / candidate
        if run_candidate.exists():
            return run_candidate.resolve()
        cwd_candidate = Path.cwd() / candidate
        if cwd_candidate.exists():
            return cwd_candidate.resolve()
        skill_candidate = skill_dir() / candidate
        if skill_candidate.exists():
            return skill_candidate.resolve()
        candidate = cwd_candidate
    return candidate.resolve()


def resolve_external_cwd(cwd_value: str, run_dir: Path) -> Path:
    if cwd_value:
        cwd = resolve_path(cwd_value)
    else:
        cwd = resolved_run_workdir(run_dir) or run_dir
    assert_dir(cwd, "external cwd")
    return cwd


def resolved_run_workdir(run_dir: Path) -> Optional[Path]:
    resolved_path = run_dir / "resolved-config.json"
    if not resolved_path.exists():
        return None
    try:
        value = json.loads(read_text(resolved_path))
    except json.JSONDecodeError:
        return None
    workdir = value.get("workdir")
    if not isinstance(workdir, str) or not workdir.strip():
        return None
    return Path(workdir).expanduser().resolve()


def build_external_invocation(
    *,
    provider: str,
    prompt: str,
    prompt_path: Path,
    command: str,
    executable_override: str,
    requested_model: str,
    mode: str,
    prompt_transport: str,
    cursor_trust: bool,
) -> Dict[str, Any]:
    if provider == "shell":
        return build_shell_invocation(
            command=command,
            prompt=prompt,
            prompt_path=prompt_path,
            mode=mode,
        )
    if provider == "cursor":
        return build_cursor_invocation(
            executable=executable_override or "agent",
            prompt=prompt,
            requested_model=requested_model,
            mode=mode,
            prompt_transport=prompt_transport,
            cursor_trust=cursor_trust,
        )
    if provider == "copilot":
        return build_copilot_invocation(
            executable=executable_override or "copilot",
            prompt=prompt,
            requested_model=requested_model,
            mode=mode,
            prompt_transport=prompt_transport,
        )
    raise CouncilError(f"unknown external provider `{provider}`")


def build_shell_invocation(
    *,
    command: str,
    prompt: str,
    prompt_path: Path,
    mode: str,
) -> Dict[str, Any]:
    if not command.strip():
        raise CouncilError("shell provider requires --command or seat.command")
    argv = shlex.split(command)
    if not argv:
        raise CouncilError("shell provider command is empty")
    stdin = prompt
    argv_for_audit = list(argv)
    for index, value in enumerate(argv):
        if "{prompt}" in value:
            argv[index] = value.replace("{prompt}", prompt)
            argv_for_audit[index] = value.replace("{prompt}", "{prompt}")
            stdin = None
        if "{prompt_file}" in value:
            argv[index] = value.replace("{prompt_file}", str(prompt_path))
            argv_for_audit[index] = value.replace("{prompt_file}", str(prompt_path))
            stdin = None
    return {
        "argv": resolve_external_argv(argv),
        "argv_for_audit": argv_for_audit,
        "stdin": stdin,
        "stdin_prompt": stdin is not None,
        "cursor_trust": False,
        "prompt_transport": "stdin" if stdin is not None else "argument",
        "read_only_strategy": (
            "caller-provided shell command; read-only is not guaranteed by the helper"
            if mode == "read-only"
            else "caller explicitly selected unrestricted shell execution"
        ),
    }


def build_cursor_invocation(
    *,
    executable: str,
    prompt: str,
    requested_model: str,
    mode: str,
    prompt_transport: str,
    cursor_trust: bool,
) -> Dict[str, Any]:
    argv = [executable, "--print", "--output-format", "text"]
    if cursor_trust:
        argv.append("--trust")
    if mode == "read-only":
        argv.extend(["--mode", "ask"])
    if requested_model:
        argv.extend(["--model", requested_model])
    use_stdin = prompt_transport in ("auto", "stdin")
    if not use_stdin:
        argv.append(prompt)
    return {
        "argv": resolve_external_argv(argv),
        "argv_for_audit": redact_prompt_argument(argv, prompt),
        "stdin": prompt if use_stdin else None,
        "stdin_prompt": use_stdin,
        "read_only_strategy": (
            "Cursor Agent print mode with --mode ask; no --force/--yolo is added"
            if mode == "read-only"
            else "Cursor Agent print mode without read-only helper flags"
        ),
        "cursor_trust": cursor_trust,
        "prompt_transport": "stdin" if use_stdin else "argument",
    }


def build_copilot_invocation(
    *,
    executable: str,
    prompt: str,
    requested_model: str,
    mode: str,
    prompt_transport: str,
) -> Dict[str, Any]:
    if prompt_transport == "stdin":
        raise CouncilError("copilot provider does not support prompt_transport=stdin")
    argv = [
        executable,
        "--no-color",
        "--no-auto-update",
        "--no-remote",
        "--stream",
        "off",
        "--silent",
    ]
    if mode == "read-only":
        argv.append("--plan")
    if requested_model:
        argv.extend(["--model", requested_model])
    argv.extend(["--prompt", prompt])
    return {
        "argv": resolve_external_argv(argv),
        "argv_for_audit": redact_prompt_argument(argv, prompt),
        "stdin": None,
        "stdin_prompt": False,
        "cursor_trust": False,
        "prompt_transport": "argument",
        "read_only_strategy": (
            "GitHub Copilot CLI non-interactive prompt with --plan; no --allow-all/--yolo is added"
            if mode == "read-only"
            else "GitHub Copilot CLI non-interactive prompt without read-only helper flags"
        ),
    }


def build_copilot_discovery_argv(executable: str, prompt: str, *, model: str) -> List[str]:
    argv = [
        executable,
        "--no-color",
        "--no-auto-update",
        "--no-remote",
        "--no-custom-instructions",
        "--disable-builtin-mcps",
        "--stream",
        "off",
        "--silent",
        "--plan",
    ]
    if model:
        argv.extend(["--model", model])
    argv.extend(["--prompt", prompt])
    return argv


def run_discovery_command(
    *,
    name: str,
    argv: List[str],
    cwd: Path,
    timeout_seconds: int,
    output_dir: Path,
    stdin: Optional[str] = None,
) -> Dict[str, Any]:
    started_at = dt.datetime.now(dt.timezone.utc)
    started_monotonic = time.monotonic()
    stdout_path = output_dir / f"{name}.stdout.txt"
    stderr_path = output_dir / f"{name}.stderr.txt"
    error_message = ""
    result: Optional[subprocess.CompletedProcess[str]] = None
    try:
        result = subprocess.run(
            argv,
            input=stdin,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        error_message = f"discovery command timed out after {timeout_seconds}s"
        write_text(stdout_path, error.stdout or "")
        write_text(stderr_path, error.stderr or "")
    except OSError as error:
        error_message = f"failed to run discovery command: {error}"

    finished_at = dt.datetime.now(dt.timezone.utc)
    stdout = result.stdout if result else read_text_if_exists(stdout_path)
    stderr = result.stderr if result else read_text_if_exists(stderr_path)
    write_text(stdout_path, stdout)
    write_text(stderr_path, stderr)
    return {
        "name": name,
        "argv": redact_discovery_prompt(argv),
        "stdin_prompt": stdin is not None,
        "cwd": str(cwd),
        "stdout_file": str(stdout_path),
        "stderr_file": str(stderr_path),
        "exit_code": result.returncode if result else None,
        "error": error_message,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(time.monotonic() - started_monotonic, 3),
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
    }


def redact_discovery_prompt(argv: List[str]) -> List[str]:
    redacted = list(argv)
    for index, value in enumerate(redacted[:-1]):
        if value == "--prompt":
            redacted[index + 1] = "{prompt}"
    return redacted


def resolve_external_argv(argv: List[str]) -> List[str]:
    resolved = find_executable(argv[0]) or argv[0]
    return [resolved] + argv[1:]


def find_executable(value: str) -> str:
    path = Path(value).expanduser()
    if path.parent != Path(".") or path.is_absolute():
        if path.exists():
            return str(path.resolve())
        return ""
    found = shutil.which(value)
    return found or ""


def preflight_external_executable(executable: str) -> Dict[str, Any]:
    version_argv = [executable, "--version"]
    try:
        result = subprocess.run(
            version_argv,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except OSError as error:
        return {
            "status": "failed",
            "message": f"failed to run version command for {executable}: {error}",
            "version_argv": version_argv,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "message": f"version command timed out for {executable}",
            "version_argv": version_argv,
        }
    return {
        "status": "ok",
        "message": "version command completed",
        "version_argv": version_argv,
        "version_exit_code": result.returncode,
        "version_stdout": result.stdout.strip(),
        "version_stderr": result.stderr.strip(),
    }


def external_run_metadata(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    provider: str,
    mode: str,
    requested_model: str,
    cwd: Path,
    timeout_seconds: int,
    invocation: Dict[str, Any],
    preflight: Dict[str, Any],
    prompt_path: Path,
    prompt_text: str,
    stdout_path: Path,
    stderr_path: Path,
    response_path: Path,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    duration_seconds: float,
    exit_code: Optional[int],
    error_message: str,
    prompt_transport: str,
    cursor_trust: bool,
) -> Dict[str, Any]:
    model_slot = seat_model_slot(config, turn["seat"])
    return {
        "provider": provider,
        "mode": mode,
        "read_only_strategy": invocation["read_only_strategy"],
        "turn": turn["name"],
        "seat": turn["seat"],
        "role": turn["role"],
        "model_slot": model_slot,
        "model": requested_model or f"{provider} harness default",
        "cwd": str(cwd),
        "timeout_seconds": timeout_seconds,
        "argv": invocation["argv_for_audit"],
        "stdin_prompt": invocation["stdin_prompt"],
        "prompt_transport": invocation.get("prompt_transport", prompt_transport),
        "cursor_trust": invocation.get("cursor_trust", cursor_trust),
        "preflight": preflight,
        "prompt_file": str(prompt_path),
        "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "stdout_file": str(stdout_path),
        "stderr_file": str(stderr_path),
        "response_file": str(response_path),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "exit_code": exit_code,
        "error": error_message,
    }


def normalize_external_response(stdout: str) -> str:
    return ensure_trailing_newline(stdout.strip()) if stdout.strip() else ""


def redact_prompt_argument(argv: List[str], prompt: str) -> List[str]:
    return ["{prompt}" if value == prompt else value for value in argv]


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return read_text(path)


def resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def read_json(path: Path) -> Any:
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError as error:
        raise CouncilError(f"failed to parse JSON {path}: {error}")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2) + "\n")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CouncilError(f"file not found: {path}")
    except OSError as error:
        raise CouncilError(f"failed to read {path}: {error}")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def assert_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise CouncilError(f"{label} not found or not a directory: {path}")


def exists_label(path: Path) -> str:
    return "yes" if path.exists() else "no"


def require_record(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise CouncilError(f"{field_name} must be an object")
    return value


def required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CouncilError(f"{field_name} must be a non-empty string")
    return value.strip()


def optional_string(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CouncilError(f"{field_name} must be a string")
    return value.strip()


def optional_bool(value: Any, field_name: str) -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise CouncilError(f"{field_name} must be a boolean")
    return value


def required_int(value: Any, field_name: str, *, minimum: int, maximum: Optional[int] = None) -> int:
    if not isinstance(value, int):
        raise CouncilError(f"{field_name} must be an integer")
    if value < minimum:
        raise CouncilError(f"{field_name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise CouncilError(f"{field_name} must be <= {maximum}")
    return value


def slug(value: str) -> str:
    lowered = value.lower()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return replaced or "item"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except CouncilError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
