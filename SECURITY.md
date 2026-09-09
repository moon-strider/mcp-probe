# Security

The current development line is 0.2.x. No extended support commitment is made for earlier releases.

Report exploitable vulnerabilities through [GitHub private vulnerability reporting](https://github.com/moon-strider/mcp-probe/security/advisories/new) when available. If private reporting is unavailable, open an issue requesting a private reporting channel without exploit details or secrets. Include the affected version, a minimal reproduction and the expected boundary.

## Boundaries

mcp-probe launches the stdio program you specify with your user's permissions. It is not a sandbox. A malicious program can access the same files, environment and network as that user. Run untrusted servers inside an isolation boundary you control.

Discovery does not call advertised tools or retrieve resource/prompt contents. Selecting a tool authorizes execution; active mode additionally sends negative requests, reads content and can create/cancel selected legacy tasks. Only tasks created by the current run are eligible for cancellation. Remote effects are not rolled back on timeout.

HTTP redirects are not followed, TLS verification remains enabled, and metadata discovery does not forward authorization headers. Prefer token/header environment options over credentials in command-line arguments. Reports redact known supplied header credentials but may contain other server-provided metadata and diagnostics.

JSON/HTTP input, pagination, notification capture, stderr and execution time are bounded. JSON Schema validation uses offline resolution in a separate, cancellable worker so peer-provided regular expressions cannot block the main event loop. These limits reduce accidental resource exhaustion; they do not isolate the stdio server itself.

The CI dependency audit checks published advisories for resolved packages. A clean audit is a point-in-time result, not a guarantee that no vulnerabilities exist.
