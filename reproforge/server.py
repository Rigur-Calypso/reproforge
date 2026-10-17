"""Lightweight HTTP server for remote cloud reproduction requests."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .cli import _run, _git
from .verifier import CandidateRejected, validate_test_source
from .runner import run_candidate

logger = logging.getLogger("reproforge.server")


class ReproForgeRequestHandler(BaseHTTPRequestHandler):
    repo_root = Path(__file__).resolve().parents[1]

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._send_json(HTTPStatus.OK, {
                "status": "healthy",
                "service": "reproforge",
                "version": "0.1.0",
                "docker_available": self._check_docker(),
            })
        elif self.path == "/cases":
            cases_dir = self.repo_root / "evals" / "cases"
            cases = []
            if cases_dir.is_dir():
                for file in sorted(cases_dir.glob("*.json")):
                    try:
                        manifest = json.loads(file.read_text(encoding="utf-8"))
                        cases.append({
                            "case_id": manifest.get("case_id"),
                            "summary": manifest.get("summary"),
                            "target_ref": manifest.get("affected_ref"),
                            "worker_image": manifest.get("worker_image", "reproforge-worker:py313"),
                            "file": file.name,
                        })
                    except Exception:
                        continue
            self._send_json(HTTPStatus.OK, {"cases": cases})
        elif self.path.startswith("/evidence/"):
            case_id = self.path.split("/evidence/", 1)[1].strip("/")
            evidence_file = self.repo_root / "artifacts" / case_id / "evidence.json"
            if evidence_file.is_file():
                try:
                    data = json.loads(evidence_file.read_text(encoding="utf-8"))
                    self._send_json(HTTPStatus.OK, data)
                except Exception as exc:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"no evidence found for {case_id}"})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "endpoint not found"})

    def do_POST(self) -> None:
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "empty request body"})
                return

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON: {exc}"})
                return

            case_id = payload.get("case_id")
            case_path: Path | None = None
            if case_id:
                candidate_case = self.repo_root / "evals" / "cases" / f"{case_id}.json"
                if not candidate_case.is_file():
                    # Check if case_id matches inside any manifest
                    for file in (self.repo_root / "evals" / "cases").glob("*.json"):
                        try:
                            c = json.loads(file.read_text(encoding="utf-8"))
                            if c.get("case_id") == case_id:
                                candidate_case = file
                                break
                        except Exception:
                            continue
                if candidate_case.is_file():
                    case_path = candidate_case

            if not case_path:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "case_id not found in evals/cases/"})
                return

            backend = payload.get("backend", "docker")
            model_backend = payload.get("model_backend", "gemini")
            candidate_file = payload.get("candidate")
            candidate_path: Path | None = None
            if candidate_file:
                p = Path(candidate_file)
                if not p.is_absolute():
                    p = self.repo_root / p
                if p.is_file():
                    candidate_path = p

            cmd = [
                sys.executable, "-m", "reproforge.cli", "run",
                "--case", str(case_path),
                "--backend", backend,
                "--model-backend", model_backend,
            ]
            if candidate_path:
                cmd.extend(["--candidate", str(candidate_path)])
            if payload.get("worker_image"):
                cmd.extend(["--worker-image", payload["worker_image"]])

            env = dict(os.environ)
            if "gemini_api_key" in payload:
                env["GEMINI_API_KEY"] = payload["gemini_api_key"]
            if "do_inference_api_key" in payload:
                env["DO_INFERENCE_API_KEY"] = payload["do_inference_api_key"]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.repo_root),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                    check=False,
                )
                evidence = None
                for line in proc.stdout.splitlines():
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict) and "status" in parsed:
                            evidence = parsed
                    except Exception:
                        continue

                if proc.returncode == 0 or evidence:
                    self._send_json(HTTPStatus.OK, evidence or {"raw_output": proc.stdout[-5000:]})
                else:
                    self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {
                        "error": "reproduction run failed",
                        "stderr": proc.stderr[-2000:],
                        "stdout": proc.stdout[-2000:],
                        "exit_code": proc.returncode,
                    })
            except subprocess.TimeoutExpired:
                self._send_json(HTTPStatus.GATEWAY_TIMEOUT, {"error": "reproduction run timed out"})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "endpoint not found"})

    def _send_json(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def _check_docker(self) -> bool:
        try:
            res = subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return res.returncode == 0
        except Exception:
            return False


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    server_address = (host, port)
    httpd = HTTPServer(server_address, ReproForgeRequestHandler)
    print(f"ReproForge cloud server listening on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
