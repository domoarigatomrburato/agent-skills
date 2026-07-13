#!/usr/bin/env python3
"""End-to-end contract tests for reviewer_packet.py."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("reviewer_packet.py")


def run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class ReviewerPacketTest(unittest.TestCase):
    def create_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "--quiet")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test User")
        (repo / "tracked.txt").write_text("base\n")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "--quiet", "-m", "base")
        return repo

    def test_lists_nested_untracked_files_and_explicit_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.create_repo(Path(directory))
            reference = repo / "skills" / "santommaso" / "references" / "review.md"
            reference.parent.mkdir(parents=True)
            reference.write_text("review\n")

            result = run(
                "--base",
                "HEAD",
                "--scope",
                "skills/santommaso",
                cwd=repo,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("skills/santommaso/references/review.md", result.stdout)
            self.assertIn("Report correctness and evidence findings", result.stdout)

    def test_non_repository_packet_keeps_explicit_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run(cwd=Path(directory))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Report correctness and evidence findings", result.stdout)
            self.assertNotIn("retain the standard output contract", result.stdout)

    def test_rejects_git_option_as_base_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = self.create_repo(root)
            output = root / "injected"

            result = run(f"--base=--output={output}", cwd=repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid --base", result.stderr)
            self.assertFalse(output.exists())

    def test_git_failure_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self.create_repo(Path(directory))

            result = run("--base", "missing-revision", cwd=repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid --base", result.stderr)
            self.assertNotIn("Changed files:", result.stdout)

    def test_missing_git_exits_nonzero_instead_of_emitting_non_repo_packet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=Path(directory),
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": ""},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("git executable not found", result.stderr)
            self.assertNotIn("this directory is not inside a git repository", result.stdout)


if __name__ == "__main__":
    unittest.main()
