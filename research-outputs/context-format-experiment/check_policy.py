"""The "gate" encoding: deterministic policy checks, never shown to the model.

This file is the realisation of rules R1-R5 of the experiment's rule set. It costs
zero model context and cannot be misread: it is a program, not prose. R6 is delegated
to an external tool (ruff). R7 and R8 are judgment/process rules that no gate can check,
so they survive as one-line prose in the steering kernel.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BLANKET_NOQA = re.compile(r"#\s*noqa(?!\s*:\s*[A-Z]+[0-9]+)")
FORBIDDEN_TERM = re.compile(r"\bfeatures?\b", re.IGNORECASE)
CONVENTIONAL_COMMIT = re.compile(r"^(build|charter|chore|ci|docs|feat|fix|lint|perf|plan|refactor|revert|spec|style|test)(\([^)]+\))?: .+")
PROTECTED_BRANCHES = frozenset({"main", "master"})


def check_branch(branch: str) -> list[str]:
    """R1: refuse work on a protected branch."""
    if branch in PROTECTED_BRANCHES:
        return [f"R1: refusing to work on protected branch {branch!r}"]
    return []


def check_commit_subject(subject: str) -> list[str]:
    """R5: commit subject must follow Conventional Commits."""
    if not CONVENTIONAL_COMMIT.match(subject):
        return [f"R5: commit subject {subject!r} is not Conventional Commits"]
    return []


def check_file(path: Path) -> list[str]:
    """R2-R4: per-file checks over a text file."""
    problems: list[str] = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    term_hits = FORBIDDEN_TERM.findall(raw)
    if term_hits:
        problems.append(f"R2: {path}: {len(term_hits)} forbidden term(s); use 'Mission'")
    if BLANKET_NOQA.search(raw):
        problems.append(f"R3: {path}: blanket '# noqa' without a rule code")
    if not raw.endswith("\n") or raw.endswith("\n\n"):
        problems.append(f"R4: {path}: must end with exactly one trailing newline")
    for number, line in enumerate(raw.splitlines(), start=1):
        if line != line.rstrip():
            problems.append(f"R4: {path}:{number}: trailing whitespace")
    return problems


def check_target(target: Path, branch: str, subject: str) -> list[str]:
    """Run every gate rule against a directory tree."""
    problems = check_branch(branch)
    problems += check_commit_subject(subject)
    for path in sorted(target.rglob("*")):
        if path.is_file():
            problems += check_file(path)
    return problems


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: exit 1 and print refusals when policy is violated."""
    parser = argparse.ArgumentParser(description="Deterministic policy gate for the experiment rule set.")
    parser.add_argument("target", type=Path, help="Directory of files to check.")
    parser.add_argument("--branch", default="work/example", help="Branch name to check against R1.")
    parser.add_argument("--subject", default="docs(research): example", help="Commit subject to check against R5.")
    args = parser.parse_args(argv)
    problems = check_target(args.target, args.branch, args.subject)
    if problems:
        print("\n".join(problems))
        print(f"\npolicy gate: {len(problems)} violation(s) found; refusing.")
        return 1
    print("policy gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
