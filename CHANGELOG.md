# Changelog

## 0.2.0 — public readiness audit

### Added

- Explicit discovery, selected-tool and active execution controls, with JSON argument case files.
- Explicit 2026-07-28 protocol mode alongside the default 2025-11-25 revision.
- Versioned JSON reports, JUnit, atomic report writes, run deadlines and an offline check catalog.
- Environment-sourced HTTP credentials, report redaction and optional read-only OAuth metadata checks.
- Official SDK demo and six integration scenarios; adversarial transport, task-ownership and schema-worker tests.
- Reproducible dependency lock, stronger CI, clean installation checks and coherent documentation.

### Fixed

- JSON-RPC envelopes, ID types, result structures and error propagation.
- Notification-driven timeout extension, repeated pagination cursors and unbounded peer input.
- Blocking HTTP/SSE reads, response cleanup, modern routing headers, legacy session handling and HTTP error envelopes.
- Content/media validation, legal tool names, parameterless schemas, bounded fixture generation and structured outputs.
- Incorrect legacy task methods/capabilities/results and cancellation of unrelated task handles.
- Stdio logging rules, bounded stderr capture, child-process termination and pipe cleanup.
- False failures for absent optional capabilities and non-normative lifecycle observations.

### Changed / removed

- Tool calls are opt-in. Existing scripts that relied on automatic invocation must use `--tool` or `--cases`; destructive/negative probes require `--active`.
- Interactive OAuth login and its unused client/port options were removed. Supply credentials with `--bearer-token-env` or `--header-env`.
- The old `sse` transport selector was removed. Use `--url` for Streamable HTTP, which accepts JSON and SSE responses.
- HTTPX is now a runtime dependency. The former zero-dependency claim no longer applies.
- Generated distribution archives are no longer tracked in git.

This repository update does not itself publish a new PyPI release. See [protocol coverage](docs/protocols.md) for the supported subset and [audit evidence](docs/audit.md) for validation.
