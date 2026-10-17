"""Manual validation of MarkupSafe issue #472.

Issue: https://github.com/pallets/markupsafe/issues/472
Fix PR: https://github.com/pallets/markupsafe/pull/477

Behavior:
- On MarkupSafe 3.0.1: crashes with SystemError: <built-in function _escape_inner> returned NULL without setting an exception
- On MarkupSafe 3.0.2: passes with "Passed: abc"

Architectural Note for ReproForge:
The crash occurs directly inside MarkupSafe's compiled C extension speedup (_speedups.c).
Because compiled C extensions do not emit Python-level stack frames (e.g. src/markupsafe/...),
Python's traceback only contains the caller frame. ReproForge's strict repository-frame
verifier rule correctly refuses this as an unverified crash unless pure-Python fallback
or C-level frame tracking is enabled.
"""

from markupsafe import _escape_inner


class NewString(str):
    def __str__(self):
        return self


if __name__ == "__main__":
    value = _escape_inner(NewString("abc"))
    assert value == "abc"
    print("Passed:", value)
