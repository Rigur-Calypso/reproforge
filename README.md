# ReproForge

ReproForge takes a curated Python crash report and repository case, asks Gemma to propose a candidate `pytest` test, runs it on affected and fixed revisions, and checks whether the observed failure matches the report. Gemma proposes tests; deterministic code checks the evidence.

## Current status

The prototype has a runnable CLI, Gemini and DigitalOcean Inference adapters, an AST anti-cheating guard, a constrained Docker worker, a traceback verifier, a 20-test verifier integrity suite, and a curated fail-to-pass case for [Click issue #3449](https://github.com/pallets/click/issues/3449). 

The pipeline has been run end-to-end with **live model generation**: the model was prompted with the issue manifest and repository context, synthesized a clean candidate `pytest` test on attempt 1, and ReproForge's deterministic verifier confirmed the differential failure-to-pass reproduction against Click 8.4.0 and the fix commit.

Issue ingestion is currently a reviewed JSON case manifest, not an automatic GitHub issue parser. The DigitalOcean Droplet deployment is not live yet.

The Click issue reports that `CliRunner.invoke` raises `ValueError: I/O operation on closed file` after `echo_via_pager` under Click 8.4, and links the merged fix in [PR #3533](https://github.com/pallets/click/pull/3533). ReproForge checks the model-generated ordinary-success test against affected Click 8.4.0 and the fix commit. Dependencies are unchanged between these revisions and are supplied by one pinned worker image.

## Quick start

Requires Python 3.11+. Install dependencies and run the verifier test suite:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest tests/ -v
```

### Running Model Generation (Gemini / Gemma)

To generate and verify a reproduction test using the Gemini API:

```bash
GEMINI_API_KEY=your_key_here reproforge run \
  --case evals/cases/click-3449.json \
  --backend host-unsafe
```

### Running with a Pre-written Candidate

Run the known issue using a checked-in test without calling a model:

```bash
reproforge run \
  --case evals/cases/click-3449.json \
  --candidate evals/reproductions/click_3449.py \
  --backend host-unsafe
```

### Running in Docker Container Isolation

Build the isolated worker image:

```bash
docker build -t reproforge-worker:py313 -f worker/Dockerfile .
```

Run the baseline test in disposable containers (no API key needed):

```bash
reproforge run \
  --case evals/cases/click-3449.json \
  --candidate evals/reproductions/click_3449.py
```

Or run live model generation inside container isolation:

```bash
GEMINI_API_KEY=your_key_here reproforge run --case evals/cases/click-3449.json
```

The command fetches the public Click repository, creates detached checkouts for the affected and fixed commits, executes the candidate in separate disposable containers, verifies the failure signature, and writes `artifacts/pallets-click-3449/evidence.json` and `candidate.py`.

An alternate DigitalOcean Inference backend is available with `--model-backend digitalocean` and `DO_INFERENCE_API_KEY`. Host execution is available for trusted local evaluation using `--backend host-unsafe`; it is not a sandbox. The default Docker worker has networking disabled and mounts source and candidate read-only.

## Verification & Anti-Cheating Behavior

A candidate must be a regular success test asserting correct behavior. The validator statically inspects Python AST to reject common spoofing patterns:
- Tests using `pytest.raises` (rejects attempts to invert the test so it passes on the bug)
- Direct `raise <ExpectedException>` (rejects candidates that artificially trigger the crash)
- `monkeypatch` fixture or `unittest.mock` imports (rejects test-time mocking of internal behavior)
- Tests lacking assertions inside test functions

While static AST validation filters out obvious shortcuts and invalid structures, deterministic differential execution across the affected and fixed revisions remains the ground truth standard for verification.

A comprehensive unit test suite in `tests/test_verifier.py` (20 tests) verifies all of these rejection rules and matching criteria.

## Results

1. **Click #3449 (Differentially Verified):** Model generated test (`test_echo_via_pager`). Failed on Click 8.4.0 with `ValueError: I/O operation on closed file.` in `src/click/testing.py:invoke` and passed on fix commit `4df304c658666f34a5ca4335ab0da15832f02f9e`.
   - Artifacts: [`artifacts/pallets-click-3449/evidence.json`](artifacts/pallets-click-3449/evidence.json) and [`candidate.py`](artifacts/pallets-click-3449/candidate.py).

2. **Click #2865 (Differentially Verified):** Model generated test (`test_clirunner_faulthandler`). Failed on Click 8.1.7 with `io.UnsupportedOperation: fileno` in `src/click/core.py:invoke` and passed cleanly on Click 8.3.3.
   - Artifacts: [`artifacts/pallets-click-2865/evidence.json`](artifacts/pallets-click-2865/evidence.json) and [`candidate.py`](artifacts/pallets-click-2865/candidate.py).

3. **HTTPX #3771 (Active Open PR - Differentially Verified):** Model generated test (`test_unquote_empty_string`) evaluated against an **active, unmerged GitHub Pull Request** ([`encode/httpx#3771`](https://github.com/encode/httpx/pull/3771)). Failed on HTTPX `master` with `IndexError: string index out of range` in `httpx/_utils.py:unquote` (line 92), and passed on the open PR branch `pr-3771`.
   - Artifacts: [`artifacts/encode-httpx-3771/evidence.json`](artifacts/encode-httpx-3771/evidence.json) and [`candidate.py`](artifacts/encode-httpx-3771/candidate.py).
   - Significance: Demonstrates that ReproForge evaluates real-time, unmerged pull requests in active open-source triage before they are merged.

4. **Execution Environment Note:** These runs used `host-unsafe` because Docker Desktop was unavailable on the evaluation workstation. The Docker container isolation configuration (`--network none`, `--read-only`, dropped capabilities) is provided in `worker/` and `runner.py`.

## Curated Evaluation Cases

ReproForge benchmarks differential reproduction across distinct environments:

1. **Click #3449 ([`evals/cases/click-3449.json`](evals/cases/click-3449.json)):**
   - **Target:** Pallets Click (8.4.0 vs fix commit `4df304c`)
   - **Environment:** Python 3.13 (`reproforge-worker:py313`)
   - **Failure signature:** `ValueError: I/O operation on closed file.` in `src/click/testing.py:invoke`
   - **Status:** Synthesized by model on attempt 1 and differentially verified (`artifacts/pallets-click-3449/`).

2. **Click #2865 ([`evals/cases/click-2865.json`](evals/cases/click-2865.json)):**
   - **Target:** Pallets Click (8.1.7 vs fix release `8.3.3`, PR #3244)
   - **Environment:** Python 3.13 (`reproforge-worker:py313`)
   - **Failure signature:** `io.UnsupportedOperation: fileno` in `src/click/core.py:invoke`
   - **Status:** Synthesized by model on attempt 1 and differentially verified (`artifacts/pallets-click-2865/`).

3. **HTTPX #3771 ([`evals/cases/httpx-3771.json`](evals/cases/httpx-3771.json)):**
   - **Target:** Encode HTTPX (`master` vs **active unmerged PR #3771**)
   - **Environment:** Python 3.13 (`reproforge-worker:py313`)
   - **Failure signature:** `IndexError: string index out of range` in `httpx/_utils.py:unquote`
   - **Status:** Synthesized by model on attempt 1 and differentially verified (`artifacts/encode-httpx-3771/`).

4. **Jinja #1362 ([`evals/cases/jinja-1362.json`](evals/cases/jinja-1362.json)):**
   - **Target:** Pallets Jinja (2.11.3 vs fix PR #1363, commit `59de6fb`)
   - **Environment:** Python 3.8 (`worker/Dockerfile.py38`), pinned `MarkupSafe==1.1.1`
   - **Failure signature:** `TypeError: sequence item 0: expected str instance, list found` in `jinja2/asyncsupport.py:concat_async`
   - **Reproducer:** [`evals/reproductions/jinja_1362.py`](evals/reproductions/jinja_1362.py)
   - **Significance:** Demonstrates ReproForge's environment pinning requirements—older Jinja releases rely on APIs removed in modern Python/MarkupSafe.

5. **MarkupSafe #472 ([`check_markupsafe.py`](check_markupsafe.py) - Boundary Study):**
   - **Target:** Pallets MarkupSafe (3.0.1 vs 3.0.2)
   - **Significance:** Demonstrates the verifier's strict repository-frame guardrail. Because the crash occurs inside compiled C code (`_speedups.c`) without emitting a Python frame, ReproForge's verifier refuses to certify it, highlighting the boundary of pure-Python traceback analysis.

## DigitalOcean

The worker is designed to run in a disposable container on a DigitalOcean Droplet. The deployment is not complete yet. Model calls run from the orchestrator, using either Gemini or the optional DigitalOcean Inference endpoint.

## Project documents

- [Architecture and reproduction workflow](docs/design.md)
- [Click issue #3449 case manifest](evals/cases/click-3449.json)
- [Click issue #2865 case manifest](evals/cases/click-2865.json)
- [HTTPX PR #3771 case manifest](evals/cases/httpx-3771.json)
- [Jinja issue #1362 case manifest](evals/cases/jinja-1362.json)
- [MarkupSafe boundary validation script](check_markupsafe.py)

## License

ReproForge source is MIT licensed. Model, API, and dependency terms remain governed by their respective providers.
