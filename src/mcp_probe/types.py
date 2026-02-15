from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

SPEC_VERSION = "2025-11-25"
PROBE_VERSION = "0.1.0"
DEFAULT_TIMEOUT = 30


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"
    INFO = "INFO"


class Severity(Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


JSONRPC_ERROR_CODES: dict[int, str] = {
    -32700: "Parse error",
    -32600: "Invalid Request",
    -32601: "Method not found",
    -32602: "Invalid params",
    -32603: "Internal error",
    -32800: "Request cancelled",
    -32801: "Content too large",
}


@dataclass
class CheckResult:
    check_id: str
    description: str
    status: Status
    severity: Severity
    duration_ms: float
    details: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.check_id,
            "description": self.description,
            "status": self.status.value,
            "severity": self.severity.value,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclass
class SuiteResult:
    name: str
    checks: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "checks": [c.to_dict() for c in self.checks],
        }


@dataclass
class ProbeReport:
    probe_version: str
    spec_version: str
    target: str
    transport: str
    timestamp: str
    duration_ms: float
    server_info: dict | None
    capabilities: dict
    suites: list[SuiteResult] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "skipped": 0,
            "info": 0,
        }
        for suite in self.suites:
            for check in suite.checks:
                counts["total"] += 1
                if check.status is Status.PASS:
                    counts["passed"] += 1
                elif check.status is Status.FAIL:
                    counts["failed"] += 1
                elif check.status is Status.WARN:
                    counts["warnings"] += 1
                elif check.status is Status.SKIP:
                    counts["skipped"] += 1
                elif check.status is Status.INFO:
                    counts["info"] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "mcp_probe_version": self.probe_version,
            "spec_version": self.spec_version,
            "target": self.target,
            "transport": self.transport,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "server_info": self.server_info,
            "capabilities": self.capabilities,
            "summary": self.summary,
            "suites": [s.to_dict() for s in self.suites],
        }
