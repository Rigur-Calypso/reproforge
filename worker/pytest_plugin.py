"""Small trusted pytest plugin that emits the real exception and traceback frames."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed or call.excinfo is None:
        return

    root = Path(os.environ["REPROFORGE_REPO_ROOT"]).resolve()
    candidate = Path(os.environ["REPROFORGE_CANDIDATE"]).resolve()
    frames = []
    tb = call.excinfo.tb
    while tb is not None:
        frame_path = Path(tb.tb_frame.f_code.co_filename).resolve()
        try:
            relative = frame_path.relative_to(root).as_posix()
        except ValueError:
            if frame_path == candidate:
                relative = "candidate/test_reproduction.py"
            else:
                relative = frame_path.as_posix()
        frames.append({
            "path": relative,
            "function": tb.tb_frame.f_code.co_name,
            "line": tb.tb_lineno,
        })
        tb = tb.tb_next

    event = {
        "exception_type": call.excinfo.type.__name__,
        "exception_message": str(call.excinfo.value),
        "frames": frames,
    }
    print("REPROFORGE_EVENT=" + json.dumps(event, sort_keys=True), flush=True)
