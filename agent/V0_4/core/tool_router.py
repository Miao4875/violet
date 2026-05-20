from __future__ import annotations

import json
from typing import Any

from core.interfaces import Agent, AgentRequest, AgentResult, Message


class CoreToolRouterAgent(Agent):
    def __init__(
        self,
        context,
        *,
        tools: dict[str, dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = 0.0,
        max_tokens: int | None = 300,
        fallback_message: str = "NO_TOOL_MATCHED",
    ) -> None:
        self.context = context
        self.tools = tools or {}
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.fallback_message = fallback_message

    def run(self, request: AgentRequest) -> AgentResult:
        selection = self._select_tool(request.task)
        if not selection:
            return AgentResult(
                output=self.fallback_message,
                done=True,
                meta={
                    "role": "CoreToolRouterAgent",
                    "source": "core.tool_router",
                    "route": "fallback",
                },
            )

        tool_name, tool_config = selection
        tool = self._build_tool(tool_name, tool_config)
        result = tool.run(request)
        result.meta.setdefault("role", "CoreToolRouterAgent")
        result.meta["source"] = "core.tool_router"
        result.meta["selected_tool"] = tool_name
        return result

    def _select_tool(self, task: str) -> tuple[str, dict[str, Any]] | None:
        heuristic_choice = self._select_tool_without_model(task)
        provider = self.context.provider
        if provider is None:
            return heuristic_choice

        tool_descriptions = []
        for tool_name in self.context.registry.list_tools():
            config = self.tools.get(tool_name, {})
            tool_descriptions.append(
                {
                    "name": tool_name,
                    "description": config.get("description", ""),
                }
            )

        response = provider.chat(
            [
                Message(
                    role="system",
                    content=(
                        "You are the core routing agent. "
                        "Choose exactly one tool from the provided tool list. "
                        "If no tool fits, return none. "
                        'Return JSON only, for example {"tool":"bilibili_command_tool","reason":"..."} '
                        'or {"tool":"none","reason":"..."}.'
                    ),
                ),
                Message(
                    role="user",
                    content=json.dumps({"task": task, "tools": tool_descriptions}, ensure_ascii=False),
                ),
            ],
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        parsed = self._parse_router_output(response.content)
        tool_name = str(parsed.get("tool", "")).strip()
        if not tool_name or tool_name == "none":
            return heuristic_choice
        if tool_name not in self.context.registry.list_tools():
            return heuristic_choice
        return tool_name, self.tools.get(tool_name, {})

    def _select_tool_without_model(self, task: str) -> tuple[str, dict[str, Any]] | None:
        normalized = task.lower()
        bilibili_tool = self._pick_registered_tool("bilibili_command_tool", "bilibili_opencli")
        if bilibili_tool and (
            "bilibili.com" in normalized
            or "b23.tv" in normalized
            or "bilibili" in normalized
            or "b站" in task
            or "哔哩哔哩" in task
        ):
            return bilibili_tool, self.tools.get(bilibili_tool, {})
        return None

    def _pick_registered_tool(self, *names: str) -> str | None:
        available = set(self.context.registry.list_tools())
        for name in names:
            if name in available:
                return name
        return None

    def _parse_router_output(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}

    def _build_tool(self, tool_name: str, tool_config: dict[str, Any]):
        factory = self.context.registry.get_tool(tool_name)
        config = {key: value for key, value in tool_config.items() if key != "description"}
        return factory.create(self.context, **config)
