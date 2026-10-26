from __future__ import annotations

import json
from typing import Iterator, Optional

import httpx


class OllamaError(Exception):
    pass


class OllamaUnreachable(OllamaError):
    pass


class ModelNotFound(OllamaError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str,
        timeout: float = 120.0,
        client: Optional[httpx.Client] = None,
    ):
        self._host = host.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def health(self) -> dict:
        try:
            resp = self._client.get(f"{self._host}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"reachable": True, "models": models}
        except (httpx.ConnectError, httpx.HTTPError):
            return {"reachable": False, "models": []}

    def chat(
        self, model: str, system: str, user: str, temperature: float
    ) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            "options": {"temperature": temperature},
        }
        try:
            with self._client.stream(
                "POST", f"{self._host}/api/chat", json=payload
            ) as resp:
                if resp.status_code == 404:
                    resp.read()
                    raise ModelNotFound(model)
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    error = data.get("error")
                    if error:
                        if "not found" in error.lower():
                            raise ModelNotFound(model)
                        raise OllamaError(error)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise OllamaUnreachable(str(exc)) from exc
