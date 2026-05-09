from __future__ import annotations

from core.interfaces import AgentFactory, HistoryBackend, LoggerBackend, ModelProvider


class Registry:
    def __init__(self) -> None:
        self.history_backends: dict[str, type[HistoryBackend]] = {}
        self.logger_backends: dict[str, type[LoggerBackend]] = {}
        self.agent_factories: dict[str, AgentFactory] = {}
        self.providers: dict[str, type[ModelProvider]] = {}

    def register_history(self, name: str, backend_cls: type[HistoryBackend]) -> None:
        if name in self.history_backends:
            raise ValueError(f"history backend '{name}' 已注册")
        self.history_backends[name] = backend_cls

    def register_logger(self, name: str, backend_cls: type[LoggerBackend]) -> None:
        if name in self.logger_backends:
            raise ValueError(f"logger backend '{name}' 已注册")
        self.logger_backends[name] = backend_cls

    def register_agent(self, name: str, factory: AgentFactory) -> None:
        if name in self.agent_factories:
            raise ValueError(f"agent '{name}' 已注册")
        self.agent_factories[name] = factory

    def register_provider(self, name: str, provider_cls: type[ModelProvider]) -> None:
        if name in self.providers:
            raise ValueError(f"provider '{name}' 已注册")
        self.providers[name] = provider_cls

    def get_history(self, name: str) -> type[HistoryBackend]:
        if name not in self.history_backends:
            raise KeyError(f"history backend '{name}' 未注册")
        return self.history_backends[name]

    def get_logger(self, name: str) -> type[LoggerBackend]:
        if name not in self.logger_backends:
            raise KeyError(f"logger backend '{name}' 未注册")
        return self.logger_backends[name]

    def get_agent(self, name: str) -> AgentFactory:
        if name not in self.agent_factories:
            raise KeyError(f"agent '{name}' 未注册")
        return self.agent_factories[name]

    def get_provider(self, name: str) -> type[ModelProvider]:
        if name not in self.providers:
            raise KeyError(f"provider '{name}' 未注册")
        return self.providers[name]
