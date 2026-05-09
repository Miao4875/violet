from __future__ import annotations

from typing import Callable

from core.interfaces import Event, HistoryRecord, Message

EventHandler = Callable[[Event], None]

DIALOGUE_ACTIONS = {"message.user", "message.agent"}


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def emit(self, event: Event) -> None:
        for handler in list(self._handlers):
            handler(event)


def is_dialogue_event(event: Event) -> bool:
    return event.action in DIALOGUE_ACTIONS and event.message is not None


def event_to_history_record(event: Event) -> HistoryRecord:
    meta = dict(event.meta)
    history_role = str(meta.pop("history_role", event.role))
    return HistoryRecord(
        session_id=event.session_id,
        message=Message(
            role=history_role,
            content=event.message or "",
            meta=meta,
        ),
    )
