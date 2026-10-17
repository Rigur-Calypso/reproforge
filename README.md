# ReproForge

ReproForge takes a curated Python crash report and repository case, asks Gemma to propose a candidate `pytest` test, runs it on affected and fixed revisions, and checks whether the observed failure matches the report. Gemma proposes tests; deterministic code checks the evidence.

## Current status

ReproForge has a runnable CLI, Gemini (Gemma) and DigitalOcean Inference adapters, an AST anti-cheating guard, constrained Docker workers, a traceback verifier, a 20-test verifier integrity suite, and a curated suite of fail-to-pass evaluation cases across distinct target environments:

1. **Click #3449 & #2865:** Model-generated tests differentially verified in isolated Docker containers (`reproforge-worker:py313`).
2. **HTTPX #3771 (Active Open PR):** Real-time triage benchmark evaluated against an **active, unmerged GitHub Pull Request** ([`encode/httpx#3771`](https://github.com/encode/httpx/pull/3771)). Model-synthesized candidate differentially verified in isolated Docker containers (`reproforge-worker:httpx`), tracking the resolved PR commit (`55ead904eff7376ccbc7f23e93be19117c642441`).
3. **Jinja #1362:** Multi-Python environment benchmark pinned to Python 3.8 and `MarkupSafe==1.1.1` (`reproforge-worker:py38`). Differentially verified in isolated Docker containers, confirming that async list rendering fails on Jinja 2.11.3 and passes on PR #1363.
4. **MarkupSafe #472 (Boundary Study):** Compiled C-extension speedup crash study ([`check_markupsafe.py`](check_markupsafe.py)) demonstrating ReproForge's guardrail rejecting crashes that do not emit repository Python stack frames.

Issue ingestion is currently a reviewed JSON case manifest, not an automatic GitHub issue parser. The DigitalOcean Droplet deployment is not live yet.

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

Run a known issue using a checked-in test without calling a model:

```bash
reproforge run \
  --case evals/cases/click-3449.json \
  --candidate evals/reproductions/click_3449.py \
  --backend host-unsafe
```

### Running in Docker Container Isolation

ReproForge executes tests inside disposable, unprivileged Docker containers (`--network none`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, tmpfs `/tmp`).

#### 1. Build the Worker Images

Build the worker image required for your target case:

```bash
# 1. Base Python 3.13 worker (for Click #3449, Click #2865)
docker build -t reproforge-worker:py313 -f worker/Dockerfile worker

# 2. Dependency-aware Python 3.13 worker (for HTTPX #3771)
docker build -t reproforge-worker:httpx -f worker/Dockerfile.httpx worker

# 3. Pinned Python 3.8 worker with MarkupSafe==1.1.1 (for Jinja 2.11.x)
docker build -t reproforge-worker:py38 -f worker/Dockerfile.py38 worker
```

#### 2. Run Verified Cases in Docker

The CLI automatically inspects `worker_image` in the case manifest (or accepts `--worker-image` overrides):

```bash
# Click #3449 (uses reproforge-worker:py313)
reproforge run --case evals/cases/click-3449.json --candidate artifacts/pallets-click-3449/candidate.py --backend docker

# Click #2865 (uses reproforge-worker:py313)
reproforge run --case evals/cases/click-2865.json --candidate artifacts/pallets-click-2865/candidate.py --backend docker

# HTTPX #3771 (automatically selects reproforge-worker:httpx)
reproforge run --case evals/cases/httpx-3771.json --candidate artifacts/encode-httpx-3771/candidate.py --backend docker

# Jinja #1362 (automatically selects reproforge-worker:py38)
reproforge run --case evals/cases/jinja-1362.json --candidate evals/reproductions/jinja_1362.py --backend docker
```

Or run live model generation inside container isolation:

```bash
GEMINI_API_KEY=your_key_here reproforge run --case evals/cases/click-3449.json --backend docker
```

An alternate DigitalOcean Inference backend is available with `--model-backend digitalocean` and `DO_INFERENCE_API_KEY`. Host execution is available for trusted local evaluation using `--backend host-unsafe`; it is not a sandbox.

## Verification & Anti-Cheating Behavior

A candidate must be a regular success test asserting correct behavior. The validator statically inspects Python AST to reject common spoofing patterns:
- Tests using `pytest.raises` (rejects attempts to invert the test so it passes on the bug)
- Direct `raise <ExpectedException>` (rejects candidates that artificially trigger the crash)
- `monkeypatch` fixture or `unittest.mock` imports (rejects test-time mocking of internal behavior)
- Tests lacking assertions inside test functions

While static AST validation filters out obvious shortcuts and invalid structures, deterministic differential execution across the affected and fixed revisions remains the ground truth standard for verification.

A comprehensive unit test suite in `tests/test_verifier.py` (20 tests) verifies all of these rejection rules and matching criteria.

## Results

All evaluation cases have been executed and differentially verified in isolated Docker containers:

1. **Click #3449 (Differentially Verified in Docker):** Model-generated test (`test_echo_via_pager`). Failed on Click 8.4.0 (`41f410f`) with `ValueError: I/O operation on closed file.` in `src/click/testing.py:invoke` and passed on fix commit `4df304c658666f34a5ca4335ab0da15832f02f9e`.
   - Worker Image: `reproforge-worker:py313`
   - Artifacts: [`artifacts/pallets-click-3449/evidence.json`](artifacts/pallets-click-3449/evidence.json) and [`candidate.py`](artifacts/pallets-click-3449/candidate.py).

2. **Click #2865 (Differentially Verified in Docker):** Model-generated test (`test_clirunner_faulthandler`). Failed on Click 8.1.7 (`874ca2b`) with `io.UnsupportedOperation: fileno` in `src/click/core.py:invoke` and passed cleanly on Click 8.3.3 (`c06d2d0`).
   - Worker Image: `reproforge-worker:py313`
   - Artifacts: [`artifacts/pallets-click-2865/evidence.json`](artifacts/pallets-click-2865/evidence.json) and [`candidate.py`](artifacts/pallets-click-2865/candidate.py).

3. **HTTPX #3771 (Active Open PR - Differentially Verified in Docker):** Model-generated test (`test_unquote_empty_string`) evaluated against an **active, unmerged GitHub Pull Request** ([`encode/httpx#3771`](https://github.com/encode/httpx/pull/3771)). Failed on HTTPX `master` (`ae1b9f6`) with `IndexError: string index out of range` in `httpx/_utils.py:unquote` (line 92), and passed on open PR branch `pr-3771` (pinned resolved commit `55ead904eff7376ccbc7f23e93be19117c642441`).
   - Worker Image: `reproforge-worker:httpx`
   - Artifacts: [`artifacts/encode-httpx-3771/evidence.json`](artifacts/encode-httpx-3771/evidence.json) and [`candidate.py`](artifacts/encode-httpx-3771/candidate.py).
   - Significance: Benchmarks real-time triage against unmerged code before upstream release.

4. **Jinja #1362 (Differentially Verified in Docker):** Reproducer (`test_native_environment_render_async_list`). Failed on Jinja 2.11.3 (`cf21539`) with `TypeError: sequence item 0: expected str instance, list found` in `src/jinja2/asyncsupport.py:concat_async` and passed cleanly on fix commit `59de6fbde98de6719758b773a77f0559756756b5`.
   - Worker Image: `reproforge-worker:py38`
   - Artifacts: [`artifacts/pallets-jinja-1362/evidence.json`](artifacts/pallets-jinja-1362/evidence.json) and [`candidate.py`](artifacts/pallets-jinja-1362/candidate.py).
   - Significance: Demonstrates multi-Python version pinning for legacy dependency stacks.

## Curated Evaluation Cases

ReproForge benchmarks differential reproduction across distinct environments:

1. **Click #3449 ([`evals/cases/click-3449.json`](evals/cases/click-3449.json)):**
   - **Target:** Pallets Click (8.4.0 vs fix commit `4df304c`)
   - **Environment:** Python 3.13 (`reproforge-worker:py313`)
   - **Failure signature:** `ValueError: I/O operation on closed file.` in `src/click/testing.py:invoke`
   - **Status:** Synthesized by model on attempt 1, differentially verified in Docker (`artifacts/pallets-click-3449/`).

2. **Click #2865 ([`evals/cases/click-2865.json`](evals/cases/click-2865.json)):**
   - **Target:** Pallets Click (8.1.7 vs fix release `8.3.3`, PR #3244)
   - **Environment:** Python 3.13 (`reproforge-worker:py313`)
   - **Failure signature:** `io.UnsupportedOperation: fileno` in `src/click/core.py:invoke`
   - **Status:** Synthesized by model on attempt 1, differentially verified in Docker (`artifacts/pallets-click-2865/`).

3. **HTTPX #3771 ([`evals/cases/httpx-3771.json`](evals/cases/httpx-3771.json)):**
   - **Target:** Encode HTTPX (`master` vs **active unmerged PR #3771**)
   - **Environment:** Python 3.13 (`reproforge-worker:httpx`)
   - **Failure signature:** `IndexError: string index out of range` in `httpx/_utils.py:unquote`
   - **Status:** Synthesized by model on attempt 1, differentially verified in Docker (`artifacts/encode-httpx-3771/`).

4. **Jinja #1362 ([`evals/cases/jinja-1362.json`](evals/cases/jinja-1362.json)):**
   - **Target:** Pallets Jinja (2.11.3 vs fix PR #1363, commit `59de6fb`)
   - **Environment:** Python 3.8 (`worker/Dockerfile.py38`), pinned `MarkupSafe==1.1.1` (`reproforge-worker:py38`)
   - **Failure signature:** `TypeError: sequence item 0: expected str instance, list found` in `src/jinja2/asyncsupport.py:concat_async`
   - **Status:** Differentially verified in Docker (`artifacts/pallets-jinja-1362/`).
   - **Significance:** Demonstrates ReproForge's environment pinning requirements—older Jinja releases rely on APIs removed in modern Python/MarkupSafe.

5. **MarkupSafe #472 ([`check_markupsafe.py`](check_markupsafe.py) - Boundary Study):**
   - **Target:** Pallets MarkupSafe (3.0.1 vs 3.0.2)
   - **Significance:** Demonstrates the verifier's strict repository-frame guardrail. Because the crash occurs inside compiled C code (`_speedups.c`) without emitting a Python frame, ReproForge's verifier refuses to certify it, highlighting the boundary of pure-Python traceback analysis.

## Cloud Server Deployment (DigitalOcean)

ReproForge can be deployed as an autonomous reproduction server on any Ubuntu cloud VM or **DigitalOcean Droplet**.

### Automated Bootstrap via DigitalOcean User Data (cloud-init)
When creating a Droplet in the DigitalOcean control panel (Ubuntu 22.04 or 24.04 LTS), expand **Advanced Options** $\rightarrow$ **Add User Data**, and paste the contents of [`deploy/cloud-init.yaml`](deploy/cloud-init.yaml). 

The Droplet will automatically:
1. Install Docker Engine and Python 3.11+.
2. Clone ReproForge and build the three worker images (`reproforge-worker:py313`, `reproforge-worker:httpx`, `reproforge-worker:py38`).
3. Register and enable the `reproforge.service` systemd daemon.
4. Start the HTTP API server on port 8080.

### Manual Setup on an Existing Droplet or VM

On any fresh Ubuntu/Debian server, run:

```bash
git clone https://github.com/Rigur-Calypso/reproforge.git /opt/reproforge
sudo /opt/reproforge/deploy/setup_server.sh
```

### Running the Server Locally or Headlessly

You can also run the server directly using the CLI:

```bash
reproforge serve --host 0.0.0.0 --port 8080
```

### Remote HTTP API Endpoints

Once running, the server exposes endpoints for automated triage:

1. **Health Check:**
   ```bash
   curl http://<SERVER_IP>:8080/health
   ```
   *Response:* `{"status": "healthy", "service": "reproforge", "docker_available": true}`

2. **List Curated Cases:**
   ```bash
   curl http://<SERVER_IP>:8080/cases
   ```

3. **Trigger Remote Reproduction:**
   ```bash
   curl -X POST http://<SERVER_IP>:8080/run \
     -H "Content-Type: application/json" \
     -d '{"case_id": "encode-httpx-3771", "candidate": "artifacts/encode-httpx-3771/candidate.py", "backend": "docker"}'
   ```
   *Response:* The complete, structured `evidence.json` produced by the isolated Docker container.

4. **Retrieve Stored Evidence Report:**
   ```bash
   curl http://<SERVER_IP>:8080/evidence/encode-httpx-3771
   ```

## Project documents

- [Architecture and reproduction workflow](docs/design.md)
- [Server systemd service configuration](deploy/reproforge.service)
- [Server automated setup script](deploy/setup_server.sh)
- [DigitalOcean Droplet cloud-init bootstrap](deploy/cloud-init.yaml)
- [Click issue #3449 case manifest](evals/cases/click-3449.json)
- [Click issue #2865 case manifest](evals/cases/click-2865.json)
- [HTTPX PR #3771 case manifest](evals/cases/httpx-3771.json)
- [Jinja issue #1362 case manifest](evals/cases/jinja-1362.json)
- [MarkupSafe boundary validation script](check_markupsafe.py)

## License

ReproForge source is MIT licensed. Model, API, and dependency terms remain governed by their respective providers.
