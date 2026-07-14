from __future__ import annotations

import json
import re
from pathlib import Path

from app.seed_profiles import SEED_PROFILES

_ALLOWED_FIELDS = ("id", "name", "description", "instructions", "model", "temperature")


class ProfileError(Exception):
    pass


class ProfileNotFound(ProfileError):
    pass


class DuplicateProfile(ProfileError):
    pass


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug


class ProfileStore:
    def __init__(self, profiles_dir: str):
        self._dir = Path(profiles_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, profile_id: str) -> Path:
        return self._dir / f"{profile_id}.json"

    def _normalize(self, data: dict, profile_id: str) -> dict:
        return {
            "id": profile_id,
            "name": data["name"].strip(),
            "description": (data.get("description") or "").strip(),
            "instructions": data["instructions"].strip(),
            "model": data.get("model") or None,
            "temperature": data.get("temperature", None),
        }

    def _validate(self, data: dict) -> None:
        if not (data.get("name") or "").strip():
            raise ValueError("Profile name is required.")
        if not (data.get("instructions") or "").strip():
            raise ValueError("Profile instructions are required.")

    def seed_if_empty(self) -> None:
        if any(self._dir.glob("*.json")):
            return
        for profile in SEED_PROFILES:
            self._path(profile["id"]).write_text(
                json.dumps(profile, indent=2), encoding="utf-8"
            )

    def list(self) -> list[dict]:
        profiles = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in self._dir.glob("*.json")
        ]
        return sorted(profiles, key=lambda p: p["name"].lower())

    def get(self, profile_id: str) -> dict:
        path = self._path(profile_id)
        if not path.exists():
            raise ProfileNotFound(profile_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def create(self, data: dict) -> dict:
        self._validate(data)
        profile_id = (data.get("id") or slugify(data["name"])) or "profile"
        if self._path(profile_id).exists():
            raise DuplicateProfile(profile_id)
        profile = self._normalize(data, profile_id)
        self._path(profile_id).write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        return profile

    def update(self, profile_id: str, data: dict) -> dict:
        existing = self.get(profile_id)
        merged = {**existing, **{k: v for k, v in data.items() if k in _ALLOWED_FIELDS}}
        self._validate(merged)
        profile = self._normalize(merged, profile_id)
        self._path(profile_id).write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        return profile

    def delete(self, profile_id: str) -> None:
        path = self._path(profile_id)
        if not path.exists():
            raise ProfileNotFound(profile_id)
        path.unlink()
