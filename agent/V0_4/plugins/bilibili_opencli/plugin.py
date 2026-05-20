from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from core.interfaces import Agent, AgentRequest, AgentResult, Message, Tool, ToolFactory

URL_PATTERN = re.compile(r"https?://(?:www\.)?(?:b23\.tv|(?:www\.)?bilibili\.com/\S+)", re.IGNORECASE)


class BilibiliWorkerAgent(Agent):
    def __init__(
        self,
        context,
        task_id: str,
        cache_dir: str,
        opencli_command: str,
        timeout_seconds: int,
        default_limit: int,
        model: str | None = None,
    ) -> None:
        self.context = context
        self.task_id = task_id
        self.cache_dir = Path(cache_dir)
        self.opencli_command = opencli_command
        self.timeout_seconds = timeout_seconds
        self.default_limit = default_limit
        self.model = model

    def run(self, request: AgentRequest) -> AgentResult:
        analysis = self._analyze_task(request.task)
        command = self._build_opencli_command(analysis)
        result = self._run_command(command)
        self._ensure_command_succeeded(result)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = self.cache_dir / "stdout.json"
        stdout_path.write_text(result.stdout, encoding="utf-8")

        items = self._parse_items(result.stdout, analysis)
        return AgentResult(
            output=self._render_output(items, analysis),
            done=True,
            meta={
                "role": "BilibiliWorkerAgent",
                "child_agent": "BilibiliWorkerAgent",
                "task_id": self.task_id,
                "analysis": analysis,
                "command": command,
                "items": items,
                "stdout_cache": str(stdout_path),
            },
        )

    def _analyze_task(self, task: str) -> dict[str, Any]:
        provider = self.context.provider
        if provider is not None:
            analysis = self._analyze_with_model(task)
            if analysis:
                return analysis
        return self._analyze_with_rules(task)

    def _analyze_with_model(self, task: str) -> dict[str, Any]:
        response = self.context.provider.chat(
            [
                Message(
                    role="system",
                    content=(
                        "你是一个 Bilibili 子 agent。"
                        "请根据用户输入分析应该执行哪个 opencli bilibili 命令。"
                        "action 只允许是 video、hot、summary、search。"
                        "如果用户给了视频链接，通常用 video 或 summary。"
                        "如果用户在找热门、最新、推荐视频，通常用 hot。"
                        "如果用户要搜索某个主题、人物、关键词，使用 search。"
                        '只返回 JSON，例如 {"action":"hot","query":"","url":"","limit":10}。'
                    ),
                ),
                Message(role="user", content=task),
            ],
            model=self.model,
            temperature=0.0,
            max_tokens=200,
        )
        parsed = self._parse_json(response.content.strip())
        if not isinstance(parsed, dict):
            return {}

        action = str(parsed.get("action", "")).strip().lower()
        if action not in {"video", "hot", "summary", "search"}:
            return {}

        return {
            "action": action,
            "url": str(parsed.get("url", "")).strip(),
            "query": str(parsed.get("query", "")).strip(),
            "limit": self._normalize_limit(parsed.get("limit")),
        }

    def _analyze_with_rules(self, task: str) -> dict[str, Any]:
        match = URL_PATTERN.search(task)
        url = match.group(0).rstrip(").,;!】』\"'") if match else ""
        limit = self._extract_limit(task)
        if url:
            if any(keyword in task for keyword in ("总结", "概括", "摘要")):
                return {"action": "summary", "url": url, "query": "", "limit": limit}
            return {"action": "video", "url": url, "query": "", "limit": limit}

        if any(keyword in task for keyword in ("搜索", "查找", "找一下", "搜一下")):
            return {"action": "search", "url": "", "query": self._extract_query(task), "limit": limit}

        return {"action": "hot", "url": "", "query": "", "limit": limit}

    def _extract_query(self, task: str) -> str:
        cleaned = task
        for keyword in ("在b站搜索", "在B站搜索", "搜索b站", "搜索B站", "搜索", "查找", "找一下", "搜一下", "b站", "B站"):
            cleaned = cleaned.replace(keyword, " ")
        return " ".join(cleaned.split()).strip()

    def _extract_limit(self, task: str) -> int:
        match = re.search(r"(\d+)\s*(条|个|项)", task)
        if not match:
            return self.default_limit
        return self._normalize_limit(match.group(1))

    def _normalize_limit(self, value: Any) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return self.default_limit
        return max(1, min(number, 50))

    def _build_opencli_command(self, analysis: dict[str, Any]) -> list[str]:
        action = analysis["action"]
        if action == "video":
            return [self.opencli_command, "bilibili", "video", analysis["url"], "-f", "json"]
        if action == "summary":
            return [self.opencli_command, "bilibili", "summary", analysis["url"], "-f", "json"]
        if action == "search":
            query = analysis.get("query", "").strip() or "视频"
            return [
                self.opencli_command,
                "bilibili",
                "search",
                query,
                "--limit",
                str(analysis["limit"]),
                "-f",
                "json",
            ]
        return [
            self.opencli_command,
            "bilibili",
            "hot",
            "--limit",
            str(analysis["limit"]),
            "-f",
            "json",
        ]

    def _run_command(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["cmd", "/c", *command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
            check=False,
        )

    def _ensure_command_succeeded(self, result: subprocess.CompletedProcess[str]) -> None:
        if result.returncode == 0:
            return
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(f"opencli 调用失败: {detail}")

    def _parse_items(self, stdout: str, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._parse_json(stdout)
        if payload is None:
            return [{"title": stdout.strip(), "url": analysis.get("url", "")}]

        items = self._coerce_items(payload)
        normalized: list[dict[str, Any]] = []
        for item in items:
            title = self._pick_value(item, "title", "name")
            url = self._pick_value(item, "url", "link", "share_url")
            bvid = self._pick_value(item, "bvid", "bv_id")
            normalized.append(
                {
                    "title": title or "",
                    "url": url or analysis.get("url", ""),
                    "bvid": bvid or "",
                    "raw": item,
                }
            )
        if normalized:
            return normalized
        if isinstance(payload, dict):
            return [
                {
                    "title": self._pick_value(payload, "title", "name") or analysis.get("url", "") or analysis.get("query", ""),
                    "url": self._pick_value(payload, "url", "link", "share_url") or analysis.get("url", ""),
                    "bvid": self._pick_value(payload, "bvid", "bv_id") or "",
                    "raw": payload,
                }
            ]
        return [{"title": stdout.strip(), "url": analysis.get("url", "")}]

    def _parse_json(self, text: str) -> Any:
        text = text.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
        return None

    def _coerce_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "list", "results", "videos"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    nested = self._coerce_items(value)
                    if nested:
                        return nested
        return []

    def _pick_value(self, data: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _render_output(self, items: list[dict[str, Any]], analysis: dict[str, Any]) -> str:
        action = analysis["action"]
        if not items:
            return f"B站任务已执行，但没有拿到可记录结果。action={action}"
        if action in {"hot", "search"}:
            titles = "；".join(item["title"] for item in items[:3] if item.get("title"))
            return f"已记录 {len(items)} 条 B站{action}结果。前几条：{titles}"
        return f"已记录视频标题: {items[0].get('title') or analysis.get('url') or analysis.get('query', '')}"


class BilibiliCommandTool(Tool):
    def __init__(
        self,
        context,
        record_path: str = "./data/results/bilibili_titles.jsonl",
        opencli_command: str = "opencli",
        timeout_seconds: int = 30,
        default_limit: int = 20,
        model: str | None = None,
    ) -> None:
        self.context = context
        self.record_path = Path(record_path)
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_path.touch(exist_ok=True)
        self.opencli_command = opencli_command
        self.timeout_seconds = timeout_seconds
        self.default_limit = default_limit
        self.model = model

    def run(self, request: AgentRequest) -> AgentResult:
        job_registry = self.context.job_registry or self.context.task_registry
        job_record = job_registry.open_job(
            parent_session_id=request.session_id,
            worker_name="BilibiliWorkerAgent",
            task=request.task,
            meta={"tool_name": "bilibili_command_tool"},
        )
        sub_agent: BilibiliWorkerAgent | None = None
        try:
            sub_agent = BilibiliWorkerAgent(
                context=self.context,
                task_id=job_record.job_id,
                cache_dir=job_record.cache_dir,
                opencli_command=self.opencli_command,
                timeout_seconds=self.timeout_seconds,
                default_limit=self.default_limit,
                model=self.model,
            )
            result = sub_agent.run(request)
            items = result.meta.get("items", [])
            self._append_records(job_record.job_id, request.session_id, items, result.meta.get("analysis", {}))
            job_registry.finish_job(
                job_record.job_id,
                meta={
                    "record_path": str(self.record_path),
                    "item_count": len(items),
                    "analysis": result.meta.get("analysis", {}),
                    "command": result.meta.get("command", []),
                },
            )
            return AgentResult(
                output=result.output,
                done=True,
                meta={
                    "role": "BilibiliCommandTool",
                    "tool_name": "bilibili_command_tool",
                    "job_id": job_record.job_id,
                    "child_agent": "BilibiliWorkerAgent",
                    "record_path": str(self.record_path),
                    "analysis": result.meta.get("analysis", {}),
                    "command": result.meta.get("command", []),
                    "item_count": len(items),
                },
            )
        except Exception as exc:
            job_registry.fail_job(job_record.job_id, str(exc))
            raise
        finally:
            sub_agent = None

    def _append_records(self, job_id: str, session_id: str, items: list[dict[str, Any]], analysis: dict[str, Any]) -> None:
        rows = items or [{"title": "", "url": analysis.get("url", ""), "bvid": "", "raw": {}}]
        with self.record_path.open("a", encoding="utf-8") as file:
            for item in rows:
                payload = {
                    "job_id": job_id,
                    "session_id": session_id,
                    "action": analysis.get("action", ""),
                    "query": analysis.get("query", ""),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "bvid": item.get("bvid", ""),
                    "raw": item.get("raw", {}),
                }
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")


class BilibiliCommandToolFactory(ToolFactory):
    def create(self, context, **kwargs) -> Tool:
        return BilibiliCommandTool(context=context, **kwargs)


def register(registry) -> None:
    factory = BilibiliCommandToolFactory()
    registry.register_tool("bilibili_command_tool", factory)
    registry.register_tool("bilibili_opencli", factory)
