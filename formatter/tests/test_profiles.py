import pytest

from app.profiles import (
    DuplicateProfile,
    ProfileNotFound,
    ProfileStore,
    slugify,
)


def test_slugify():
    assert slugify("Clean Verbatim") == "clean-verbatim"
    assert slugify("  Legal  Style!! ") == "legal-style"


def test_seed_creates_two_profiles(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.seed_if_empty()
    ids = sorted(p["id"] for p in store.list())
    assert ids == ["clean-verbatim", "full-verbatim"]


def test_seed_is_noop_when_not_empty(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Mine", "instructions": "do the thing"})
    store.seed_if_empty()
    assert [p["name"] for p in store.list()] == ["Mine"]


def test_create_and_get_roundtrip(tmp_path):
    store = ProfileStore(str(tmp_path))
    created = store.create({"name": "Legal Style", "instructions": "Format legally."})
    assert created["id"] == "legal-style"
    fetched = store.get("legal-style")
    assert fetched["instructions"] == "Format legally."
    assert fetched["model"] is None


def test_create_requires_name_and_instructions(tmp_path):
    store = ProfileStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.create({"name": "", "instructions": "x"})
    with pytest.raises(ValueError):
        store.create({"name": "x", "instructions": "  "})


def test_create_duplicate_raises(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Dup", "instructions": "a"})
    with pytest.raises(DuplicateProfile):
        store.create({"name": "Dup", "instructions": "b"})


def test_update_changes_fields(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Edit Me", "instructions": "old"})
    updated = store.update("edit-me", {"instructions": "new", "temperature": 0.4})
    assert updated["instructions"] == "new"
    assert updated["temperature"] == 0.4
    assert store.get("edit-me")["instructions"] == "new"


def test_get_missing_raises(tmp_path):
    store = ProfileStore(str(tmp_path))
    with pytest.raises(ProfileNotFound):
        store.get("nope")


def test_delete_removes(tmp_path):
    store = ProfileStore(str(tmp_path))
    store.create({"name": "Bye", "instructions": "x"})
    store.delete("bye")
    with pytest.raises(ProfileNotFound):
        store.get("bye")
