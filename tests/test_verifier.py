"""Unit tests verifying ReproForge's anti-cheating safeguards and differential logic."""

import pytest
from reproforge.verifier import (
    CandidateRejected,
    validate_test_source,
    verify_failure,
    verify_differential,
)


# ==============================================================================
# AST Anti-Cheating & Candidate Validation Tests
# ==============================================================================

def test_valid_candidate_accepted():
    source = """
def test_something():
    result = 1 + 1
    assert result == 2
"""
    # Should not raise
    validate_test_source(source, expected_exception="ValueError")


def test_reject_syntax_error():
    source = "def test_broken(:"
    with pytest.raises(CandidateRejected, match="not valid Python"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_no_test_function():
    source = """
def helper():
    assert 1 == 1
"""
    with pytest.raises(CandidateRejected, match="define at least one pytest test function"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_missing_assert():
    source = """
def test_something():
    x = 10
"""
    with pytest.raises(CandidateRejected, match="assert the expected successful behavior inside a test function"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_assert_only_at_module_level():
    source = """
assert True

def test_empty():
    pass
"""
    with pytest.raises(CandidateRejected, match="assert the expected successful behavior inside a test function"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_assert_only_in_helper_function():
    source = """
def helper():
    assert 1 == 1

def test_empty():
    pass
"""
    with pytest.raises(CandidateRejected, match="assert the expected successful behavior inside a test function"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_pytest_raises():
    source = """
import pytest

def test_cheating():
    with pytest.raises(Exception):
        pass
    assert True
"""
    with pytest.raises(CandidateRejected, match="may not use pytest.raises"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_direct_raise_of_expected_exception():
    source = """
def test_fake_bug():
    if True:
        raise ValueError("faking the crash")
    assert True
"""
    with pytest.raises(CandidateRejected, match="may not directly raise the reported ValueError"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_monkeypatch():
    source = """
def test_with_patch(monkeypatch):
    assert True
"""
    with pytest.raises(CandidateRejected, match="may not use pytest monkeypatch"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_unittest_mock_import():
    source = """
import unittest.mock

def test_with_mock():
    assert True
"""
    with pytest.raises(CandidateRejected, match="may not patch or mock the target package"):
        validate_test_source(source, expected_exception="ValueError")


def test_reject_from_unittest_mock_import():
    source = """
from unittest.mock import patch

def test_with_mock():
    assert True
"""
    with pytest.raises(CandidateRejected, match="may not patch or mock the target package"):
        validate_test_source(source, expected_exception="ValueError")


# ==============================================================================
# Failure Signature Verification Tests
# ==============================================================================

ORACLE = {
    "expected_exception": "ValueError",
    "message_pattern": "I/O operation on closed file",
    "reported_functions": ["invoke"],
}

REPO_ROOTS = ("src/click",)


def test_verify_failure_no_event():
    v = verify_failure(None, ORACLE, REPO_ROOTS)
    assert not v.verified
    assert "runner produced no exception event" in v.reasons


def test_verify_failure_wrong_exception():
    event = {
        "exception_type": "TypeError",
        "exception_message": "I/O operation on closed file",
        "frames": [{"path": "src/click/testing.py", "function": "invoke"}],
    }
    v = verify_failure(event, ORACLE, REPO_ROOTS)
    assert not v.verified
    assert any("exception type mismatch" in r for r in v.reasons)


def test_verify_failure_wrong_message():
    event = {
        "exception_type": "ValueError",
        "exception_message": "Unexpected None value",
        "frames": [{"path": "src/click/testing.py", "function": "invoke"}],
    }
    v = verify_failure(event, ORACLE, REPO_ROOTS)
    assert not v.verified
    assert any("exception message did not match" in r for r in v.reasons)


def test_verify_failure_missing_repo_frame():
    # Only candidate frame or external library frame, no frame in src/click
    event = {
        "exception_type": "ValueError",
        "exception_message": "I/O operation on closed file",
        "frames": [{"path": "candidate/test_reproduction.py", "function": "test_cli"}],
    }
    v = verify_failure(event, ORACLE, REPO_ROOTS)
    assert not v.verified
    assert any("did not pass through a frame owned by the target repository" in r for r in v.reasons)


def test_verify_failure_wrong_function():
    event = {
        "exception_type": "ValueError",
        "exception_message": "I/O operation on closed file",
        "frames": [{"path": "src/click/core.py", "function": "main"}],
    }
    v = verify_failure(event, ORACLE, REPO_ROOTS)
    assert not v.verified
    assert any("deepest repository frame mismatch" in r for r in v.reasons)


def test_verify_failure_exact_match():
    event = {
        "exception_type": "ValueError",
        "exception_message": "ValueError: I/O operation on closed file.",
        "frames": [
            {"path": "candidate/test_reproduction.py", "function": "test_cli"},
            {"path": "src/click/core.py", "function": "main"},
            {"path": "src/click/testing.py", "function": "invoke"},
        ],
    }
    v = verify_failure(event, ORACLE, REPO_ROOTS)
    assert v.verified
    assert v.deepest_repo_frame == {"path": "src/click/testing.py", "function": "invoke"}


# ==============================================================================
# Differential Verification Tests
# ==============================================================================

def test_verify_differential_pass():
    affected_event = {
        "exit_code": 1,
        "exception_type": "ValueError",
        "exception_message": "I/O operation on closed file",
        "frames": [{"path": "src/click/testing.py", "function": "invoke"}],
    }
    v = verify_differential(
        affected_event=affected_event,
        fixed_exit_code=0,
        oracle=ORACLE,
        repo_roots=REPO_ROOTS,
    )
    assert v.verified


def test_verify_differential_fixed_fails():
    affected_event = {
        "exit_code": 1,
        "exception_type": "ValueError",
        "exception_message": "I/O operation on closed file",
        "frames": [{"path": "src/click/testing.py", "function": "invoke"}],
    }
    v = verify_differential(
        affected_event=affected_event,
        fixed_exit_code=1,  # Fixed revision also failed!
        oracle=ORACLE,
        repo_roots=REPO_ROOTS,
    )
    assert not v.verified
    assert any("did not pass on the fix revision" in r for r in v.reasons)


def test_verify_differential_affected_passed():
    affected_event = {
        "exit_code": 0,  # Buggy revision unexpectedly passed
        "exception_type": "ValueError",
        "exception_message": "I/O operation on closed file",
        "frames": [{"path": "src/click/testing.py", "function": "invoke"}],
    }
    v = verify_differential(
        affected_event=affected_event,
        fixed_exit_code=0,
        oracle=ORACLE,
        repo_roots=REPO_ROOTS,
    )
    assert not v.verified
    assert any("passed on the affected revision; expected it to fail" in r for r in v.reasons)
