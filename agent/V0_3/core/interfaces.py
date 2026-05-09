from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoryRecord:
    session_id: str
    message: Message


@dataclass
class AgentRequest:
    session_id: str
    task: str
    messages: list[Message] = field(default_factory=list)


@dataclass
class AgentResult:
    output: str
    done: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    content: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    session_id: str
    event_type: str
    action: str
    role: str = "system"
    message: str | None = None
    depth: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


class HistoryBackend(ABC):
    @abstractmethod
    def append(self, record: HistoryRecord) -> None: ...

    @abstractmethod
    def load(self, session_id: str, limit: int | None = None) -> list[HistoryRecord]: ...

    @abstractmethod
    def clear(self, session_id: str) -> None: ...


class LoggerBackend(ABC):
    @abstractmethod
    def start_session(self, session_id: str) -> None: ...

    @abstractmethod
    def log(self, event: Event) -> None: ...

    @abstractmethod
    def end_session(self, session_id: str, result: str) -> None: ...


class Agent(ABC):
    @abstractmethod
    def run(self, request: AgentRequest) -> AgentResult: ...


class AgentFactory(ABC):
    @abstractmethod
    def create(self, context: Any, **kwargs: Any) -> Agent: ...


class ModelProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse: ...
