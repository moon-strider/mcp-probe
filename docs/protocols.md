# Protocol coverage

mcp-probe checks observable behavior against a chosen MCP revision. It is a diagnostic client with an explicit coverage boundary, not an exhaustive conformance or security certification suite.

## Supported revisions

| Behavior | 2025-11-25 (default) | 2026-07-28 (explicit) |
| --- | --- | --- |
| Startup | `initialize`, then `notifications/initialized` | `server/discover` |
| Version handling | Require the requested negotiated version | Require the requested version in `supportedVersions` |
| Request metadata | Client information in initialization | Version, client capabilities and client information in request `_meta` |
| HTTP metadata | Protocol version after initialization; session ID when assigned | Protocol version, `Mcp-Method`, encoded `Mcp-Name` and annotated `Mcp-Param-*` |
| Health check | `ping` | `server/discover` |
| Successful results | Object result | Object result with `resultType` |
| Cacheable results | No cache-hint requirement | Validate `ttlMs` and `cacheScope` on discovery and exercised list/read results |
| Structured tool results | Object-valued `structuredContent` | Any JSON value, checked against outputSchema when available |
| Server requests | Answer ping; reject unsupported client capabilities | Standalone peer requests are rejected; MRTR is not implemented |
| Tasks | Selected, owned legacy core task checks | Modern task extension is not implemented |

The default preserves compatibility with the previous release's target revision. Choosing a version is intentional: automatic fallback could report success for a different protocol than the one a developer meant to test. Older revisions are not claimed as supported.

## Transport scope

**Stdio:** one UTF-8 JSON object per line, without a shell. Non-JSON stdout fails validation. Received JSON-RPC messages require a valid version, envelope and ID type; booleans do not count as integer IDs. Notifications cannot extend the request deadline indefinitely. Stderr capture, message size, pagination and process cleanup are bounded.

**Streamable HTTP:** a POST per message; JSON and incremental SSE response readers; notifications and, for legacy peers, server-initiated requests can be processed before a final response. LF, CRLF and CR event framing are accepted. A matching final response closes the response stream immediately, even when the server does not close it. Bodies have a total byte limit and exchanges have a total deadline.

Legacy session IDs are preserved on subsequent messages and deleted during cleanup when supported. Modern mode does not use session IDs. Modern `400` and `404` JSON-RPC error bodies remain available to protocol checks. Redirects are rejected and credentials are not forwarded to another endpoint.

Modern custom header annotations are validated and values are extracted only along static schema `properties` paths. Encoded Unicode, whitespace and sentinel values follow the specification's Base64 format. Invalid annotations fail the diagnostic listing; their tools are not executed. A changed schema/header-mismatch response is reported rather than automatically retried, because retrying a tool can repeat its effects.

The probe does **not** implement legacy HTTP+SSE discovery, a standalone legacy GET stream, SSE reconnection/resumption, automatic request replay, `subscriptions/listen` or modern MRTR. It does not advertise sampling, roots or elicitation capabilities. A server requiring those capabilities cannot be fully exercised by this client.

## What a report does not establish

- Complete feature coverage: resource templates, completion, logging configuration, modern subscriptions and the modern task extension are outside the current check catalog.
- End-to-end OAuth correctness: only unauthenticated response and metadata observations are available.
- Tool business correctness: arguments can be schema-valid while unsuitable for an application's domain. The probe checks result structure, not the truth of returned content.
- Security of the server process or network deployment: there is no exploit scan, isolation container, origin-policy attack suite or access-control audit.
- Concurrent load tolerance: requests are serialized. The probe is not a benchmark or load generator.
- Notification causality: only observed notification shape and progress ordering are checked; no server-specific mutation is synthesized to trigger changes.
- Cancellation of remote work after a timeout: the client stops waiting and cleans up its connection. Legacy task cancellation is tested only for task handles this run created.
- Every JSON Schema dialect or reference graph: the optional validator operates offline, with bounded worker execution. External references are not fetched; fixture generation intentionally handles only a conservative subset.

The first resource and prompt are retrieved in active mode. All selected tools with usable cases are exercised within the check deadline; other advertised tools are inspected but not called. Very large selected sets may need a larger timeout or smaller suite/case selection.

Lifecycle requests before initialization and repeated initialization are informational observations on isolated connections. They do not assert a universal rejection requirement that the specification does not make. Likewise, shutdown is managed by the client and is not represented as proof of application-level graceful shutdown.

## Primary references

- [MCP 2025-11-25 specification](https://modelcontextprotocol.io/specification/2025-11-25)
- [Legacy transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [Legacy tasks](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks)
- [MCP 2026-07-28 changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
- [Modern discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [Modern Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [Modern tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
