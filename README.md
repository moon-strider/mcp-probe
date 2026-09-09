# mcp-probe

[![CI](https://github.com/moon-strider/mcp-probe/actions/workflows/ci.yml/badge.svg)](https://github.com/moon-strider/mcp-probe/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Find protocol problems in an MCP server before your users do.**

mcp-probe is a command-line checker for Model Context Protocol servers. It connects over stdio or Streamable HTTP, checks actual response envelopes and feature results, and produces a readable console report or machine-readable JSON/JUnit.

Start with discovery. Choose exact tools when you want to test execution. Use active mode for negative probes, resource reads, prompt retrieval and selected legacy tasks.

## Try it locally

Python 3.10–3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/) are required for this walkthrough. The included demo uses the official MCP Python SDK and needs no model, API key or external service.

```bash
git clone https://github.com/moon-strider/mcp-probe.git
cd mcp-probe
uv sync --locked --extra full --extra demo

# Discover the demo's tools, resources and prompts.
uv run --no-sync mcp-probe ".venv/bin/python examples/server.py" \
  --protocol-version 2026-07-28

# Execute only the tools named in this case file.
uv run --no-sync mcp-probe ".venv/bin/python examples/server.py" \
  --protocol-version 2026-07-28 --cases examples/cases.json
```

The case file exercises integer addition and text echo. Add `--active` to also run negative checks and retrieve the demo resource and prompt. The commands above use POSIX shell paths; Linux is the tested platform.

For a standalone CLI installed from this checkout:

```bash
pipx install '.[full]'
mcp-probe --help
```

The `full` extra enables offline JSON Schema validation. The base installation still checks protocol envelopes, metadata and content structure. HTTPX is a runtime dependency; the SDK is only needed for the optional demo/integration extra.

## Point it at your server

```bash
# A stdio command is one quoted argument, executed without a shell.
mcp-probe 'python path/to/server.py'

# Streamable HTTP, with a token already available in your environment.
mcp-probe --url http://127.0.0.1:8000/mcp \
  --bearer-token-env MCP_TOKEN --format json --output report.json

# Select a tool explicitly and use the newer protocol revision.
mcp-probe --url http://127.0.0.1:8000/mcp \
  --protocol-version 2026-07-28 --tool echo

# A CI report with bounded execution and warnings treated as failures.
mcp-probe 'python path/to/server.py' --cases cases.json --active \
  --timeout 10 --run-timeout 120 --strict --format junit --output junit.xml
```

The default revision is **2025-11-25**, retained for existing servers. Select **2026-07-28** explicitly for stateless discovery and request metadata. The probe tests the requested revision; it does not silently fall back to another version.

## What it checks

| Area | Coverage |
| --- | --- |
| Lifecycle | Legacy initialize/initialized or modern server discovery, version, identity, capabilities, responsiveness |
| JSON-RPC | Envelope shape, response ID and type, structured errors, explicit negative probes |
| Tools | Bounded listing, definitions, offline input/output schemas, selected calls, content blocks, argument rejection |
| Resources and prompts | Listing and pagination, metadata, active content retrieval and result structure |
| Notifications | Observed message format and progress monotonicity; legacy subscribe/unsubscribe where advertised |
| Legacy tasks | Correct task methods and metadata; task creation and cancellation restricted to selected probe-created work |
| HTTP | JSON and incremental SSE, headers, legacy sessions, bounded bodies and timeouts, credential-preserving redirect policy |
| Reports | Console, versioned JSON and JUnit; explicit skips, incomplete runs and CI exit codes |

A passing report means the exercised checks passed. It is **not exhaustive MCP certification**. Unexercised features are skipped or excluded when unsupported. [Protocol coverage](docs/protocols.md) describes the limits, including MRTR, subscriptions and the modern task extension.

## Execution controls

| Invocation | Behavior |
| --- | --- |
| No execution flags | Discover metadata and perform health checks; no advertised tool calls, resource reads or prompt retrieval |
| `--tool NAME` | Allow this exact tool to be called with conservative generated arguments |
| `--cases FILE` | Allow tools named in a JSON map, with explicit argument objects |
| `--active` | Add negative requests, content reads and isolated framing/lifecycle probes; selected tools may receive invalid arguments and task-augmented calls |
| `--check-auth` | Inspect unauthenticated HTTP responses and OAuth metadata without logging in |

`--active` alone does not select advertised tools. Tool annotations do not grant permission. Starting a stdio server runs the program with your permissions; discovery is not a sandbox. Calls may have effects and remote work can outlive a timeout. Use a disposable test server for active checks.

## Read the results

| Exit code | Meaning |
| --- | --- |
| `0` | No failing error/critical checks; warnings are allowed unless `--strict` |
| `1` | A checked requirement failed, or strict mode promoted a warning |
| `2` | Invalid invocation, setup/reporting failure, transport failure or incomplete run |
| `130` | Interrupted by the user |

`SKIP` is not a pass. `INFO` records an observation without asserting a requirement. `--strict` also promotes warning-severity failures and `WARN` results. JSON includes `exit_code`, `incomplete`, `mode`, `spec_version` and `report_schema_version`.

## Documentation

- [Usage and CLI reference](docs/usage.md): flags, cases, authentication, reports and troubleshooting.
- [Check catalog](docs/checks.md): every check ID, severity and execution prerequisites.
- [Protocol coverage](docs/protocols.md): supported revisions, transport behavior and deliberate limits.
- [Audit and verification](docs/audit.md): reproduced defects and the validation used for this release.
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md) and [changelog](CHANGELOG.md).

MIT licensed. Contributions should include a reproducible server or response transcript for protocol issues.
