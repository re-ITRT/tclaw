"""WebSearchTool —— 联网搜索工具（基于 Kimi $web_search）。"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from openai import OpenAI

from ...common.tool import Tool

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


KIMI_API_KEY = "sk-haGwDupYEuN1kDPGE4CcNdSQCLH2F54ppxfjqPwi2beLIhol"
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = "kimi-k2.6"


class WebSearchTool(Tool):
    tool_id = "web_search"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
        },
        "required": ["query"],
    }

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._kimi = OpenAI(
            base_url=KIMI_BASE_URL,
            api_key=KIMI_API_KEY,
        )

    async def do_execute(self, payload: dict) -> None:
        query = payload.get("query", "")
        sid = payload.get("session_id", "")

        if not query:
            await self.reply_to_llm({"status": "error", "error": "query required"}, sid)
            return

        try:
            result = await self._search_kimi(query)
            await self.reply_to_llm(result, sid)
        except Exception as e:
            await self.reply_to_llm({
                "status": "error", "query": query, "error": str(e),
            }, sid)

    async def _search_kimi(self, query: str) -> dict:
        """通过 Kimi $web_search 执行搜索。"""
        import asyncio

        messages = [
            {"role": "system", "content": "你是搜索助手。根据搜索结果返回摘要。"},
            {"role": "user", "content": query},
        ]

        def _do_search():
            client = self._kimi
            resp = client.chat.completions.create(
                model=KIMI_MODEL,
                messages=messages,
                max_tokens=8192,
                tools=[
                    {
                        "type": "builtin_function",
                        "function": {"name": "$web_search"},
                    }
                ],
                extra_body={"thinking": {"type": "disabled"}},
            )
            choice = resp.choices[0]

            if choice.finish_reason == "tool_calls":
                # Kimi 要求回传 arguments 以触发搜索
                tc = choice.message.tool_calls[0]
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": "$web_search",
                    "content": tc.function.arguments,
                }
                messages.append({
                    "role": "assistant",
                    "content": choice.message.content or "",
                    "tool_calls": [tc],
                })
                messages.append(tool_msg)

                # 第二次请求：Kimi 执行搜索并返回结果
                resp2 = client.chat.completions.create(
                    model=KIMI_MODEL,
                    messages=messages,
                    max_tokens=8192,
                    tools=[
                        {
                            "type": "builtin_function",
                            "function": {"name": "$web_search"},
                        }
                    ],
                    extra_body={"thinking": {"type": "disabled"}},
                )
                choice2 = resp2.choices[0]
                text = choice2.message.content or ""
            else:
                text = choice.message.content or ""

            if not text:
                return {"status": "ok", "query": query, "results": [], "text": "未找到结果"}

            return {
                "status": "ok",
                "query": query,
                "results": [],
                "text": text,
            }

        return await asyncio.to_thread(_do_search)
