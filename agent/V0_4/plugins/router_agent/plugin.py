from __future__ import annotations

import json
import re
from typing import Any

from core.interfaces import Agent, AgentFactory, AgentRequest, AgentResult, Message

BILIBILI_KEYWORDS = ("b站", "bilibili", "哔哩哔哩", "b 站")
HOT_KEYWORDS = ("最新", "热门", "热榜", "热搜", "推荐", "看看")


class IntentRouterAgent(Agent):
    def __init__(
        self,
        context,
        tools: dict[str, dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = 0.0,
        max_tokens: int | None = 300,
        fallback_message: str = "当前没有匹配到可执行工具。",
    ) -> None:
        self.context = context
        self.tools = tools or {}
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.fallback_message = fallback_message

    def run(self, request: AgentRequest) -> AgentResult:
        selected_tool = self._select_tool(request.task)
        if not selected_tool:
            return AgentResult(
                output=self.fallback_message,
                done=True,
                meta={
                    "role": "RouterAgent",
                    "source": "router_agent",
                    "route": "fallback",
                },
            )

        tool_name, tool_config = selected_tool
        tool = self._build_tool(tool_name, tool_config)
        result = tool.run(request)
        result.meta.setdefault("role", "RouterAgent")
        result.meta["source"] = "router_agent"
        result.meta["selected_tool"] = tool_name
        return result

    def _select_tool(self, task: str) -> tuple[str, dict[str, Any]] | None:
        provider = self.context.provider
        heuristic_choice = self._select_tool_without_model(task)
        if provider is None:
            return heuristic_choice

        tool_descriptions = []
        for tool_name, tool_config in self.tools.items():
            description = tool_config.get("description", "")
            tool_descriptions.append({"name": tool_name, "description": description})

        system_prompt = (
            "你是一个工具路由器。"
            "你只能从给定工具中选择一个最合适的工具。"
            "如果没有任何工具适合，就返回 none。"
            "请只返回 JSON，例如 "
            '{"tool":"bilibili_opencli","reason":"检测到B站任务"} '
            '或 {"tool":"none","reason":"..."}。'
        )
        user_prompt = json.dumps(
            {
                "task": task,
                "tools": tool_descriptions,
            },
            ensure_ascii=False,
        )
        response = provider.chat(
            [
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ],
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        parsed = self._parse_router_output(response.content)
        tool_name = parsed.get("tool", "")
        if not tool_name or tool_name == "none":
            return heuristic_choice
        if tool_name not in self.tools:
            return heuristic_choice
        return tool_name, self.tools[tool_name]

    def _select_tool_without_model(self, task: str) -> tuple[str, dict[str, Any]] | None:
        normalized = task.lower()
        if "bilibili.com" in normalized or "b23.tv" in normalized:
            return self._match_tool("bilibili_opencli")
        if any(keyword in normalized for keyword in ("bilibili", "b站")):
            return self._match_tool("bilibili_opencli")
        if any(keyword in task for keyword in BILIBILI_KEYWORDS) and any(keyword in task for keyword in HOT_KEYWORDS):
            return self._match_tool("bilibili_opencli")
        if re.search(r"(视频|热榜|热门|最新)", task) and any(keyword in task for keyword in BILIBILI_KEYWORDS):
            return self._match_tool("bilibili_opencli")
        return None

    def _match_tool(self, tool_name: str) -> tuple[str, dict[str, Any]] | None:
        tool_config = self.tools.get(tool_name)
        if not tool_config:
            return None
        return tool_name, tool_config

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


class RouterAgentFactory(AgentFactory):
    def create(self, context, **kwargs) -> Agent:
        return IntentRouterAgent(context=context, **kwargs)


def register(registry) -> None:
    factory = RouterAgentFactory()
    registry.register_agent("intent_router_agent", factory)
    registry.register_agent("router_agent", factory)
