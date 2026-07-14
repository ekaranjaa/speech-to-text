from __future__ import annotations

from typing import Optional

import httpx


class DiarizerError(Exception):
    pass


class DiarizerUnreachable(DiarizerError):
    pass


class DiarizerClient:
    def __init__(self, host: str, timeout: float = 600.0, client: Optional[httpx.Client] = None):
        self._host = host.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def health(self) -> dict:
        try:
            resp = self._client.get(f"{self._host}/health")
            resp.raise_for_status()
            return {"reachable": True, **resp.json()}
        except (httpx.ConnectError, httpx.HTTPError):
            return {"reachable": False, "ready": False}

    def diarize(self, audio: bytes, filename: str, num_speakers: Optional[int] = None) -> dict:
        files = {"audio": (filename, audio, "application/octet-stream")}
        data = {"num_speakers": str(num_speakers)} if num_speakers else {}
        try:
            resp = self._client.post(f"{self._host}/diarize", files=files, data=data)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise DiarizerUnreachable(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise DiarizerError(str(exc)) from exc
