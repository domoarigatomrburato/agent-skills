#!/usr/bin/env python3

"""Thin blackboard helper for the cursor-council skill."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_OUTPUT_ROOT = "/tmp/cursor-council"


class CouncilError(Exception):
    """User-facing council error."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="council.py",
        description="Create and maintain cursor-council run blackboards.",
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
    start.set_defaults(handler=command_start)

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
        help="actual model used; defaults to the seat's bound model",
    )
    record.set_defaults(handler=command_record)

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
        help="actual model used for the final; defaults to the final seat's bound model",
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
    workdir = resolve_path(args.workdir)
    assert_dir(workdir, "workdir")
    output_root = resolve_path(args.out)
    brief = load_brief(topic=args.topic, brief_file=args.brief_file, workdir=workdir)

    run_dir = make_run_dir(output_root)
    ensure_run_dirs(run_dir)
    write_json(run_dir / "config.json", config)
    write_text(run_dir / "brief.md", brief)
    write_text(run_dir / "transcript.md", transcript_document(config, run_dir))

    print(f"Run started: {run_dir}")
    print(f"Preset: {config_path}")
    print(f"Brief: {run_dir / 'brief.md'}")
    print(f"Transcript: {run_dir / 'transcript.md'}")
    print("Planned turns:")
    for index, turn in enumerate(config["turns"], start=1):
        print(
            f"- turn {index}: name={turn['name']} round={turn['round']} "
            f"seat={turn['seat']} role={turn['role']} model={seat_model(config, turn['seat'])}"
        )
    final_turn = config["final"]
    print(
        f"- final: name={final_turn['name']} seat={final_turn['seat']} "
        f"role={final_turn['role']} model={seat_model(config, final_turn['seat'])}"
    )
    return 0


def command_record(args: argparse.Namespace) -> int:
    run_dir = resolve_path(args.run_dir)
    assert_dir(run_dir, "run-dir")
    config = load_run_config(run_dir)
    turn = planned_turn_by_name(config, args.turn)
    source = resolve_path(args.from_file)
    response = read_text(source).strip()
    if not response:
        raise CouncilError("recorded turn file is empty")

    stale_final = run_dir / "final.md"
    removed_stale_final = stale_final.exists()
    if removed_stale_final:
        stale_final.unlink()

    target = turn_output_path(run_dir, config, turn)
    prompt_target = turn_prompt_path(target)
    prompt_name = ""
    if args.prompt_file:
        prompt_source = resolve_path(args.prompt_file)
        prompt_text = read_text(prompt_source).rstrip()
        write_text(prompt_target, prompt_text + ("\n" if prompt_text else ""))
        prompt_name = prompt_target.name
    elif prompt_target.exists():
        prompt_target.unlink()

    actual_model = args.model.strip() or seat_model(config, turn["seat"])
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
    final_path = run_dir / "final.md"
    if final_path.exists() and not args.force:
        raise CouncilError(f"final output already exists: {final_path} (pass --force to replace it)")

    missing = missing_turns(run_dir, config)
    if missing and not args.force:
        joined = ", ".join(missing)
        raise CouncilError(f"cannot finalize; missing planned turns: {joined}")

    final_turn = config["final"]
    response = read_text(resolve_path(args.from_file)).strip()
    if not response:
        raise CouncilError("recorded final file is empty")

    actual_model = args.model.strip() or seat_model(config, final_turn["seat"])
    write_text(final_path, final_document(config, final_turn, actual_model, response))
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
            model_label = seat_model(config, turn["seat"])
            if path.exists():
                meta = read_turn_metadata(path)
                used_model = meta.get("model", model_label)
                if used_model != model_label:
                    model_label = f"{used_model} (planned {model_label})"
                else:
                    model_label = used_model
            print(
                f"- [{status}] {turn['name']}: seat={turn['seat']} role={turn['role']} "
                f"model={model_label}"
            )

    final_turn = config["final"]
    final_model = seat_model(config, final_turn["seat"])
    final_path = run_dir / "final.md"
    if final_path.exists():
        meta = read_leading_bullets(final_path)
        used_model = meta.get("model", final_model)
        if used_model != final_model:
            final_model = f"{used_model} (planned {final_model})"
        else:
            final_model = used_model
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
    normalized_seats: Dict[str, Dict[str, str]] = {}
    for seat_name, seat_value in seats.items():
        if not isinstance(seat_name, str) or not seat_name.strip():
            raise CouncilError("config.seats keys must be non-empty strings")
        seat = require_record(seat_value, f"config.seats.{seat_name}")
        normalized_seats[seat_name] = {
            "model": required_string(seat.get("model"), f"config.seats.{seat_name}.model")
        }
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

    return {
        "name": name,
        "stop_condition": stop_condition,
        "rounds": rounds,
        "seats": normalized_seats,
        "turns": normalized_turns,
        "final": final_turn,
    }


def validate_turn(
    value: Any,
    label: str,
    *,
    seats: Dict[str, Dict[str, str]],
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
        "- Use the supplied brief and transcript, not the chair's private history.\n"
        "- Preserve disagreement instead of smoothing it away.\n"
        "- This is a read-only council: do not modify project files.\n"
    )


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


def ensure_run_dirs(run_dir: Path) -> None:
    (run_dir / "turns").mkdir(parents=True, exist_ok=True)


def transcript_document(config: Dict[str, Any], run_dir: Path) -> str:
    sections = [
        "# Cursor Council Transcript",
        "",
        f"- council: {config['name']}",
        f"- run_dir: {run_dir}",
        f"- rounds: {config['rounds']}",
        f"- stop_condition: {config['stop_condition']}",
        "",
    ]
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
    config: Dict[str, Any],
    final_turn: Dict[str, Any],
    actual_model: str,
    response: str,
) -> str:
    planned_model = seat_model(config, final_turn["seat"])
    lines = [
        "# Final Output",
        "",
        f"- council: {config['name']}",
        f"- name: {final_turn['name']}",
        f"- seat: {final_turn['seat']}",
        f"- role: {final_turn['role']}",
        f"- planned_model: {planned_model}",
        f"- model: {actual_model}",
        f"- model_override: {str(actual_model != planned_model).lower()}",
        "- transcript: transcript.md",
        "",
        response.strip(),
        "",
    ]
    return "\n".join(lines)


def turn_document(
    *,
    config: Dict[str, Any],
    turn: Dict[str, Any],
    order_index: int,
    actual_model: str,
    prompt_name: str,
    response: str,
) -> str:
    planned_model = seat_model(config, turn["seat"])
    lines = [
        f"## Turn {order_index}: {turn['seat']} / {turn['role']}",
        "",
        f"- round: {turn['round']}",
        f"- name: {turn['name']}",
        f"- seat: {turn['seat']}",
        f"- role: {turn['role']}",
        f"- planned_model: {planned_model}",
        f"- model: {actual_model}",
        f"- model_override: {str(actual_model != planned_model).lower()}",
        f"- prompt: {prompt_name or 'not-recorded'}",
        f"- recorded_at: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        "",
        "### Instruction",
        "",
        turn["instruction"].strip(),
        "",
        "### Response",
        "",
        response.strip(),
        "",
    ]
    return "\n".join(lines)


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


def seat_model(config: Dict[str, Any], seat_name: str) -> str:
    return config["seats"][seat_name]["model"]


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
