"""Run one generated pytest file in Docker or an explicitly unsafe local mode."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


EVENT_PREFIX = "REPROFORGE_EVENT="


def run_candidate(
    repo: Path,
    candidate: Path,
    import_paths: list[str],
    backend: str = "docker",
    image: str = "reproforge-worker:py313",
    timeout: int = 45,
) -> dict[str, Any]:
    repo = repo.resolve()
    candidate = candidate.resolve()
    plugin = Path(__file__).parents[1] / "worker" / "pytest_plugin.py"
    if not repo.is_dir() or not candidate.is_file() or not plugin.is_file():
        raise FileNotFoundError("repository, candidate, or ReproForge pytest plugin is missing")

    if backend == "docker":
        command = _docker_command(repo, candidate, plugin, import_paths, image, timeout)
        env = None
        cwd = None
    elif backend == "host-unsafe":
        command = [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "-p", "pytest_plugin", str(candidate),
        ]
        path_entries = [str(plugin.parent), *(str((repo / item).resolve()) for item in import_paths)]
        path_entries.extend(filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep)))
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(path_entries)}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["REPROFORGE_REPO_ROOT"] = str(repo)
        env["REPROFORGE_CANDIDATE"] = str(candidate)
        cwd = str(repo)
    else:
        raise ValueError(f"unknown execution backend: {backend}")

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout + 10,
            check=False,
        )
        output = completed.stdout[-24000:]
        return _result(completed.returncode, output, False)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return _result(124, str(output)[-24000:], True)
    except FileNotFoundError as exc:
        if backend == "docker":
            raise RuntimeError("Docker is not installed or the Docker daemon is not running.") from exc
        raise


def _docker_command(
    repo: Path,
    candidate: Path,
    plugin: Path,
    import_paths: list[str],
    image: str,
    timeout: int,
) -> list[str]:
    paths = ["/opt/reproforge", *(f"/workspace/{item}" for item in import_paths)]
    env = [
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        f"PYTHONPATH={os.pathsep.join(paths)}",
        "REPROFORGE_REPO_ROOT=/workspace",
        "REPROFORGE_CANDIDATE=/candidate/test_reproduction.py",
    ]
    return [
        "docker", "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "128", "--memory", "512m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--mount", f"type=bind,src={repo},dst=/workspace,readonly",
        "--mount", f"type=bind,src={candidate},dst=/candidate/test_reproduction.py,readonly",
        "--mount", f"type=bind,src={plugin},dst=/opt/reproforge/pytest_plugin.py,readonly",
        "--workdir", "/workspace",
        *[item for value in env for item in ("--env", value)],
        image,
        "python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "-p", "pytest_timeout", "-p", "pytest_plugin", "/candidate/test_reproduction.py",
        "--timeout", str(timeout),
    ]


def _result(exit_code: int, output: str, timed_out: bool) -> dict[str, Any]:
    event = None
    for line in output.splitlines():
        if line.startswith(EVENT_PREFIX):
            try:
                event = json.loads(line[len(EVENT_PREFIX):])
            except json.JSONDecodeError:
                continue
    if event is not None:
        event["exit_code"] = exit_code
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "event": event,
        "output": output,
    }
