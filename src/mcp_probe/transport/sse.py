from __future__ import annotations

import json
import logging
from collections.abc import Generator, Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    event: str | None
    data: str
    id: str | None = None


def parse_sse_stream(lines: Iterable[str]) -> Generator[SSEEvent, None, None]:
    event_type: str | None = None
    data_buffer: list[str] = []
    event_id: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")

        if line.startswith(":"):
            continue

        if not line:
            if data_buffer:
                yield SSEEvent(
                    event=event_type,
                    data="\n".join(data_buffer),
                    id=event_id,
                )
            event_type = None
            data_buffer = []
            event_id = None
            continue

        if line.startswith("data:"):
            data_buffer.append(line[5:].strip())
        elif line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("id:"):
            event_id = line[3:].strip()

    if data_buffer:
        yield SSEEvent(
            event=event_type,
            data="\n".join(data_buffer),
            id=event_id,
        )


def parse_sse_json_stream(lines: Iterable[str]) -> Generator[dict, None, None]:
    for event in parse_sse_stream(lines):
        try:
            yield json.loads(event.data)
        except json.JSONDecodeError:
            logger.debug("SSE event data is not valid JSON: %s", event.data[:200])
