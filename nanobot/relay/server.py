"""HTTP relay server for Teams backend -> nanobot inbound requests."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import httpx
from aiohttp import web
from aiohttp.web import Request, Response, json_response
from loguru import logger

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.cron.service import CronService
from nanobot.heartbeat.service import HeartbeatService


class TeamsInboundRelayServer:
    """Relay inbound requests to AgentLoop and route outbound to Teams backend."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        agent: AgentLoop,
        cron: CronService,
        heartbeat: HeartbeatService,
        host: str,
        port: int,
        inbound_timeout_sec: float,
        internal_token: str = "",
        teams_proactive_url: str = "",
        teams_internal_token: str = "",
    ):
        self.bus = bus
        self.agent = agent
        self.cron = cron
        self.heartbeat = heartbeat
        self.host = host
        self.port = port
        self.inbound_timeout_sec = inbound_timeout_sec
        self.internal_token = internal_token
        self.teams_proactive_url = teams_proactive_url
        self.teams_internal_token = teams_internal_token

        self._running = False
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._agent_task: asyncio.Task | None = None
        self._outbound_task: asyncio.Task | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._http = httpx.AsyncClient(timeout=15.0)

    def _auth_ok(self, req: Request) -> bool:
        if not self.internal_token:
            return True
        return req.headers.get("x-internal-token", "") == self.internal_token

    async def _inbound(self, req: Request) -> Response:
        if not self._auth_ok(req):
            return Response(status=HTTPStatus.UNAUTHORIZED, text="unauthorized")

        try:
            data = await req.json()
        except Exception:
            return Response(status=HTTPStatus.BAD_REQUEST, text="invalid json")

        request_id = str(data.get("request_id", "")).strip() or f"req_{uuid4().hex}"
        chat_id = str(data.get("chat_id", "")).strip()
        sender_id = str(data.get("sender_id", "")).strip() or "teams-user"
        content = str(data.get("content", "")).strip()
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        channel = str(metadata.get("channel", "teams")).strip() or "teams"

        if not chat_id or not content:
            return Response(status=HTTPStatus.BAD_REQUEST, text="chat_id/content required")

        metadata["request_id"] = request_id
        fut = asyncio.get_running_loop().create_future()
        self._pending[request_id] = fut

        await self.bus.publish_inbound(
            InboundMessage(
                channel=channel,
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
            )
        )

        try:
            response_text = await asyncio.wait_for(fut, timeout=self.inbound_timeout_sec)
            return json_response(
                {"status": "ok", "content": response_text, "request_id": request_id}
            )
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            return json_response({"status": "accepted", "request_id": request_id})
        finally:
            if fut.done():
                self._pending.pop(request_id, None)

    async def _healthz(self, _: Request) -> Response:
        return json_response({"status": "ok"})

    async def _send_proactive(self, *, chat_id: str, content: str, request_id: str = "") -> None:
        if not self.teams_proactive_url:
            return
        headers = {"content-type": "application/json"}
        if self.teams_internal_token:
            headers["x-internal-token"] = self.teams_internal_token
        payload: dict[str, Any] = {"chat_id": chat_id, "content": content}
        if request_id:
            payload["request_id"] = request_id
        try:
            r = await self._http.post(self.teams_proactive_url, json=payload, headers=headers)
            r.raise_for_status()
        except Exception as e:
            logger.error("Failed to send proactive to Teams backend: {}", e)

    async def _outbound_loop(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            meta = msg.metadata or {}
            if meta.get("_progress"):
                continue

            request_id = str(meta.get("request_id", "")).strip()
            if request_id and request_id in self._pending:
                fut = self._pending[request_id]
                if not fut.done():
                    fut.set_result(msg.content)
                continue

            if msg.channel == "teams":
                await self._send_proactive(
                    chat_id=msg.chat_id,
                    content=msg.content,
                    request_id=request_id,
                )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        await self.cron.start()
        await self.heartbeat.start()
        self._agent_task = asyncio.create_task(self.agent.run())
        self._outbound_task = asyncio.create_task(self._outbound_loop())

        app = web.Application()
        app.router.add_post("/internal/inbound", self._inbound)
        app.router.add_get("/healthz", self._healthz)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await self._site.start()
        logger.info("Teams inbound relay listening on http://{}:{}", self.host, self.port)

    async def stop(self) -> None:
        self._running = False

        self.heartbeat.stop()
        self.cron.stop()
        self.agent.stop()

        tasks = [t for t in (self._outbound_task, self._agent_task) if t]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await self.agent.close_mcp()
        await self._http.aclose()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
