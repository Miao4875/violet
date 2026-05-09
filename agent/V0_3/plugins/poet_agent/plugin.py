from __future__ import annotations

from core.interfaces import Agent, AgentFactory, AgentRequest, AgentResult, Message


class PoetAgent(Agent):
    def __init__(
        self,
        context,
        style: str = "classic",
        model: str | None = None,
        temperature: float | None = 0.7,
        max_tokens: int | None = 400,
    ) -> None:
        self.context = context
        self.style = style
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def run(self, request: AgentRequest) -> AgentResult:
        provider = self.context.provider
        if provider is None:
            raise RuntimeError("PoetAgent 需要一个可用的 provider，但当前 runtime 没有配置 provider")

        style_hint = "简洁、含蓄、四行左右" if self.style == "short" else "中文诗歌，四行，意象鲜明，有一点文学感"
        messages = [
            Message(
                role="system",
                content=(
                    "你是一名中文诗歌写作者。"
                    "请直接输出诗歌正文，不要加解释，不要加分析。"
                ),
            ),
            Message(
                role="user",
                content=f"请围绕这个主题写一首诗：{request.task}。风格要求：{style_hint}。",
            ),
        ]
        response = provider.chat(
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        poem = response.content.strip()
        return AgentResult(
            output=poem,
            done=True,
            meta={
                "role": "PoetAgent",
                "style": self.style,
                "source": "poet_agent",
                "depth": 1,
                "provider_meta": response.meta,
            },
        )


class PoetAgentFactory(AgentFactory):
    def create(self, context, **kwargs) -> Agent:
        return PoetAgent(context=context, **kwargs)


def register(registry) -> None:
    registry.register_agent("poet_agent", PoetAgentFactory())
