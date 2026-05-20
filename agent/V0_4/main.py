from __future__ import annotations

import argparse
from pathlib import Path

from core.plugin_manager import PluginManager
from core.registry import Registry
from core.runtime import KernelRuntime


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    plugin_dir = base_dir / "plugins"

    parser = argparse.ArgumentParser(prog="violet-kernel")
    parser.add_argument("task", nargs="*", help="task text or bilibili intent")
    parser.add_argument("--config", default=str(base_dir / "configs" / "default.yaml"))
    args = parser.parse_args()

    config_path = Path(args.config)
    task = " ".join(args.task).strip()
    if not task:
        task = input("请输入任务目标：").strip()
    if not task:
        print("未提供任务目标，程序结束。")
        return

    registry = Registry()
    plugin_manager = PluginManager(registry)
    plugin_manager.load_all(plugin_dir)

    runtime = KernelRuntime(registry=registry, base_dir=base_dir)
    result = runtime.run(task=task, config_path=config_path)
    print(result)


if __name__ == "__main__":
    main()
