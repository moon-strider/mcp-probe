from __future__ import annotations

import abc
import logging
import time
from collections.abc import Callable
from typing import Any

from mcp_probe.client import MCPClient
from mcp_probe.types import CheckResult, Severity, Status, SuiteResult

logger = logging.getLogger(__name__)

_CHECK_ATTR = "_check_meta"


class SkipCheck(Exception):
    pass


def check(check_id: str, description: str, severity: Severity) -> Callable:
    def decorator(fn: Callable) -> Callable:
        setattr(fn, _CHECK_ATTR, {
            "check_id": check_id,
            "description": description,
            "severity": severity,
        })
        return fn
    return decorator


class BaseSuite(abc.ABC):
    name: str = ""

    def __init__(self, client: MCPClient, timeout: float = 30.0) -> None:
        self._client = client
        self._timeout = timeout

    def _get_checks(self) -> list[tuple[dict, Callable]]:
        checks: list[tuple[dict, Callable]] = []
        for attr_name in dir(self):
            attr = getattr(self, attr_name, None)
            if callable(attr) and hasattr(attr, _CHECK_ATTR):
                meta = getattr(attr, _CHECK_ATTR)
                checks.append((meta, attr))
        checks.sort(key=lambda c: c[0]["check_id"])
        return checks

    async def run(self) -> SuiteResult:
        results: list[CheckResult] = []
        for meta, method in self._get_checks():
            check_id = meta["check_id"]
            description = meta["description"]
            severity = meta["severity"]
            start = time.perf_counter()
            try:
                result = await method()
                elapsed = (time.perf_counter() - start) * 1000
                if isinstance(result, CheckResult):
                    result.check_id = check_id
                    result.description = description
                    result.severity = severity
                    result.duration_ms = elapsed
                    results.append(result)
                else:
                    results.append(CheckResult(
                        check_id=check_id,
                        description=description,
                        status=Status.PASS,
                        severity=severity,
                        duration_ms=elapsed,
                    ))
            except SkipCheck as exc:
                elapsed = (time.perf_counter() - start) * 1000
                results.append(CheckResult(
                    check_id=check_id,
                    description=description,
                    status=Status.SKIP,
                    severity=severity,
                    duration_ms=elapsed,
                    details=str(exc) if str(exc) else None,
                ))
            except Exception as exc:
                elapsed = (time.perf_counter() - start) * 1000
                logger.debug("Check %s failed with exception: %s", check_id, exc, exc_info=True)
                results.append(CheckResult(
                    check_id=check_id,
                    description=description,
                    status=Status.FAIL,
                    severity=severity,
                    duration_ms=elapsed,
                    details=str(exc),
                ))
        return SuiteResult(name=self.name, checks=results)

    def skip(self, reason: str = "") -> CheckResult:
        raise SkipCheck(reason)

    def pass_check(self, details: str | None = None) -> CheckResult:
        return CheckResult(
            check_id="",
            description="",
            status=Status.PASS,
            severity=Severity.INFO,
            duration_ms=0,
            details=details,
        )

    def fail_check(self, details: str) -> CheckResult:
        return CheckResult(
            check_id="",
            description="",
            status=Status.FAIL,
            severity=Severity.INFO,
            duration_ms=0,
            details=details,
        )

    def warn_check(self, details: str) -> CheckResult:
        return CheckResult(
            check_id="",
            description="",
            status=Status.WARN,
            severity=Severity.INFO,
            duration_ms=0,
            details=details,
        )

    def info_check(self, details: str) -> CheckResult:
        return CheckResult(
            check_id="",
            description="",
            status=Status.INFO,
            severity=Severity.INFO,
            duration_ms=0,
            details=details,
        )
