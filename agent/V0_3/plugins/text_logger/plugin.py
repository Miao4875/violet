from __future__ import annotations

from pathlib import Path

from core.interfaces import Event, LoggerBackend


class TextLogger(LoggerBackend):
    def __init__(self, path: str = "./data/event_log.txt") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def start_session(self, session_id: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(f"session={session_id}\n{{\n")

    def log(self, event: Event) -> None:
        prefix = "\t" * event.depth
        line = (
            f"{prefix}{{type:{event.event_type},action:{event.action},role:{event.role},"
            f"message:{event.message},meta:{event.meta}}}\n"
        )
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line)

    def end_session(self, session_id: str, result: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(f"{{type:session,action:session.result,role:system,message:{result}}}\n")
            file.write("}\n")


def register(registry) -> None:
    registry.register_logger("text_logger", TextLogger)
