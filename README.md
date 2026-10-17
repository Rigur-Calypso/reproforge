# ReproForge

ReproForge takes a curated Python crash report and repository case, asks Gemma to propose a candidate `pytest` test, runs it on affected and fixed revisions, and checks whether the observed failure matches the report. Gemma proposes tests; deterministic code checks the evidence.

## Current status

The prototype now has a runnable CLI, Gemini and DigitalOcean Inference adapters, a constrained Docker worker, a traceback verifier, and a curated fail-to-pass case for [Click issue #3449](https://github.com/pallets/click/issues/3449). The issue's own reproducer is checked in as a baseline. Issue ingestion is currently a reviewed JSON case manifest, not an automatic GitHub issue parser. The model-backed path is implemented but needs an API key to run. The DigitalOcean Droplet deployment is not live yet.

The Click issue reports that `CliRunner.invoke` raises `ValueError: I/O operation on closed file` after `echo_via_pager` under Click 8.4, and links the merged fix in [PR #3533](https://github.com/pallets/click/pull/3533). ReproForge checks the same ordinary-success test against affected Click 8.4.0 and the fix commit. Dependencies are unchanged between these revisions and are supplied by one pinned worker image.

## Quick start

Requires Python 3.11+ and Docker. Build the isolated worker image and install the CLI:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
docker build -t reproforge-worker:py313 -f worker/Dockerfile .
```

Run the known issue using its checked-in test (no model key needed):

```bash
reproforge run \
  --case evals/cases/click-3449.json \
  --candidate evals/reproductions/click_3449.py
```

The command fetches the public Click repository, creates detached checkouts for the affected and fixed commits, executes the same candidate in separate disposable containers, verifies the failure signature, and writes `artifacts/pallets-click-3449/evidence.json` and `candidate.py`.

To ask Gemma to generate a candidate instead, set `GEMINI_API_KEY` and omit `--candidate`:

```bash
GEMINI_API_KEY=... reproforge run --case evals/cases/click-3449.json
```

An alternate DigitalOcean Inference backend is available with `--model-backend digitalocean` and `DO_INFERENCE_API_KEY`. Host execution is available only for a trusted local evaluation using `--backend host-unsafe`; it is not a sandbox. The default Docker worker has networking disabled and mounts source and candidate read-only.

## Verification behavior

A candidate must be a regular success test with an assertion. The validator rejects `pytest.raises`, direct raises of the reported exception, and common test-time patching. For a differential pass, the runner must observe a failing test on the affected revision, with the reported exception, message, and reported function all matching when supplied. The deepest repo-owned traceback frame must be in the target package; dependency frames can be deeper and do not disqualify the report's own frame. The exact same test must pass on the fix revision.

Static checks are not a complete defense against adversarial Python code. This is a curated hackathon prototype, not a production hostile-code sandbox. Do not expose the worker as a public multi-tenant service.

## Results

Baseline result on Python 3.13.11 with pytest 8.4.2: the checked-in, issue-derived candidate fails on Click 8.4.0 with the reported `ValueError` in `click.testing.invoke` and passes on the linked fix commit. ReproForge's deterministic differential verifier accepts the fail-to-pass result. This first run used `host-unsafe` because Docker Desktop was unavailable in the workspace; rerun with the default Docker backend before presenting container isolation as demonstrated. This is one curated functional demo, not evidence of general reproduction accuracy.

## DigitalOcean

The worker is designed to run in a disposable container on a DigitalOcean Droplet. The deployment is not complete yet. Model calls run from the orchestrator, using either Gemini or the optional DigitalOcean Inference endpoint.

## Project documents

- [Architecture and reproduction workflow](docs/design.md)
- [Click issue case manifest](evals/cases/click-3449.json)

## License

ReproForge source is MIT licensed. Model, API, and dependency terms remain governed by their respective providers.
