from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.interfaces import ModelProvider


@dataclass
class KernelContext:
    session_id: str
    base_dir: Path
    config: dict[str, Any] = field(default_factory=dict)
    provider: ModelProvider | None = None
    registry: Any = None
    job_registry: Any = None


RuntimeContext = KernelContext
