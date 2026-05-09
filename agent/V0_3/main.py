from __future__ import annotations

import sys
from pathlib import Path

from core.plugin_manager import PluginManager
from core.registry import Registry
from core.runtime import Runtime


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    plugin_dir = base_dir / "plugins"
    config_path = base_dir / "configs" / "default.yaml"

    task = " ".join(sys.argv[1:]).strip()
    if not task:
        task = input("请输入任务目标：").strip()
    if not task:
        print("未提供任务目标，程序结束。")
        return

    registry = Registry()
    plugin_manager = PluginManager(registry)
    plugin_manager.load_all(plugin_dir)

    runtime = Runtime(registry=registry, base_dir=base_dir)
    result = runtime.run(task=task, config_path=config_path)
    print(result)


if __name__ == "__main__":
    main()
