"""MemorySearchTool —— 语义搜索记忆索引。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Event, Topics
from ...backend.memory import init_db

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class MemorySearchTool(Tool):
    tool_id = "memory_search"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回条数（默认 5）",
            },
        },
        "required": ["query"],
    }

    async def handle_event(self, event: Event) -> None:
        query = event.payload.get("query", "")
        max_results = event.payload.get("max_results", 5)

        if not query:
            return

        try:
            conn = init_db()
            cursor = conn.execute(
                """
                SELECT c.text, c.path, c.start_line, c.end_line, c.source
                FROM chunks_fts f
                JOIN chunks c ON c.id = f.id
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, max_results),
            )
            rows = cursor.fetchall()
            conn.close()

            results = []
            for row in rows:
                results.append({
                    "path": row["path"],
                    "source": row["source"],
                    "lines": f"{row['start_line']}-{row['end_line']}",
                    "text": row["text"][:500],
                })

            text = "\n---\n".join(
                f"[{r['path']}:{r['lines']}] {r['text']}"
                for r in results
            ) if results else f"No results for: {query}"

        except Exception as e:
            text = f"Memory search error: {e}"

        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={"tool": "memory_search", "status": "done", "text": text},
            source=self.tool_id,
            session_id=event.session_id,
        ))
