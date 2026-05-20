from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from core.registry import Registry


class PluginManager:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def load_all(self, plugins_dir: str | Path) -> None:
        base = Path(plugins_dir)
        if not base.exists() or not base.is_dir():
            raise FileNotFoundError(f"plugins directory does not exist: {plugins_dir}")

        for plugin_dir in base.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest_path = plugin_dir / "plugin.json"
            if not manifest_path.exists():
                continue

            manifest = self._read_manifest(manifest_path)
            entry_name = manifest.get("entry", "register.py")
            entry_path = plugin_dir / entry_name
            if not entry_path.exists():
                raise FileNotFoundError(f"plugin '{plugin_dir.name}' is missing entry file: {entry_name}")

            module = self._load_module(plugin_dir.name, entry_path)
            if not hasattr(module, "register"):
                raise AttributeError(f"plugin '{plugin_dir.name}' is missing register(registry)")
            module.register(self.registry)

    def _read_manifest(self, manifest_path: Path) -> dict:
        raw = manifest_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise ValueError(f"plugin manifest is empty: {manifest_path}")
        return json.loads(raw)

    def _load_module(self, plugin_name: str, file_path: Path):
        spec = importlib.util.spec_from_file_location(f"plugin_{plugin_name}", file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"unable to load plugin module: {plugin_name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
