"""Command line entry point for a small fail-to-pass reproduction run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .gemini import generate_test
from .runner import run_candidate
from .verifier import CandidateRejected, verify_differential, verify_failure, validate_test_source


def main() -> None:
    parser = argparse.ArgumentParser(prog="reproforge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="generate or load a test and compare affected/fix revisions")
    run.add_argument("--case", type=Path, required=True, help="JSON issue/evaluation manifest")
    run.add_argument("--repo-url", help="Git repository URL; defaults to the case manifest")
    run.add_argument("--candidate", type=Path, help="use a reviewed test file instead of calling a model")
    run.add_argument("--model-backend", choices=("gemini", "digitalocean"), default="gemini")
    run.add_argument("--backend", choices=("docker", "host-unsafe"), default="docker")
    run.add_argument("--worker-image", default="reproforge-worker:py313")
    run.add_argument("--max-attempts", type=int, default=3)
    run.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    run.set_defaults(handler=_run)

    args = parser.parse_args()
    try:
        args.handler(args)
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"reproforge: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _run(args: argparse.Namespace) -> None:
    case_path = args.case.resolve()
    case = json.loads(case_path.read_text(encoding="utf-8"))
    repo_url = args.repo_url or case["repository_url"]
    affected_ref = case["affected_ref"]
    fixed_ref = case["fixed_ref"]
    out_dir = args.output_dir.resolve() / case["case_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.candidate:
        source = args.candidate.resolve().read_text(encoding="utf-8")
        validate_test_source(source, case["expected_exception"])
        candidate_is_model_generated = False
    else:
        source = None
        candidate_is_model_generated = True

    history: list[dict[str, Any]] = []
    feedback: str | None = None
    final_result: dict[str, Any] | None = None

    with tempfile.TemporaryDirectory(prefix="reproforge-") as temporary:
        temp_root = Path(temporary)
        clone = temp_root / "source"
        _git(["clone", "--quiet", "--filter=blob:none", "--no-checkout", repo_url, str(clone)])
        affected = temp_root / "affected"
        fixed = temp_root / "fixed"
        _git(["-C", str(clone), "worktree", "add", "--quiet", "--detach", str(affected), affected_ref])
        _git(["-C", str(clone), "worktree", "add", "--quiet", "--detach", str(fixed), fixed_ref])

        attempt_limit = 1 if source is not None else max(1, min(args.max_attempts, 3))
        for attempt_no in range(1, attempt_limit + 1):
            if candidate_is_model_generated:
                try:
                    source = generate_test(case, affected, args.model_backend, feedback)
                except CandidateRejected as exc:
                    history.append({"attempt": attempt_no, "candidate_rejected": str(exc)})
                    feedback = f"The candidate was rejected before execution: {exc}. Return a normal-success pytest test only."
                    continue

            candidate_path = out_dir / "candidate.py"
            candidate_path.write_text(source or "", encoding="utf-8")
            start = time.monotonic()
            affected_result = run_candidate(
                affected, candidate_path, case.get("import_paths", []),
                backend=args.backend, image=args.worker_image,
            )
            affected_result["duration_seconds"] = round(time.monotonic() - start, 3)
            failure_check = verify_failure(
                affected_result.get("event"),
                case,
                tuple(case["repo_roots"]),
            )

            fixed_result = run_candidate(
                fixed, candidate_path, case.get("import_paths", []),
                backend=args.backend, image=args.worker_image,
            )
            differential = verify_differential(
                affected_result.get("event"),
                fixed_result["exit_code"],
                case,
                tuple(case["repo_roots"]),
            )
            record = {
                "attempt": attempt_no,
                "affected": _public_worker_result(affected_result),
                "affected_signature_check": failure_check.as_dict(),
                "fixed": _public_worker_result(fixed_result),
                "differential_check": differential.as_dict(),
            }
            history.append(record)
            final_result = record
            if differential.verified:
                break
            if not candidate_is_model_generated:
                break
            feedback = _feedback(record)

    if final_result is None or not final_result["differential_check"]["verified"]:
        status = "not_reproduced"
    else:
        status = "differentially_verified"

    evidence = {
        "case_id": case["case_id"],
        "issue_url": case["issue_url"],
        "repository_url": case.get("repository_url", repo_url),
        "repository_source_override": repo_url if repo_url != case.get("repository_url") else None,
        "affected_ref": affected_ref,
        "fixed_ref": fixed_ref,
        "model_backend": args.model_backend if candidate_is_model_generated else "manual-candidate",
        "execution_backend": args.backend,
        "model_generated_candidate": candidate_is_model_generated,
        "status": status,
        "attempts": history,
        "candidate_path": "candidate.py",
    }
    (out_dir / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if status != "differentially_verified":
        raise SystemExit(1)


def _git(args: list[str]) -> None:
    result = subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git command failed ({result.returncode}): {detail}")


def _public_worker_result(result: dict[str, Any]) -> dict[str, Any]:
    output = result.get("output", "")
    for sensitive in (str(Path.home()), str(Path.cwd())):
        output = output.replace(sensitive, "<workspace>")
    return {key: value for key, value in result.items() if key != "output"} | {
        "output_excerpt": output[-4000:],
        "output_truncated": len(output) > 4000,
    }


def _feedback(record: dict[str, Any]) -> str:
    return json.dumps({
        "affected_output": record["affected"].get("output_excerpt", "")[-3500:],
        "affected_signature_check": record["affected_signature_check"],
        "fixed_exit_code": record["fixed"].get("exit_code"),
        "fixed_output": record["fixed"].get("output_excerpt", "")[-1500:],
        "differential_check": record["differential_check"],
    }, indent=2)


if __name__ == "__main__":
    main()
