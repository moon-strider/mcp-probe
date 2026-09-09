# Contributing

Protocol bug reports are most useful with the selected MCP revision, transport, probe version, check ID, and a minimal server or redacted response transcript. Do not include tokens or private resource contents.

## Development environment

The lock file pins development and demo dependencies. Use Python 3.10–3.13 on Linux and uv 0.12.8, matching CI.

```bash
uv sync --locked --extra dev --extra full
uv run --no-sync ruff check src tests examples scripts
uv run --no-sync ruff format --check src tests examples scripts
uv run --no-sync mypy src
uv run --no-sync pytest -m 'not integration' --cov=mcp_probe --cov-fail-under=80
uv run --no-sync python scripts/check_docs.py
uv run --no-sync pip-audit --local --skip-editable --progress-spinner off
```

The unit/regression suite needs no external server. HTTP tests use loopback or an in-process mock transport and explicitly remove inherited proxy variables. Tests include real subprocess cleanup and deliberately pathological schema evaluation.

## Official SDK integration

The demo uses the official `mcp==2.2.0` package. It runs as an independent server process; it is not used internally by the probe client.

```bash
uv sync --locked --extra dev --extra full --extra demo
MCP_PROBE_SDK_PYTHON="$PWD/.venv/bin/python" \
  uv run --no-sync pytest -m integration
```

Six scenarios cover both protocol revisions across stdio, HTTP JSON and HTTP SSE. They exercise selected tools, a resource and a prompt, plus active negative checks. Without `MCP_PROBE_SDK_PYTHON`, these tests are explicitly skipped. You can point it at a separate environment containing the same official SDK version.

To inspect the HTTP demo manually, keep this process running in another terminal:

```bash
uv run --no-sync python examples/server.py --port 8000
```

Then connect with `--url http://127.0.0.1:8000/mcp`. Add `--json` to the server command to use JSON responses instead of SSE.

## Packaging

```bash
uv build
uv run --no-sync twine check dist/*
uv run --no-sync python scripts/verify_package.py
```

The package verifier creates temporary environments, installs base and full wheels, and runs the installed CLI outside the source checkout. It requires package-index access. Build output is ignored by git and available as a CI artifact. Publishing to PyPI is a separate maintainer action; CI does not publish packages or create releases.

## Making changes

1. Reproduce protocol problems with a focused regression test and cite the applicable specification revision.
2. Keep tool execution explicitly selected. Do not infer permission from annotations or cancel tasks discovered in a listing.
3. Preserve bounded input, deadlines, subprocess cleanup and offline schema resolution.
4. Distinguish malformed protocol data, application errors, transport failures and unexercised behavior in reports.
5. Update documentation and `CHANGELOG.md` for user-visible changes. Regenerate the check table with `python scripts/check_docs.py --write` after changing check metadata.
6. Use lowercase commit messages of at most ten words, without digits.

CI runs unit tests on Python 3.10–3.13, linting and type checking, the official SDK integration, dependency auditing, documentation checks and clean package installation. The coverage floor is 80% of executable statements; coverage is not a substitute for meaningful behavior checks. Subprocess code is exercised but is not included in the parent process's coverage counters.

When updating dependencies, edit the relevant constraints, run `uv lock`, and run the same checks before committing the new lock file. GitHub Actions are pinned to reviewed commit SHAs.
