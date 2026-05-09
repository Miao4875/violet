from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from core.context import RuntimeContext
from core.events import EventBus, event_to_history_record, is_dialogue_event
from core.interfaces import AgentRequest, Event, Message
from core.registry import Registry


class Runtime:
    def __init__(self, registry: Registry, base_dir: str | Path) -> None:
        self.registry = registry
        self.base_dir = Path(base_dir)

    def run(self, task: str, config_path: str | Path) -> str:
        config = self._load_config(config_path)
        session_id = self._build_session_id(config.get("runtime", {}))

        history = self._build_history(config["history"])
        logger = self._build_logger(config["logger"])
        provider = self._build_provider(config.get("provider"))
        agent = self._build_agent(config["agent"], config, session_id, provider)

        event_bus = EventBus()
        event_bus.subscribe(logger.log)
        event_bus.subscribe(lambda event: self._write_history(history, event))

        logger.start_session(session_id)
        event_bus.emit(
            Event(
                session_id=session_id,
                event_type="session",
                action="session.start",
                role="system",
            )
        )
        event_bus.emit(
            Event(
                session_id=session_id,
                event_type="message",
                action="message.user",
                role="user",
                message=task,
                meta={"history_role": "user"},
            )
        )
        event_bus.emit(
            Event(
                session_id=session_id,
                event_type="agent",
                action="agent.start",
                role=agent.__class__.__name__,
                meta={"task": task},
            )
        )

        request = AgentRequest(
            session_id=session_id,
            task=task,
            messages=[Message(role="user", content=task)],
        )
        result = agent.run(request)

        result_meta = dict(result.meta)
        role = str(result_meta.pop("role", agent.__class__.__name__))
        depth = int(result_meta.pop("depth", 1))
        event_bus.emit(
            Event(
                session_id=session_id,
                event_type="message",
                action="message.agent",
                role=role,
                message=result.output,
                depth=depth,
                meta={
                    **result_meta,
                    "history_role": "agent",
                },
            )
        )
        event_bus.emit(
            Event(
                session_id=session_id,
                event_type="agent",
                action="agent.finish",
                role=role,
                meta={"done": result.done},
            )
        )
        event_bus.emit(
            Event(
                session_id=session_id,
                event_type="session",
                action="session.finish",
                role="system",
                meta={"done": result.done},
            )
        )

        logger.end_session(session_id, result.output)
        return result.output

    def _load_config(self, config_path: str | Path) -> dict[str, Any]:
        path = Path(config_path)
        if not path.is_absolute():
            path = self.base_dir / path
        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def _build_history(self, section: dict[str, Any]):
        backend_cls = self.registry.get_history(section["name"])
        return backend_cls(**self._resolve_plugin_config(section.get("config", {})))

    def _build_logger(self, section: dict[str, Any]):
        backend_cls = self.registry.get_logger(section["name"])
        return backend_cls(**self._resolve_plugin_config(section.get("config", {})))

    def _build_agent(self, section: dict[str, Any], config: dict[str, Any], session_id: str, provider):
        factory = self.registry.get_agent(section["name"])
        context = RuntimeContext(
            session_id=session_id,
            base_dir=self.base_dir,
            config=config,
            provider=provider,
        )
        return factory.create(context, **section.get("config", {}))

    def _build_provider(self, section: dict[str, Any] | None):
        if not section:
            return None
        provider_cls = self.registry.get_provider(section["name"])
        return provider_cls(**self._resolve_plugin_config(section.get("config", {})))

    def _build_session_id(self, runtime_config: dict[str, Any]) -> str:
        prefix = runtime_config.get("session_prefix", "session")
        return f"{prefix}-{uuid4().hex[:8]}"

    def _resolve_plugin_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, value in raw_config.items():
            if isinstance(value, str) and (key.endswith("path") or key.endswith("dir") or key == "path"):
                path = Path(value)
                if not path.is_absolute():
                    path = (self.base_dir / path).resolve()
                resolved[key] = str(path)
            else:
                resolved[key] = value
        return resolved

    def _write_history(self, history, event: Event) -> None:
        if is_dialogue_event(event):
            history.append(event_to_history_record(event))
