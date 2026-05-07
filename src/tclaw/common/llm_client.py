"""LLMClient —— 语言模型客户端。

调用真实 LLM API（OpenAI 兼容接口），支持自动续写截断。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from .settings import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, LLM_MAX_TOKENS

logger = logging.getLogger("tclaw.llm_client")


@dataclass
class LLMResponse:
    """LLM 返回结果。"""
    text: str = ""
    tool_call: dict | None = None


class LLMClient:
    """语言模型客户端。"""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or LLM_MODEL
        self.max_tokens = max_tokens or LLM_MAX_TOKENS
        base_url = base_url or LLM_BASE_URL
        api_key = api_key or LLM_API_KEY

        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """向 LLM 发送对话，自动处理截断续写。"""
        all_text_parts: list[str] = []
        final_tool_call: dict | None = None
        current_msgs = list(messages)

        while True:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": current_msgs,
                "max_tokens": self.max_tokens,
                "stream": False,
            }
            if tools:
                kwargs["tools"] = tools

            try:
                response = await self._client.chat.completions.create(**kwargs)
            except Exception as e:
                logger.error("LLM API call failed: %s", e)
                break

            choice = response.choices[0]
            finish = choice.finish_reason
            msg = choice.message

            # 收集文本
            if msg.content:
                all_text_parts.append(msg.content)

            # 收集 tool_call（取第一个）
            if msg.tool_calls and not final_tool_call:
                tc = msg.tool_calls[0]
                final_tool_call = {
                    "name": tc.function.name,
                    "args": tc.function.arguments,
                }

            # 判断是否需要续写
            if finish == "length":
                # 被截断，追加本轮输出后继续
                current_msgs.append({"role": "assistant", "content": msg.content or ""})
                current_msgs.append({
                    "role": "user",
                    "content": "[请继续，输出还未完成]",
                })
                logger.debug("Truncated at %d tokens, continuing...", self.max_tokens)
                continue

            # 正常结束
            break

        return LLMResponse(
            text="".join(all_text_parts),
            tool_call=final_tool_call,
        )
