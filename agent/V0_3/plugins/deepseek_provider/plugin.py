from __future__ import annotations

import json
import os
from urllib import error, request
from dotenv import load_dotenv
from core.interfaces import Message, ModelProvider, ModelResponse
load_dotenv(verbose=True)


class DeepSeekProvider(ModelProvider):
    def __init__(
        self,
        api_key_env: str = "DEEPSEEK_API_KEY",
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"DeepSeek provider 需要环境变量 {self.api_key_env}，但当前没有找到"
            )

        payload: dict[str, object] = {
            "model": model or self.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"DeepSeek API 连接失败: {exc.reason}") from exc

        data = json.loads(raw)
        choice = data["choices"][0]["message"]
        content = choice.get("content", "") or ""
        usage = data.get("usage", {})
        return ModelResponse(
            content=content,
            meta={
                "provider": "deepseek",
                "model": payload["model"],
                "usage": usage,
            },
        )


def register(registry) -> None:
    registry.register_provider("deepseek_provider", DeepSeekProvider)
