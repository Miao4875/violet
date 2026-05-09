from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.interfaces import ModelProvider


@dataclass
class RuntimeContext:
    session_id: str
    base_dir: Path
    config: dict[str, Any] = field(default_factory=dict)
    provider: ModelProvider | None = None
