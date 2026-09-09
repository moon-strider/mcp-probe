# Public readiness audit

This audit starts from commit `b80118e` and prepares the 0.2.0 development release. It covers the implementation, execution defaults, protocol assumptions, packaging, documentation and repository maintenance. Verification was performed on Linux with CPython 3.12.14; CI extends unit coverage to Python 3.10–3.13.

## Baseline and reproduced problems

The original suite had 70 passing tests and approximately 55% statement coverage. Passing that suite did not establish correctness of the full client: task checks had no measured coverage and transport/runner branches were largely untested.

An initial regression commit recorded 15 cases: 14 failed against the original implementation and one passed. Those cases now pass. Subsequent tests cover the additional behavior introduced during the audit.

| Finding | Resolution |
| --- | --- |
| Notifications extended request timeouts indefinitely | Total exchange/check/run deadlines and message limits |
| Pagination could repeat cursors forever and errors became empty lists | Shared bounded pagination, cursor/item validation and error propagation |
| Malformed envelopes and boolean response IDs were accepted | Strict JSON-RPC shape and ID-type checks |
| Blocking HTTP reads waited for SSE EOF | Async HTTPX transport, incremental event parsing and immediate final-response cleanup |
| Unbounded stderr and incomplete process cleanup | Bounded capture, POSIX process-group termination and pipe draining |
| Tools were called without explicit selection | Discovery default, exact tool allowlist and case files |
| Invalid tool results and schema-generated fixtures went unchecked | Content validation, offline schemas, conservative generation and structured-output checks |
| Arbitrary listed tasks could be cancelled; result method was incorrect | Own-handle-only cancellation, correct capabilities/metadata and `tasks/result` |
| Optional capabilities and lifecycle assumptions caused false failures | Capability-aware suites and informational isolated lifecycle observations |
| OAuth CLI controls did not reliably authenticate the transport | Removed interactive login; added environment credentials and scoped metadata checks |
| Report/CLI failures were ambiguous | Validated options, distinct incomplete status, JSON/JUnit and atomic writes |
| Latest protocol assumptions differed from legacy behavior | Explicit 2025-11-25 and 2026-07-28 modes, with documented coverage limits |
| Peer schemas could monopolize the event loop | Cancellable subprocess validation, offline references and regression for catastrophic regexes |
| Generated package binaries were tracked | Removed binaries, expanded ignore rules and CI build artifacts |

## Verification

- **186 unit/regression tests** pass locally, with approximately **85% statement coverage**. The coverage threshold in CI is 80%. Subprocess work is exercised but not counted in the parent process's coverage.
- **Six official SDK scenarios** pass using `mcp==2.2.0`: both requested protocol revisions across stdio, Streamable HTTP JSON and Streamable HTTP SSE. They execute two selected tools, read a resource, retrieve a prompt and run active negative checks.
- HTTP tests additionally exercise an open SSE stream after its final response, CR/LF framing and split UTF-8, notifications and server ping before the response, stalled bodies, oversized payloads, redirects, metadata headers and modern HTTP error envelopes.
- Task tests prove that listed foreign task IDs are not cancelled, execution requires both selection and active mode, task results use related-task metadata, and completion/cancellation races are handled.
- CLI/report tests cover contradictory flags, non-finite limits, malformed case files, environment credentials, report redaction, atomic-write failures, JUnit and exit decisions.
- Stdio tests verify stderr bounds and termination of a descendant holding inherited pipes. Schema tests verify cancellation and cleanup of a worker running a pathological regular expression.
- Ruff lint/format checks and mypy with untyped function-body checking pass.
- Source and wheel distributions build successfully and pass `twine check`. Separate base and full environments install the wheel and exercise the installed CLI outside the checkout.
- The runtime dependency audit was clean. Extending the audit to development tools found [PYSEC-2026-1845](https://osv.dev/vulnerability/PYSEC-2026-1845) in pytest 8.3.5; pytest was updated to 9.0.3 and the resolved environment was audited again with no known vulnerabilities found. Dependency auditing is a point-in-time check, not an independent security certification.

The [CI workflow](../.github/workflows/ci.yml) makes the unit matrix, official SDK integration, quality checks and packaging checks repeatable. The [contributor guide](../CONTRIBUTING.md) contains the exact commands.

## Remaining boundaries

The audit does not claim complete MCP certification. Modern MRTR, subscriptions and task extensions, full OAuth flows, load testing, server-specific notification triggers and business correctness are not implemented. See [protocol coverage](protocols.md) for the full boundary. No language model is needed to verify this deterministic protocol client; the demo and test servers use local synthetic data.

The changes prepare the repository and build artifacts. Publishing a package to PyPI remains a separate release operation.
