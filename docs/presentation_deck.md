# ReproForge Presentation Deck

> **Prompt for Gamma (gamma.app):**
> "Create a modern, sleek, high-tech presentation deck based on the following slide-by-slide content for an AI developer tooling project called ReproForge. Use dark mode aesthetics, clean developer-focused cards, minimal typography, and clear visual hierarchy."

---

## Slide 1: Title Slide
# ReproForge
### Autonomous AI Bug Reproduction & Zero-Trust Regression Verification
- **Tagline:** Gemma proposes candidate tests; deterministic container sandboxes decide the verdict.
- **Presenter:** Hackathon Team
- **Track Categories:** Google / Gemma Track & DigitalOcean Cloud Track
- **Repository:** https://github.com/Rigur-Calypso/reproforge

---

## Slide 2: The Problem
# The Open-Source Triage Crisis
### Software maintainers waste hundreds of hours manually recreating reported bugs.
- **The Manual Nightmare:** Users submit raw GitHub issues with 50-line stack traces. Maintainers must manually configure runtimes, match package versions, and write reproduction scripts.
- **The LLM Dilemma:** Pasting tracebacks into ChatGPT or raw LLMs fails because models **hallucinate and cheat**:
  - Wrapping buggy calls in `pytest.raises` to make broken tests falsely pass.
  - Injecting `mock` objects that bypass real code execution.
  - Declaring "it worked!" without ever executing code against the repository.

---

## Slide 3: The Solution
# Enter ReproForge
### Turning messy GitHub crash reports into verified, minimal pytest regression tests.
- **Zero-Trust AI:** We never believe an LLM's self-reported success.
- **Dual-Worktree Isolation:** Tests are executed across both the broken revision and the fixed revision.
- **Differential Proof:** A test is certified only if it triggers the exact reported traceback on the bug, and passes cleanly (exit code 0) on the fix.
- **Turnkey Output:** Hands maintainers a production-ready `candidate.py` test file ready to commit to their codebase.

---

## Slide 4: System Architecture
# The 5-Stage Zero-Trust Pipeline
```
[ GitHub Issue & PR ] ──► [ Gemma 4 Synthesis ] ──► [ AST Anti-Cheating ] ──► [ Docker Sandbox ] ──► [ Certified Evidence ]
```
1. **Intake & Worktrees:** Clones repo at `blob:none` and checks out `affected` vs `fixed` worktrees.
2. **AI Code Synthesis:** Gemma 4 analyzes the traceback excerpt and target source code ($\le 3,500$ chars).
3. **Static AST Analysis:** Inspects syntax tree to mathematically reject cheating before execution.
4. **Isolated Sandbox:** Runs test in disposable Docker containers (`--network none`, `--read-only`, dropped capabilities).
5. **Deterministic Verifier:** Matches exception type, error message pattern, and repository stack frames.

---

## Slide 5: The Anti-Cheating Engine
# Compiler-Level AST Validation
### Why string search fails and why compiler analysis is required.
- **No `pytest.raises`:** Rejects attempts to catch the crash to simulate false passes.
- **No Manual `raise`:** Rejects candidates where the model artificially triggers the exception.
- **No `mock` or `monkeypatch`:** Rejects test-time faking of internal library methods.
- **Function-Scoped Assertions:** Enforces real, active assertion nodes inside test functions.
- **Integrity Test Suite:** 20 comprehensive unit tests in `tests/test_verifier.py` validating all rejection rules.

---

## Slide 6: Security & Sandboxing
# Isolated Container Execution
### Executing untrusted AI code safely without compromising host machines.
- **Networkless Execution:** Containers run with `--network none` (zero internet access; cannot exfiltrate secrets).
- **Read-Only Root Filesystem:** Prevents malware installation, disk wiping, or backdoors.
- **Dropped Capabilities:** Drops all Linux root privileges (`--cap-drop ALL`, `--security-opt no-new-privileges`).
- **Resource Constraints:** Strictly bounded CPU (1 core), memory (512MB), and process count (pids limit 128).
- **Multi-Python Workers:** Dedicated images for Python 3.13 (`reproforge-worker:py313`), HTTPX (`reproforge-worker:httpx`), and legacy Python 3.8 (`reproforge-worker:py38`).

---

## Slide 7: Real-World Proofs
# Evaluation Benchmarks & Results
### Proven across real production bugs in the Python ecosystem.

| Case ID | Target Repository | Environment | Target Error Signature | Verification Status |
| :--- | :--- | :--- | :--- | :---: |
| **HTTPX #3771** | `encode/httpx` *(Active Unmerged PR)* | Python 3.13 (`reproforge-worker:httpx`) | `IndexError: string index out of range` | **Verified in Docker** (PR commit `55ead904`) |
| **Click #3449** | `pallets/click` (8.4.0 vs `4df304c`) | Python 3.13 (`reproforge-worker:py313`) | `ValueError: I/O operation on closed file` | **Verified in Docker** (Attempt 1 Model Test) |
| **Click #2865** | `pallets/click` (8.1.7 vs 8.3.3) | Python 3.13 (`reproforge-worker:py313`) | `io.UnsupportedOperation: fileno` | **Verified in Docker** (Attempt 1 Model Test) |
| **Jinja #1362** | `pallets/jinja` (2.11.3 vs `59de6fb`) | Python 3.8 + `MarkupSafe 1.1.1` | `TypeError: sequence item 0: expected str...` | **Verified in Docker** (Legacy Pinning) |

> **Boundary Guardrail Study:** MarkupSafe #472 proves that crashes in compiled C speedups lacking Python repository frames are safely rejected.

---

## Slide 8: The Live PR Benchmark
# Benchmarking an Active, Unmerged PR
### Proving zero data leakage on live open-source triage (`encode/httpx#3771`).
- **The Problem:** Historical benchmarks risk data contamination (models memorizing old, closed bugs).
- **The Experiment:** Evaluated against an **active, open Pull Request** on HTTPX where `unquote("")` crashes.
- **The Workflow:** ReproForge fetched `pull/3771/head:pr-3771` directly from GitHub.
- **The Result:** Gemma synthesized a clean 2-line test:
  ```python
  from httpx._utils import unquote
  def test_unquote_empty_string():
      assert unquote("") == ""
  ```
- **Differential Proof:** Crashed on `master` with `IndexError` $\rightarrow$ Passed on the unmerged PR branch with exit code 0!

---

## Slide 9: Technology Stack
# Gemma 4 & DigitalOcean Alignment
### How our sponsors power the intelligence and infrastructure layers.
- **Google / Gemma Track:**
  - Gemma 4 acts as the code synthesis engine, reading tracebacks and writing idiomatic `pytest` files.
  - Supports Google Gemini API and DigitalOcean GenAI Inference (`gemma-4-31b-it`).
- **DigitalOcean Cloud Track:**
  - Serverless GenAI Inference API adapter (`reproforge/gemini.py`).
  - Worker container sandboxing designed for **DigitalOcean Droplets**.
  - Includes [`deploy/cloud-init.yaml`](deploy/cloud-init.yaml) and [`deploy/setup_server.sh`](deploy/setup_server.sh) for 1-click automated cloud provisioning.
  - Lightweight HTTP API daemon (`reproforge/server.py`) for headless remote triage.

---

## Slide 10: Real-World Impact
# Who Uses ReproForge?
- **Open-Source Maintainers:** Drops verified regression tests directly into their repository's `tests/` folder.
- **CI/CD & GitHub Actions:** Automated bot comments verified reproduction tests on new issues with zero human effort.
- **Engineering Teams:** Central cloud server allows developers to trigger container reproductions over HTTP without local Docker.
- **Developers Everywhere:** Saves 2+ hours of manual setup per bug report.

---

## Slide 11: Summary & Conclusion
# ReproForge
### Autonomous, Evidence-Backed Bug Triage for Python
- **Deterministic:** "Gemma proposes; containers decide."
- **Protected:** AST compiler validation stops AI cheating.
- **Proven:** 4 real-world benchmarks differentially verified.
- **Cloud-Ready:** 1-click DigitalOcean Droplet bootstrap & HTTP API.

**GitHub Repository:** https://github.com/Rigur-Calypso/reproforge  
*Thank you! Questions?*
