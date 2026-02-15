# mcp-probe

[![CI](https://github.com/moon-strider/mcp-probe/actions/workflows/ci.yml/badge.svg)](https://github.com/moon-strider/mcp-probe/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

CLI tool that validates MCP server protocol compliance against the [Model Context Protocol](https://modelcontextprotocol.io/) specification (2025-11-25).

Zero runtime dependencies. Pure Python stdlib.

## Installation

```bash
pip install git+https://github.com/moon-strider/mcp-probe.git

# With full JSON Schema validation
pip install "mcp-probe[full] @ git+https://github.com/moon-strider/mcp-probe.git"
```

## Quick Start

**Stdio transport:**
```bash
mcp-probe "python my_server.py"
```

**HTTP transport:**
```bash
mcp-probe --url https://example.com/mcp
```

**CI mode (strict, JSON output):**
```bash
mcp-probe "uvx my-server" --strict --format json
```

## What It Checks

### Lifecycle & Handshake

| ID | Description | Severity |
|---|---|---|
| INIT-001 | Server responds to initialize | CRITICAL |
| INIT-002 | protocolVersion is present and valid | CRITICAL |
| INIT-003 | capabilities object is present | CRITICAL |
| INIT-004 | notifications/initialized does not crash server | CRITICAL |
| INIT-005 | Request before initialize is rejected | WARNING |
| INIT-006 | Double initialize is rejected | WARNING |

### JSON-RPC Protocol

| ID | Description | Severity |
|---|---|---|
| RPC-001 | Response contains jsonrpc 2.0 field | CRITICAL |
| RPC-002 | Response id matches request id | CRITICAL |
| RPC-003 | Error response has valid structure | ERROR |
| RPC-004 | Server survives invalid JSON input | ERROR |
| RPC-005 | Unknown method returns -32601 | WARNING |
| RPC-006 | Server ignores unknown notification | INFO |
| RPC-007 | Error codes summary | INFO |

### Tools

| ID | Description | Severity |
|---|---|---|
| TOOL-001 | tools/list returns a list of tools | CRITICAL |
| TOOL-002 | Each tool has name, description, inputSchema | CRITICAL |
| TOOL-003 | inputSchema is valid JSON Schema | ERROR |
| TOOL-004 | Tool call with valid arguments succeeds | ERROR |
| TOOL-005 | Tool call with invalid arguments returns error | ERROR |
| TOOL-006 | Nonexistent tool returns error | WARNING |
| TOOL-007 | Tool names follow naming convention | INFO |
| TOOL-008 | tools/list pagination works | WARNING |

### Resources

| ID | Description | Severity |
|---|---|---|
| RES-001 | resources/list returns a list of resources | CRITICAL |
| RES-002 | Each resource has uri and name | ERROR |
| RES-003 | resources/read returns content | ERROR |
| RES-004 | Nonexistent resource returns error | WARNING |
| RES-005 | resources/list pagination works | WARNING |

### Prompts

| ID | Description | Severity |
|---|---|---|
| PROMPT-001 | prompts/list returns a list of prompts | CRITICAL |
| PROMPT-002 | Each prompt has name and description | ERROR |
| PROMPT-003 | prompts/get returns messages | ERROR |
| PROMPT-004 | prompts/list pagination works | WARNING |

### Notifications & Subscriptions

| ID | Description | Severity |
|---|---|---|
| NOTIF-001 | Server accepts notifications/initialized | CRITICAL |
| NOTIF-002 | notifications/tools/list_changed format | ERROR |
| NOTIF-003 | notifications/resources/list_changed format | ERROR |
| NOTIF-004 | notifications/prompts/list_changed format | ERROR |
| NOTIF-005 | notifications/progress format and monotonicity | WARNING |
| SUB-001 | resources/subscribe returns success | ERROR |
| SUB-002 | resources/unsubscribe returns success | ERROR |
| SUB-003 | Resource update triggers notification | WARNING |

### Tasks

| ID | Description | Severity |
|---|---|---|
| TASK-001 | tasks/list returns a list of tasks | CRITICAL |
| TASK-002 | Each task has taskId, status, createdAt | ERROR |
| TASK-003 | tasks/get returns task status | ERROR |
| TASK-004 | Nonexistent taskId returns error | WARNING |
| TASK-005 | tasks/cancel cancels a working task | ERROR |
| TASK-006 | tasks/cancel on terminal task returns error | WARNING |
| TASK-007 | tasks/result returns completed task result | ERROR |
| TASK-008 | Task-augmented tools/call returns task handle | ERROR |

### Authentication (OAuth 2.1)

| ID | Description | Severity |
|---|---|---|
| AUTH-001 | Server returns 401 with WWW-Authenticate | INFO |
| AUTH-002 | Protected Resource Metadata discovery | INFO |
| AUTH-003 | OAuth Authorization Server Metadata discovery | INFO |
| AUTH-004 | Full OAuth flow with Bearer token | ERROR |

### Edge Cases

| ID | Description | Severity |
|---|---|---|
| EDGE-001 | tools/list accepts empty params object | WARNING |
| EDGE-002 | tools/list accepts missing params field | WARNING |
| EDGE-003 | Server handles 100KB+ payload | INFO |
| EDGE-004 | Response time within timeout | WARNING |
| EDGE-005 | Server graceful shutdown on SIGTERM | INFO |

## CLI Reference

| Argument | Type | Default | Description |
|---|---|---|---|
| `command` | positional | — | Shell command to launch MCP server (stdio) |
| `--url` | string | — | URL of remote MCP server (HTTP) |
| `--transport` | string | auto | Transport type: `stdio`, `http` |
| `--timeout` | int | 30 | Timeout in seconds per check |
| `--suite` | string | all | Suites to run (comma-separated) |
| `--format` | string | console | Output format: `console`, `json` |
| `--output` | string | stdout | Write report to file |
| `-v` / `--verbose` | flag | false | Show details for all checks |
| `--strict` | flag | false | Treat warnings as failures (exit 1) |
| `--no-color` | flag | false | Disable ANSI colors |
| `-H` / `--header` | string | — | Custom HTTP header (repeatable) |
| `--oauth` | flag | false | Enable OAuth 2.1 flow |
| `--client-id` | string | — | OAuth client_id |
| `--redirect-port` | int | 8765 | OAuth callback port |

**Suite names:** `lifecycle`, `jsonrpc`, `tools`, `resources`, `prompts`, `notifications`, `tasks`, `auth`, `edge`

**Exit codes:**
- `0` — all checks passed (no FAIL with CRITICAL/ERROR severity)
- `1` — at least one check failed; or with `--strict`, at least one warning
- `2` — invalid arguments or connection failure

## Output Formats

**Console (default):**
```
mcp-probe v0.1.0 — MCP Server Protocol Compliance Validator
Target: python my_server.py
Transport: stdio
Spec: MCP 2025-11-25

────────────────────────────────────────────────────────────
 Lifecycle & Handshake
────────────────────────────────────────────────────────────
 PASS  INIT-001   Server responds to initialize              45ms
 PASS  INIT-002   protocolVersion is present and valid        12ms
...

────────────────────────────────────────────────────────────
 Summary: 18 passed, 1 failed, 2 warnings, 1 skipped
 Duration: 1.2s
```

**JSON (`--format json`):**
```json
{
  "mcp_probe_version": "0.1.0",
  "spec_version": "2025-11-25",
  "target": "python my_server.py",
  "transport": "stdio",
  "timestamp": "2026-02-15T12:00:00Z",
  "duration_ms": 1234,
  "summary": {
    "total": 22,
    "passed": 18,
    "failed": 1,
    "warnings": 2,
    "skipped": 1,
    "info": 0
  },
  "suites": [...]
}
```

## CI/CD Integration

**GitHub Actions:**
```yaml
- name: Validate MCP server
  run: |
    pip install git+https://github.com/moon-strider/mcp-probe.git
    mcp-probe "python my_server.py" --strict --format json --output report.json
```

## Contributing

```bash
git clone https://github.com/moon-strider/mcp-probe.git
cd mcp-probe
pip install -e ".[dev,full]"
pytest tests/ -v
ruff check src/ tests/
```

## License

MIT
