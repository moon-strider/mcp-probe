# Check catalog

Use `mcp-probe --list-checks` for the same machine-readable catalog without contacting a server. The table below is generated from the check decorators and checked in CI.

## Reading statuses

`PASS` means the exercised assertion succeeded. `FAIL` describes a failed assertion or exception. `WARN` identifies a recommendation, application error or incomplete validation that needs attention. `SKIP` means the behavior was not exercised. `INFO` is an observation, not a conformance verdict.

Error/critical failures fail the run. Warnings affect the exit code only with `--strict`. Transport failure or a run deadline makes the report incomplete with exit code 2. See [usage](usage.md) for the full report contract.

## Prerequisites and scope

| Checks | Execution prerequisite |
| --- | --- |
| `INIT-001`–`INIT-004`, health/envelope checks | Always run during applicable suite execution |
| `INIT-005`, `INIT-006` | Active mode, legacy revision, isolated connections; informational |
| `RPC-003`–`RPC-005` | Active mode; malformed framing recovery also requires stdio |
| `RPC-006` | Active mode and legacy revision; informational |
| `TOOL-001`–`TOOL-003`, `TOOL-007`, `TOOL-008` | Tools capability or explicitly requested tools suite/selection |
| `TOOL-004` | Exact tool selection and usable arguments; task-required tools are deferred |
| `TOOL-005` | Active mode, exact tool selection and provably invalid arguments |
| `TOOL-006` | Active mode; probes a name not advertised by the server |
| `RES-003`, `PROMPT-003` | Active mode; retrieve the first listed resource/prompt |
| `RES-004` | Active mode; unknown-resource probe |
| `NOTIF-002`–`NOTIF-005` | Matching notifications observed during the run |
| `SUB-001`, `SUB-002` | Active mode, legacy subscribe capability and a listed resource |
| `SUB-003` | Always skipped; no server-specific update trigger is assumed |
| `TASK-000`–`TASK-002` | Legacy task suite; selected-tool presence and optional task listing |
| `TASK-003`, `TASK-005`–`TASK-008` | Active mode, selected task-capable tool, advertised task execution; cancel checks also require cancellation capability |
| `TASK-004` | Active mode, legacy task suite |
| `AUTH-001`–`AUTH-003` | HTTP and explicit `--check-auth` or auth suite selection |
| `EDGE-002` | Legacy revision only |
| `EDGE-003` | Active mode; large metadata request, no advertised tool invocation |

Absent capabilities generally exclude their suites. Within included suites, unavailable prerequisites produce explicit skips. Critical failures skip dependent checks; transport failures stop further suites. `RUN-001` is a runtime diagnostic added if the entire run reaches its deadline, not a server conformance check in this static catalog.

<!-- generated checks start -->

| Suite | Check | Severity | Description |
| --- | --- | --- | --- |
| lifecycle | `INIT-001` | CRITICAL | Protocol handshake or discovery succeeds |
| lifecycle | `INIT-002` | CRITICAL | Requested protocol version is supported |
| lifecycle | `INIT-003` | CRITICAL | Capabilities and server identity are well formed |
| lifecycle | `INIT-004` | CRITICAL | Server responds after handshake or discovery |
| lifecycle | `INIT-005` | INFO | Observe requests before legacy initialization |
| lifecycle | `INIT-006` | INFO | Observe repeated legacy initialization |
| jsonrpc | `RPC-001` | CRITICAL | Response has a valid JSON-RPC envelope |
| jsonrpc | `RPC-002` | CRITICAL | Response id matches request id |
| jsonrpc | `RPC-003` | ERROR | Unknown method produces a structured error |
| jsonrpc | `RPC-004` | ERROR | Isolated server survives malformed stdio input |
| jsonrpc | `RPC-005` | ERROR | Unknown method returns method-not-found |
| jsonrpc | `RPC-006` | INFO | Legacy server tolerates unknown notification |
| jsonrpc | `RPC-007` | INFO | Observed protocol error codes |
| tools | `TOOL-001` | CRITICAL | tools/list returns a bounded list |
| tools | `TOOL-002` | CRITICAL | Tool metadata has valid required fields |
| tools | `TOOL-003` | ERROR | Tool input and output schemas are valid |
| tools | `TOOL-004` | ERROR | Selected tool calls return valid content |
| tools | `TOOL-005` | ERROR | Selected tools reject schema-invalid arguments |
| tools | `TOOL-006` | WARNING | Nonexistent tool returns an error |
| tools | `TOOL-007` | WARNING | Tool names follow the naming recommendation |
| tools | `TOOL-008` | WARNING | tools/list pagination terminates |
| resources | `RES-001` | CRITICAL | resources/list returns a list of resources |
| resources | `RES-002` | ERROR | Each resource has uri and name |
| resources | `RES-003` | ERROR | resources/read returns content |
| resources | `RES-004` | WARNING | Nonexistent resource returns error |
| resources | `RES-005` | WARNING | resources/list pagination works |
| prompts | `PROMPT-001` | CRITICAL | prompts/list returns a list of prompts |
| prompts | `PROMPT-002` | ERROR | Prompt names and optional descriptions are valid |
| prompts | `PROMPT-003` | ERROR | prompts/get returns messages |
| prompts | `PROMPT-004` | WARNING | prompts/list pagination works |
| notifications | `NOTIF-001` | CRITICAL | Server remains operational during notification checks |
| notifications | `NOTIF-002` | ERROR | notifications/tools/list_changed format |
| notifications | `NOTIF-003` | ERROR | notifications/resources/list_changed format |
| notifications | `NOTIF-004` | ERROR | notifications/prompts/list_changed format |
| notifications | `NOTIF-005` | WARNING | notifications/progress format and monotonicity |
| notifications | `SUB-001` | ERROR | resources/subscribe returns success |
| notifications | `SUB-002` | ERROR | resources/unsubscribe returns success |
| notifications | `SUB-003` | WARNING | Resource update triggers notification |
| tasks | `TASK-000` | CRITICAL | Selected task tools are advertised |
| tasks | `TASK-001` | ERROR | Advertised tasks/list returns a bounded list |
| tasks | `TASK-002` | ERROR | Listed task metadata is well formed |
| tasks | `TASK-003` | ERROR | tasks/get returns the probe-created task |
| tasks | `TASK-004` | WARNING | Unknown task id returns an error |
| tasks | `TASK-005` | ERROR | Only a probe-created working task is cancelled |
| tasks | `TASK-006` | WARNING | Terminal task rejects cancellation |
| tasks | `TASK-007` | ERROR | Completed probe task returns its tool result |
| tasks | `TASK-008` | ERROR | Task-augmented call returns a task object |
| auth | `AUTH-001` | INFO | Observe unauthenticated endpoint response |
| auth | `AUTH-002` | WARNING | Protected Resource Metadata is discoverable |
| auth | `AUTH-003` | WARNING | Authorization server advertises endpoints |
| edge_cases | `EDGE-001` | ERROR | Request accepts empty application parameters |
| edge_cases | `EDGE-002` | ERROR | Legacy request accepts omitted params |
| edge_cases | `EDGE-003` | INFO | Observe handling of a large metadata payload |
| edge_cases | `EDGE-004` | ERROR | Response arrives within the check deadline |
| edge_cases | `EDGE-005` | INFO | Transport shutdown is managed by the runner |

<!-- generated checks end -->
