# Usage

## Targets and execution

Pass exactly one quoted command or `--url`. The command is parsed into an argument vector and executed directly. Shell operators, substitutions and redirection are not interpreted. Use `--cwd` to set the server's working directory; environment variables are inherited.

```bash
mcp-probe 'python server.py --config development.json' --cwd ./example
mcp-probe --url http://127.0.0.1:8000/mcp
```

`--transport stdio|http` is an optional consistency check. An HTTP endpoint must be a complete `http` or `https` URL without user information or a fragment. `--url` accepts a Streamable HTTP MCP endpoint, not a legacy SSE discovery endpoint.

The probe always performs lifecycle/discovery checks first. Other suites are chosen from advertised capabilities unless explicitly requested. Select suites with a comma-separated list:

```bash
mcp-probe 'python server.py' --suite lifecycle,jsonrpc,tools
mcp-probe --list-checks --output checks.json
```

Valid suites: `lifecycle`, `jsonrpc`, `tools`, `resources`, `prompts`, `notifications`, `tasks`, `auth`, `edge`. Explicitly selecting an unsupported feature may fail its requests. `auth` requires HTTP; `tasks` applies only to revision 2025-11-25. Selecting tools alongside a suite filter requires `tools` or `tasks` in the filter.

## Tool cases

`--tool` is repeatable and matches exact, case-sensitive names. A case file also selects every tool it names; you do not need duplicate `--tool` flags.

```json
{
  "add": {"a": 17, "b": 25},
  "echo": {"text": "hello from mcp-probe"}
}
```

```bash
mcp-probe 'python server.py' --cases cases.json
mcp-probe 'python server.py' --tool add --tool echo
```

Case files must be nonempty JSON objects mapping tool names to argument objects, no larger than 64 KiB. Non-finite numbers are rejected. Missing selected tools fail discovery instead of silently passing.

Without explicit cases, the generator handles a small subset of object, primitive and array schemas. It respects supported bounds and avoids inventing arguments for complex schemas. If it cannot generate a case, execution is skipped with an explanation. Provide domain-appropriate cases for patterns, unions, references and business rules.

With `full`, arguments and structured outputs are checked against JSON Schema offline. Schemas with unresolved external references are not fetched. An unavailable output validation produces a warning. A well-formed tool result with `isError: true` is an application error and produces a warning, rather than being described as malformed protocol data.

`--active` adds schema-invalid arguments only when an invalid object can be constructed. Unconstrained object schemas have no invalid object case. It also probes an unadvertised tool name, retrieves the first listed resource and prompt, and may create a legacy task for a selected task-capable tool. An optional task tool can therefore be invoked both normally and as a task. Only task IDs created by this run can be cancelled; listed tasks are never cancelled. A timeout stops the probe's wait, not necessarily remote work.

## Authentication

Use credentials already available to your shell. The CLI never opens a browser, registers an OAuth client or exchanges authorization codes.

```bash
mcp-probe --url https://service.example/mcp --bearer-token-env MCP_TOKEN
mcp-probe --url https://service.example/mcp --header-env X-Api-Key=MCP_API_KEY
mcp-probe --url https://service.example/mcp -H 'X-Environment: staging'
```

`--header-env` takes `Header-Name=ENVIRONMENT_VARIABLE` and is repeatable. `--header` takes `Name: Value`. Duplicate header names are rejected case-insensitively. Transport-owned headers and `Mcp-Param-*` cannot be overridden.

Environment-based credentials keep secrets out of the command line. Known supplied header values are redacted from reports, as are Bearer tokens appearing in server messages. Query strings and stdio command arguments are omitted from the target label. Reports can still contain server metadata, resource URIs and server-supplied diagnostic text; review them before sharing.

`--check-auth` (or `--suite auth`) makes separate unauthenticated requests and inspects well-known protected-resource and authorization-server metadata. A non-401 response does not prove that access is public. The metadata probes do not forward your credentials or follow redirects. Custom discovery URLs supplied only in a challenge are reported as a limitation. These checks do not establish full OAuth compliance or test token audience, scopes, issuer attacks or login behavior.

HTTPX honors standard proxy and TLS environment settings. For SOCKS proxies, install the optional HTTPX support into the same environment (`httpx[socks]`). For local development, configure `NO_PROXY` appropriately or unset proxy variables for the command. Keep TLS verification enabled.

## Reports and CI

```bash
mcp-probe 'python server.py' --format json --output report.json
mcp-probe 'python server.py' --format junit --output junit.xml --strict
mcp-probe 'python server.py' --verbose --no-color
```

Reports go to stdout unless `--output` is supplied. File writes replace the destination atomically; a failed replacement preserves an existing report. The destination directory must already exist. `NO_COLOR` disables ANSI colors, as does a non-terminal stdout.

JSON report schema `1` contains:

| Field | Meaning |
| --- | --- |
| `mcp_probe_version`, `spec_version` | Probe release and requested MCP revision |
| `report_schema_version` | Report contract version; currently the string `"1"` |
| `target`, `transport`, `mode` | Redacted target, transport and execution mode |
| `timestamp`, `duration_ms` | UTC start time and elapsed suite time |
| `server_info`, `capabilities` | Observed identity and advertised feature presence |
| `suites` | Check IDs, descriptions, status, severity, duration, details and error kind |
| `summary` | Counts of all statuses, including skips and observations |
| `incomplete`, `exit_code` | Whether transport/deadline failure interrupted the run, and the CLI decision |

A check has `error_kind: "transport"` for connectivity or deadline failures. Exceptions due to malformed protocol data use `"protocol"`; explicit check verdicts can leave it null. A transport failure aborts further suite execution, avoiding reuse of an ambiguous response stream. A critical failure prevents dependent checks. A failed handshake produces a failing report even though its dependent checks are skipped.

JUnit maps error/critical failures to `<failure>`, transport failures to `<error>`, and skipped checks to `<skipped>`. `--strict` applies the same warning promotion as the CLI exit code. Setup failures before the run and interrupted runs print a diagnostic and may not produce a report.

## Limits

| Control | Default |
| --- | --- |
| `--timeout` | 10 seconds per check and per client request/listing |
| `--run-timeout` | 120 seconds for the suite run |
| `--max-pages` | 100 pages per listing |
| Peer messages | 1,000 per exchange; 1,000 retained notifications per client |
| Integer parsing | 256 digits per integer; floating-point overflow is rejected |
| Listing items | 10,000 per listing |
| JSON/stdio message and HTTP response | 4 MiB |
| Captured stdio stderr | 64 chunks of at most 4,096 decoded characters |
| Schema size / case file size | 64 KiB / 64 KiB |
| Schema evaluation | Separate subprocess; two-second deadline per operation |

Timeouts must be positive and finite; page limits must be positive integers. Schema workers are killed and reaped on cancellation so pathological regexes cannot block the main event loop. Resource-budget exhaustion is a diagnostic limit, not proof that a server violates the specification.

Transport startup and cleanup are outside the suite run timer. Cleanup is separately bounded. Stdio closes stdin, then escalates termination as needed and handles POSIX process groups. It is not an operating-system sandbox and cannot promise control of processes that detach themselves from that group.

## CLI reference

| Flag | Purpose |
| --- | --- |
| `--url URL`, `--transport stdio|http`, `--cwd DIR` | Target and working directory |
| `--protocol-version VERSION` | `2025-11-25` (default) or `2026-07-28` |
| `--suite LIST`, `--list-checks` | Suite filter or offline catalog |
| `--tool NAME`, `--cases FILE`, `--active` | Execution controls |
| `--check-auth`, `--bearer-token-env VAR` | Metadata inspection and Bearer token source |
| `-H/--header 'Name: Value'`, `--header-env Name=VAR` | Extra HTTP headers |
| `--timeout SECONDS`, `--run-timeout SECONDS`, `--max-pages N` | Resource budgets |
| `--format console|json|junit`, `--output FILE` | Report format and destination |
| `--strict`, `-v/--verbose`, `--no-color` | Exit behavior and display |
| `-V/--version`, `-h/--help` | Version and help |

## Troubleshooting

- **Version mismatch:** select the revision your server implements. No automatic fallback is performed.
- **Invalid JSON on stdout:** send server logs to stderr; stdout is the stdio protocol channel.
- **HTTP 401:** supply the token/header expected by your server. Metadata inspection does not authenticate the main connection.
- **HTTP redirect:** use the final MCP endpoint directly. Redirects are not followed with credentials.
- **Skipped tool call:** supply an explicit case, check the suite filter, and inspect whether the tool requires task execution.
- **Incomplete report:** check startup, connectivity and deadlines. Increase limits only after investigating the slow or excessive response.
- **Skipped notification checks:** no matching notification was observed. The probe does not fabricate a server-specific change event.
