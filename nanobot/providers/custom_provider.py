"""Direct OpenAI-compatible provider — bypasses LiteLLM."""

from __future__ import annotations

from typing import Any

import json_repair
from openai import AsyncOpenAI

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class CustomProvider(LLMProvider):

    def __init__(
        self,
        api_key: str = "no-key",
        api_base: str = "",
        default_model: str = "default",
        azure_endpoint: str | None = None,
        api_version: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.azure_endpoint = azure_endpoint
        self.api_version = api_version
        self._is_azure = bool(self.azure_endpoint or self.api_version)
        self._client = self._build_client(api_key, api_base)

    def _build_client(self, api_key: str, api_base: str):
        if not self._is_azure:
            return AsyncOpenAI(api_key=api_key, base_url=api_base)

        if not self.api_version:
            raise ValueError("custom provider with Azure requires providers.custom.apiVersion")

        try:
            from openai import AsyncAzureOpenAI
        except ImportError as e:
            raise ImportError(
                "AsyncAzureOpenAI is not available. Please upgrade the `openai` package."
            ) from e

        azure_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "api_version": self.api_version,
        }
        if self.azure_endpoint:
            azure_kwargs["azure_endpoint"] = self.azure_endpoint
        elif api_base:
            azure_kwargs["base_url"] = api_base
        else:
            raise ValueError(
                "custom provider with Azure requires providers.custom.azureEndpoint or apiBase"
            )
        return AsyncAzureOpenAI(**azure_kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")
        try:
            return self._parse(await self._client.chat.completions.create(**kwargs))
        except Exception as e:
            return LLMResponse(content=f"Error: {e}", finish_reason="error")

    def _parse(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        tool_calls = [
            ToolCallRequest(
                id=tc.id,
                name=tc.function.name,
                arguments=(
                    json_repair.loads(tc.function.arguments)
                    if isinstance(tc.function.arguments, str)
                    else tc.function.arguments
                ),
            )
            for tc in (msg.tool_calls or [])
        ]
        u = response.usage
        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.total_tokens,
            }
            if u
            else {},
            reasoning_content=getattr(msg, "reasoning_content", None),
        )

    def get_default_model(self) -> str:
        return self.default_model
