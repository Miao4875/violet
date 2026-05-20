from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class JobRecord:
    job_id: str
    parent_session_id: str
    worker_name: str
    task: str
    status: str
    started_at: str
    cache_dir: str
    meta: dict = field(default_factory=dict)


class JobRegistry:
    def __init__(
        self,
        path: str,
        cache_root: str,
        history_path: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.history_path = Path(history_path) if history_path else self.path.with_name("job_history.jsonl")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_state({})

    def open_job(self, parent_session_id: str, worker_name: str, task: str, meta: dict | None = None) -> JobRecord:
        job_id = f"job-{uuid4().hex[:10]}"
        cache_dir = self.cache_root / job_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        record = JobRecord(
            job_id=job_id,
            parent_session_id=parent_session_id,
            worker_name=worker_name,
            task=task,
            status="running",
            started_at=self._now(),
            cache_dir=str(cache_dir),
            meta=meta or {},
        )
        state = self._read_state()
        state[job_id] = asdict(record)
        self._write_state(state)
        return record

    def finish_job(self, job_id: str, meta: dict | None = None) -> None:
        self._finalize_job(job_id=job_id, status="completed", meta=meta or {})

    def fail_job(self, job_id: str, error_message: str, meta: dict | None = None) -> None:
        payload = dict(meta or {})
        payload["error"] = error_message
        self._finalize_job(job_id=job_id, status="failed", meta=payload)

    def _finalize_job(self, job_id: str, status: str, meta: dict) -> None:
        state = self._read_state()
        record = state.pop(job_id, None)
        if record is None:
            return
        record["status"] = status
        record["finished_at"] = self._now()
        record_meta = dict(record.get("meta", {}))
        record_meta.update(meta)
        record["meta"] = record_meta
        self._write_state(state)
        with self.history_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._cleanup_cache(record.get("cache_dir", ""))

    def _cleanup_cache(self, cache_dir: str) -> None:
        if not cache_dir:
            return
        path = Path(cache_dir)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _read_state(self) -> dict:
        if not self.path.exists():
            return {}
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        return json.loads(raw)

    def _write_state(self, state: dict) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


TaskRegistry = JobRegistry
