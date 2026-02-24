"""Azure Bot Framework relay backend for Teams <-> nanobot."""

from __future__ import annotations

import sys
import traceback
import uuid
from datetime import datetime
from http import HTTPStatus

from aiohttp import web
from aiohttp.web import Request, Response, json_response
from botbuilder.core import TurnContext
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp import (
    CloudAdapter,
    ConfigurationBotFrameworkAuthentication,
)
from botbuilder.schema import Activity, ActivityTypes

from bots import RelayBot
from config import Settings
from nanobot_client import NanobotClient
from reference_store import ConversationReferenceStore

SETTINGS = Settings.from_env()
STORE = ConversationReferenceStore(SETTINGS.reference_store_path)
NANOBOT = NanobotClient(
    inbound_url=SETTINGS.nanobot_inbound_url,
    timeout_sec=SETTINGS.nanobot_timeout_sec,
    token=SETTINGS.internal_token,
)

ADAPTER = CloudAdapter(ConfigurationBotFrameworkAuthentication(SETTINGS))
APP_ID = SETTINGS.app_id if SETTINGS.app_id else uuid.uuid4()
BOT = RelayBot(STORE, NANOBOT)


async def on_error(context: TurnContext, error: Exception):
    print(f"\n[on_turn_error] {error}", file=sys.stderr)
    traceback.print_exc()
    await context.send_activity("The bot encountered an error.")
    if context.activity.channel_id == "emulator":
        await context.send_activity(
            Activity(
                label="TurnError",
                name="on_turn_error Trace",
                timestamp=datetime.utcnow(),
                type=ActivityTypes.trace,
                value=f"{error}",
                value_type="https://www.botframework.com/schemas/error",
            )
        )


ADAPTER.on_turn_error = on_error


def _internal_auth_ok(req: Request) -> bool:
    if not SETTINGS.internal_token:
        return True
    return req.headers.get("x-internal-token", "") == SETTINGS.internal_token


async def messages(req: Request) -> Response:
    ts = datetime.utcnow().isoformat() + "Z"
    forwarded_for = req.headers.get("x-forwarded-for", "")
    remote = forwarded_for.split(",")[0].strip() if forwarded_for else (req.remote or "")
    print(f"[{ts}] POST /api/messages from={remote} ua={req.headers.get('user-agent', '-')}")
    return await ADAPTER.process(req, BOT)


async def messages_get(_: Request) -> Response:
    return Response(
        status=HTTPStatus.OK,
        text=(
            "This endpoint only accepts POST from Bot Framework channels.\n"
            "Use GET /healthz for health checks."
        ),
        content_type="text/plain",
    )


async def proactive(req: Request) -> Response:
    if not _internal_auth_ok(req):
        return Response(status=HTTPStatus.UNAUTHORIZED, text="unauthorized")

    data = await req.json()
    chat_id = str(data.get("chat_id", "")).strip()
    content = str(data.get("content", "")).strip()
    if not chat_id or not content:
        return Response(status=HTTPStatus.BAD_REQUEST, text="chat_id/content required")

    reference = await STORE.get(chat_id)
    if not reference:
        return Response(status=HTTPStatus.NOT_FOUND, text="conversation reference not found")

    async def callback(turn_context: TurnContext):
        await turn_context.send_activity(content)

    await ADAPTER.continue_conversation(reference, callback, APP_ID)
    return json_response({"status": "ok", "chat_id": chat_id})


async def healthz(_: Request) -> Response:
    return json_response({"status": "ok"})


async def on_cleanup(_: web.Application):
    await NANOBOT.close()


APP = web.Application(middlewares=[aiohttp_error_middleware])
APP.router.add_post("/api/messages", messages)
APP.router.add_get("/api/messages", messages_get)
APP.router.add_post("/internal/proactive", proactive)
APP.router.add_get("/healthz", healthz)
APP.on_cleanup.append(on_cleanup)


if __name__ == "__main__":
    web.run_app(APP, host="0.0.0.0", port=SETTINGS.port)
