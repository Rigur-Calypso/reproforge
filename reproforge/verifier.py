"""Deterministic checks for a candidate reproduction and differential run."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


class CandidateRejected(ValueError):
    """Raised when a proposed test can manufacture or invert the target failure."""


@dataclass(frozen=True)
class Verification:
    verified: bool
    reasons: tuple[str, ...]
    deepest_repo_frame: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "reasons": list(self.reasons),
            "deepest_repo_frame": self.deepest_repo_frame,
        }


def validate_test_source(source: str, expected_exception: str) -> None:
    """Accept a normal-success test, not a test that expects the bug to happen."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CandidateRejected(f"candidate is not valid Python: {exc}") from exc

    test_functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if not test_functions:
        raise CandidateRejected("candidate must define at least one pytest test function")

    has_test_with_assert = any(
        any(isinstance(sub, ast.Assert) for sub in ast.walk(fn))
        for fn in test_functions
    )
    if not has_test_with_assert:
        raise CandidateRejected("candidate must assert the expected successful behavior inside a test function")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_pytest_raises(node):
            raise CandidateRejected(
                "candidate may not use pytest.raises; the test must pass after the fix"
            )
        if isinstance(node, ast.Raise) and _raised_type(node) == expected_exception:
            raise CandidateRejected(
                f"candidate may not directly raise the reported {expected_exception}"
            )
        if isinstance(node, ast.arg) and node.arg == "monkeypatch":
            raise CandidateRejected("candidate may not use pytest monkeypatch")

    imports_mock = any(
        (isinstance(node, ast.Import) and any(alias.name == "unittest.mock" for alias in node.names))
        or (isinstance(node, ast.ImportFrom) and node.module == "unittest.mock")
        for node in ast.walk(tree)
    )
    if imports_mock:
        raise CandidateRejected("candidate may not patch or mock the target package")


def _is_pytest_raises(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "raises" and isinstance(func.value, ast.Name) and func.value.id == "pytest"
    return isinstance(func, ast.Name) and func.id == "raises"


def _raised_type(node: ast.Raise) -> str | None:
    exc = node.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    if isinstance(exc, ast.Name):
        return exc.id
    if isinstance(exc, ast.Attribute):
        return exc.attr
    return None


def verify_failure(
    event: dict[str, Any] | None,
    oracle: dict[str, Any],
    repo_roots: tuple[str, ...],
    candidate_paths: tuple[str, ...] = ("candidate/test_reproduction.py",),
) -> Verification:
    """Verify the issue's exception and every report-provided message/function clue."""
    reasons: list[str] = []
    if event is None:
        return Verification(False, ("runner produced no exception event",), None)

    expected_exception = oracle.get("expected_exception")
    if not expected_exception:
        reasons.append("issue does not specify an expected exception type")
    elif event.get("exception_type") != expected_exception:
        reasons.append(
            f"exception type mismatch: expected {expected_exception}, got {event.get('exception_type')}"
        )

    frames = event.get("frames") or []
    repo_frames = [
        frame for frame in frames
        if _is_under_any(_normal_path(frame.get("path", "")), repo_roots)
        and not _is_under_any(_normal_path(frame.get("path", "")), candidate_paths)
    ]
    deepest = repo_frames[-1] if repo_frames else None
    if deepest is None:
        reasons.append("exception did not pass through a frame owned by the target repository")

    reported_functions = set(oracle.get("reported_functions") or [])
    if reported_functions:
        if deepest is None or deepest.get("function") not in reported_functions:
            got = deepest.get("function") if deepest else None
            reasons.append(
                f"deepest repository frame mismatch: expected one of {sorted(reported_functions)}, got {got}"
            )

    message_pattern = oracle.get("message_pattern")
    if message_pattern:
        actual = str(event.get("exception_message", ""))
        try:
            matches = re.search(message_pattern, actual, flags=re.IGNORECASE) is not None
        except re.error as exc:
            return Verification(False, (f"invalid issue message pattern: {exc}",), deepest)
        if not matches:
            reasons.append("exception message did not match the issue's reported message")

    if not reported_functions and not message_pattern:
        reasons.append("issue has no additional message or function evidence to verify")

    return Verification(not reasons, tuple(reasons), deepest)


def verify_differential(
    affected_event: dict[str, Any] | None,
    fixed_exit_code: int,
    oracle: dict[str, Any],
    repo_roots: tuple[str, ...],
    candidate_paths: tuple[str, ...] = ("candidate/test_reproduction.py",),
) -> Verification:
    """Require a correctly oriented fail-to-pass result across the two commits."""
    failure = verify_failure(affected_event, oracle, repo_roots, candidate_paths)
    reasons = list(failure.reasons)
    affected_exit_code = affected_event.get("exit_code") if affected_event else None
    if affected_exit_code is None:
        reasons.append("affected run has no process exit code")
    elif affected_exit_code == 0:
        reasons.append("candidate passed on the affected revision; expected it to fail there")
    if fixed_exit_code != 0:
        reasons.append(f"candidate did not pass on the fix revision (exit code {fixed_exit_code})")
    if reasons:
        return Verification(False, tuple(reasons), failure.deepest_repo_frame)
    return Verification(
        True,
        ("reported failure matched on affected revision and test passed on fix revision",),
        failure.deepest_repo_frame,
    )


def _normal_path(value: str) -> str:
    path = str(PurePosixPath(value.replace("\\", "/")))
    return path[2:] if path.startswith("./") else path


def _is_under_any(path: str, roots: tuple[str, ...]) -> bool:
    for root in roots:
        normalized = _normal_path(root).rstrip("/")
        if path == normalized or path.startswith(normalized + "/"):
            return True
    return False
