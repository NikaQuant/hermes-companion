from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class SSEObserver:
    """Incrementally observes SSE frames while preserving the original byte stream."""

    def __init__(self, callback: Callable[[str, dict[str, Any]], None]):
        self._callback = callback
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._buffer.extend(chunk)
        while True:
            marker = self._find_boundary()
            if marker is None:
                return
            index, width = marker
            frame = bytes(self._buffer[:index])
            del self._buffer[: index + width]
            self._process(frame)

    def flush(self) -> None:
        if self._buffer:
            self._process(bytes(self._buffer))
            self._buffer.clear()

    def _find_boundary(self) -> tuple[int, int] | None:
        candidates = []
        for boundary in (b"\n\n", b"\r\n\r\n"):
            index = self._buffer.find(boundary)
            if index >= 0:
                candidates.append((index, len(boundary)))
        return min(candidates) if candidates else None

    def _process(self, frame: bytes) -> None:
        event_name = "message"
        data_lines: list[str] = []
        for raw_line in frame.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n"):
            if not raw_line or raw_line.startswith(":"):
                continue
            field, _, value = raw_line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event_name = value or "message"
            elif field == "data":
                data_lines.append(value)
        if not data_lines:
            return
        payload_text = "\n".join(data_lines)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = {"data": payload_text}
        if isinstance(payload, dict):
            event_name = str(payload.get("event") or event_name)
            try:
                self._callback(event_name, payload)
            except Exception:
                # Notifications are garnish; they must never break the live stream.
                pass
