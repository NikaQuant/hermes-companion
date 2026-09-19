from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from ..config import ProfileSpec, Settings


class HermesUpstreamError(RuntimeError):
    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class HermesGateway:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def url(self, profile: ProfileSpec, path: str, query: dict[str, Any] | None = None) -> str:
        if not path.startswith("/"):
            path = "/" + path
        value = f"{self.settings.hermes_base_url}{profile.route_prefix}{path}"
        if query:
            cleaned = {k: v for k, v in query.items() if v is not None}
            if cleaned:
                value += "?" + urlencode(cleaned, doseq=True)
        return value

    def headers(
        self, profile: ProfileSpec, *, session_key: str | None = None,
        extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {profile.api_key}",
            "Accept": "application/json",
        }
        if session_key:
            headers["X-Hermes-Session-Key"] = session_key
        if extra:
            headers.update(extra)
        return headers

    def _timeout(self, *, stream: bool = False) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.settings.hermes_connect_timeout_seconds,
            read=None if stream else self.settings.hermes_request_timeout_seconds,
            write=self.settings.hermes_request_timeout_seconds,
            pool=self.settings.hermes_connect_timeout_seconds,
        )

    async def request(
        self,
        profile: ProfileSpec,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: Any = None,
        session_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout(), transport=self.transport) as client:
            response = await client.request(
                method,
                self.url(profile, path, query),
                headers=self.headers(
                    profile,
                    session_key=session_key,
                    extra={"Content-Type": "application/json", **(extra_headers or {})},
                ),
                json=json_body,
            )
        if response.status_code >= 400:
            raise self._error(response)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"text": response.text}

    async def stream(
        self,
        profile: ProfileSpec,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: Any = None,
        session_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[bytes]:
        client = httpx.AsyncClient(timeout=self._timeout(stream=True), transport=self.transport)
        try:
            async with client.stream(
                method,
                self.url(profile, path, query),
                headers=self.headers(
                    profile,
                    session_key=session_key,
                    extra={
                        "Accept": "text/event-stream",
                        "Cache-Control": "no-cache",
                        **(extra_headers or {}),
                    },
                ),
                json=json_body,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise self._error(response)
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
        finally:
            await client.aclose()

    @staticmethod
    def _error(response: httpx.Response) -> HermesUpstreamError:
        try:
            payload = response.json()
            detail = payload.get("error", payload) if isinstance(payload, dict) else payload
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = response.text[:1000] or f"Hermes returned HTTP {response.status_code}"
        return HermesUpstreamError(response.status_code, detail)


def upstream_http_exception(exc: HermesUpstreamError) -> HTTPException:
    status_code = exc.status_code if 400 <= exc.status_code < 600 else 502
    return HTTPException(status_code=status_code, detail=exc.detail)
