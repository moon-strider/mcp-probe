from __future__ import annotations

from collections.abc import Generator, Iterable
from dataclasses import dataclass

from mcp_probe.protocol import loads_message


@dataclass
class SSEEvent:
    event: str | None
    data: str
    id: str | None = None


def parse_sse_stream(lines: Iterable[str]) -> Generator[SSEEvent, None, None]:
    """Parse dispatched events; incomplete final events are deliberately discarded."""
    event_type: str | None = None
    data: list[str] = []
    event_id: str | None = None
    first_line = True
    for raw in lines:
        if first_line:
            raw = raw.removeprefix("\ufeff")
            first_line = False
        line = raw.rstrip("\r\n")
        if not line:
            if data:
                yield SSEEvent(event_type, "\n".join(data), event_id)
            event_type, data = None, []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if not separator:
            value = ""
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
        elif field == "event":
            event_type = value
        elif field == "id" and "\x00" not in value:
            event_id = value


def parse_sse_json_stream(lines: Iterable[str]) -> Generator[dict, None, None]:
    for event in parse_sse_stream(lines):
        if not event.data:
            continue
        yield loads_message(event.data)
