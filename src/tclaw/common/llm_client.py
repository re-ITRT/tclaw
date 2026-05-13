"""LLMClient —— 语言模型客户端。

调用真实 LLM API（OpenAI 兼容接口），支持自动续写截断。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from .settings import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, LLM_MAX_TOKENS

logger = logging.getLogger("tclaw.llm_client")


@dataclass
class LLMResponse:
    """LLM 返回结果。"""
    text: str = ""
    tool_call: dict | None = None  # 第一个 tool_call（兼容）
    tool_calls: list[dict] = field(default_factory=list)  # 所有 tool_call
    tool_call_id: str = ""
    # 完整 assistant 消息（含 tool_calls），供上下文历史用
    assistant_message: dict | None = None


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
        final_tool_calls: list[dict] = []
        final_tool_call_id: str = ""
        final_assistant_msg: dict | None = None
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
                logger.debug("LLM request: %d msgs, tools=%s, last_role=%s",
                             len(current_msgs), bool(tools),
                             current_msgs[-1].get("role", "?") if current_msgs else "?")
                if current_msgs:
                    last = current_msgs[-1]
                    if last.get("role") == "tool":
                        logger.debug("  tool_call_id=%s", last.get("tool_call_id", "(missing)"))
                response = await self._client.chat.completions.create(**kwargs)
            except Exception as e:
                logger.error("LLM API call failed: %s", e)
                break

            choice = response.choices[0]
            finish = choice.finish_reason
            msg = choice.message

            if msg.tool_calls:
                logger.debug("  LLM response: %d tool_calls, first id=%s, finish=%s",
                             len(msg.tool_calls), msg.tool_calls[0].id, finish)
            else:
                logger.debug("  LLM response: text (%d chars), finish=%s",
                             len(msg.content or ""), finish)

            # 收集文本
            if msg.content:
                all_text_parts.append(msg.content)

            # 收集 tool_calls（所有）
            if msg.tool_calls and not final_tool_calls:
                final_tool_call_id = msg.tool_calls[0].id
                final_tool_call = {
                    "name": msg.tool_calls[0].function.name,
                    "args": msg.tool_calls[0].function.arguments,
                }
                final_tool_calls = [
                    {"name": tc.function.name, "args": tc.function.arguments, "id": tc.id}
                    for tc in msg.tool_calls
                ]
                # 完整的 assistant 消息（含所有 tool_calls）
                final_assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                # DeepSeek reasoning 模型要求回传 reasoning_content
                reasoning = getattr(msg, "reasoning_content", None)
                if reasoning:
                    final_assistant_msg["reasoning_content"] = reasoning

            # 判断是否需要续写
            if finish == "length":
                current_msgs.append({"role": "assistant", "content": msg.content or ""})
                current_msgs.append({
                    "role": "user",
                    "content": "[请继续，输出还未完成]",
                })
                logger.debug("Truncated at %d tokens, continuing...", self.max_tokens)
                continue

            # 正常结束
            break

        # 纯文本回复且无 assistant_message 时（无 tool_call），也构建一个
        if not final_assistant_msg:
            text_content = "".join(all_text_parts)
            final_assistant_msg = {"role": "assistant", "content": text_content}
            # reasoning 模型也可能在纯文本回复时带 reasoning_content
            if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                final_assistant_msg["reasoning_content"] = msg.reasoning_content

        return LLMResponse(
            text="".join(all_text_parts),
            tool_call=final_tool_call,
            tool_calls=final_tool_calls,
            tool_call_id=final_tool_call_id,
            assistant_message=final_assistant_msg,
        )
