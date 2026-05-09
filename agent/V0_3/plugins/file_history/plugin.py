from __future__ import annotations

import json
from pathlib import Path

from core.interfaces import HistoryBackend, HistoryRecord, Message


class FileHistory(HistoryBackend):
    def __init__(self, path: str = "./data/chat_history.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, record: HistoryRecord) -> None:
        row = {
            "session_id": record.session_id,
            "role": record.message.role,
            "content": record.message.content,
            "meta": record.message.meta,
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    def load(self, session_id: str, limit: int | None = None) -> list[HistoryRecord]:
        records: list[HistoryRecord] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if item["session_id"] != session_id:
                    continue
                records.append(
                    HistoryRecord(
                        session_id=item["session_id"],
                        message=Message(
                            role=item["role"],
                            content=item["content"],
                            meta=item.get("meta", {}),
                        ),
                    )
                )

        if limit is not None:
            return records[-limit:]
        return records

    def clear(self, session_id: str) -> None:
        kept_lines: list[str] = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if item["session_id"] != session_id:
                    kept_lines.append(line)

        with self.path.open("w", encoding="utf-8") as file:
            for line in kept_lines:
                file.write(line + "\n")


def register(registry) -> None:
    registry.register_history("file_history", FileHistory)
