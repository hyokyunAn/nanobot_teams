"""Tiny HTTP client for sending inbound messages to nanobot."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import httpx


@dataclass
class NanobotResult:
    status: str
    content: str = ""
    request_id: str = ""
    error: str = ""


class NanobotClient:
    def __init__(
        self,
        inbound_url: str,
        timeout_sec: float,
        token: str = "",
        host_header: str = "",
        verify_ssl: bool = True,
    ):
        self.inbound_url = inbound_url
        self.token = token
        self.host_header = host_header.strip()
        self._client = httpx.AsyncClient(timeout=timeout_sec, verify=verify_ssl)

    async def close(self) -> None:
        await self._client.aclose()

    async def ask(
        self,
        *,
        chat_id: str,
        sender_id: str,
        content: str,
        metadata: dict,
    ) -> NanobotResult:
        request_id = f"req_{uuid4().hex}"
        payload = {
            "request_id": request_id,
            "chat_id": chat_id,
            "sender_id": sender_id,
            "content": content,
            "metadata": metadata,
        }
        headers = {"content-type": "application/json"}
        if self.token:
            headers["x-internal-token"] = self.token
        if self.host_header:
            headers["host"] = self.host_header
            headers["x-forwarded-host"] = self.host_header

        try:
            resp = await self._client.post(
                self.inbound_url,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        except Exception as e:
            return NanobotResult(status="error", error=str(e), request_id=request_id)

        data = resp.json()
        return NanobotResult(
            status=str(data.get("status", "ok")),
            content=str(data.get("content", "")),
            request_id=str(data.get("request_id", request_id)),
        )

