from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from core.context import KernelContext
from core.events import EventBus, event_to_history_record, is_dialogue_event
from core.interfaces import AgentRequest, Event, Message
from core.registry import Registry
from core.task_registry import JobRegistry
from core.tool_router import CoreToolRouterAgent


class KernelRuntime:
    def __init__(self, registry: Registry, base_dir: str | Path) -> None:
        self.registry = registry
        self.base_dir = Path(base_dir)

    def run(self, task: str, config_path: str | Path) -> str:
        config = self._load_config(config_path)
        session_id = self._build_session_id(config.get("runtime", {}))

        history = self._build_history(config["history"])
        logger = self._build_logger(config["logger"])
        provider = self._build_provider(config.get("provider"))
        job_registry = self._build_job_registry(config.get("runtime", {}))
        context = self._build_context(config, session_id, provider, job_registry)
        agent = self._build_router(context)

        event_bus = EventBus()
        event_bus.subscribe(logger.log)
        event_bus.subscribe(lambda event: self._write_history(history, event))

        logger.start_session(session_id)
        event_bus.emit(Event(session_id=session_id, event_type="session", action="session.start", role="system"))
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

        request = AgentRequest(session_id=session_id, task=task, messages=[Message(role="user", content=task)])
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
                meta={**result_meta, "history_role": "agent"},
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

    def _build_context(self, config: dict[str, Any], session_id: str, provider, job_registry) -> KernelContext:
        return KernelContext(
            session_id=session_id,
            base_dir=self.base_dir,
            config=config,
            provider=provider,
            registry=self.registry,
            job_registry=job_registry,
        )

    def _build_router(self, context: KernelContext) -> CoreToolRouterAgent:
        router_config = self._resolve_plugin_config(context.config.get("router", {}))
        tools = self._resolve_tool_configs(context.config.get("tools", {}))
        return CoreToolRouterAgent(context=context, tools=tools, **router_config)

    def _resolve_tool_configs(self, raw_tools: dict[str, Any]) -> dict[str, dict[str, Any]]:
        resolved: dict[str, dict[str, Any]] = {}
        for tool_name, config in raw_tools.items():
            if isinstance(config, dict):
                resolved[tool_name] = self._resolve_plugin_config(config)
        return resolved

    def _build_provider(self, section: dict[str, Any] | None):
        if not section:
            return None
        provider_cls = self.registry.get_provider(section["name"])
        return provider_cls(**self._resolve_plugin_config(section.get("config", {})))

    def _build_job_registry(self, runtime_config: dict[str, Any]) -> JobRegistry:
        registry_config = runtime_config.get("job_registry") or runtime_config.get("task_registry", {})
        path = registry_config.get("path", "./data/job_registry.json")
        cache_dir = registry_config.get("cache_dir", "./data/job_cache")
        history_path = registry_config.get("history_path", "./data/job_history.jsonl")
        resolved = self._resolve_plugin_config({"path": path, "cache_dir": cache_dir, "history_path": history_path})
        return JobRegistry(path=resolved["path"], cache_root=resolved["cache_dir"], history_path=resolved["history_path"])

    def _build_session_id(self, runtime_config: dict[str, Any]) -> str:
        prefix = runtime_config.get("session_prefix", "session")
        return f"{prefix}-{uuid4().hex[:8]}"

    def _resolve_plugin_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        return {key: self._resolve_value(key, value) for key, value in raw_config.items()}

    def _resolve_value(self, key: str, value: Any) -> Any:
        if isinstance(value, dict):
            return {child_key: self._resolve_value(child_key, child_value) for child_key, child_value in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(key, item) for item in value]
        if isinstance(value, str) and (key.endswith("path") or key.endswith("dir") or key == "path"):
            path = Path(value)
            if not path.is_absolute():
                path = (self.base_dir / path).resolve()
            return str(path)
        return value

    def _write_history(self, history, event: Event) -> None:
        if is_dialogue_event(event):
            history.append(event_to_history_record(event))


Runtime = KernelRuntime
