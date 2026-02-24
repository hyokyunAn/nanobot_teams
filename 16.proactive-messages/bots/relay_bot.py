"""Bot that relays Teams user messages to nanobot."""

from __future__ import annotations

from botbuilder.core import ActivityHandler, TurnContext

from nanobot_client import NanobotClient
from reference_store import ConversationReferenceStore


def build_chat_id(activity) -> str:
    tenant_id = ""
    if activity.conversation and activity.conversation.tenant_id:
        tenant_id = activity.conversation.tenant_id
    elif isinstance(activity.channel_data, dict):
        tenant_id = (
            activity.channel_data.get("tenant", {}).get("id", "")
            if isinstance(activity.channel_data.get("tenant"), dict)
            else ""
        )

    conversation_id = activity.conversation.id if activity.conversation else ""
    user_id = activity.from_property.id if activity.from_property else ""
    return f"{tenant_id}|{conversation_id}|{user_id}"


def build_sender_id(activity) -> str:
    user_id = activity.from_property.id if activity.from_property else ""
    aad_id = getattr(activity.from_property, "aad_object_id", "") or ""
    return f"{user_id}|{aad_id}" if aad_id else user_id


class RelayBot(ActivityHandler):
    def __init__(self, store: ConversationReferenceStore, nanobot: NanobotClient):
        self.store = store
        self.nanobot = nanobot

    async def on_conversation_update_activity(self, turn_context: TurnContext):
        await self._remember_reference(turn_context)
        return await super().on_conversation_update_activity(turn_context)

    async def on_message_activity(self, turn_context: TurnContext):
        await self._remember_reference(turn_context)
        activity = turn_context.activity
        chat_id = build_chat_id(activity)

        result = await self.nanobot.ask(
            chat_id=chat_id,
            sender_id=build_sender_id(activity),
            content=activity.text or "",
            metadata={
                "channel": "teams",
                "message_id": activity.id,
                "tenant_id": chat_id.split("|", 1)[0],
            },
        )

        if result.status == "ok":
            await turn_context.send_activity(result.content or "(empty response)")
            return
        if result.status == "accepted":
            await turn_context.send_activity("요청을 접수했습니다. 완료되면 알려드릴게요.")
            return

        await turn_context.send_activity(
            f"nanobot 연결 오류가 발생했습니다. request_id={result.request_id}"
        )

    async def _remember_reference(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        chat_id = build_chat_id(activity)
        if not chat_id or chat_id.count("|") < 2:
            return
        reference = TurnContext.get_conversation_reference(activity)
        await self.store.upsert(chat_id, reference)

