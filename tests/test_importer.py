from __future__ import annotations

import json

import pytest

from astrbot_conversation_manager.importer import (
    ConversationImportError,
    ImportManager,
)


def _conversation(cid: str = "demo-1") -> dict:
    return {
        "cid": cid,
        "user_id": "webchat:demo:1",
        "platform_id": "webchat",
        "title": "Demo",
        "persona_id": "default",
        "created_at": "2026-01-01 10:00:00.000000",
        "updated_at": "2026-01-01 10:05:00.000000",
        "content": [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}
        ],
    }


def test_jsonl_and_cid_normalization(tmp_path):
    path = tmp_path / "export.jsonl"
    path.write_text(
        json.dumps(_conversation("one"), ensure_ascii=False)
        + "\n"
        + json.dumps(_conversation("two"), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    conversations = ImportManager.load_file(path)

    assert [item["conversation_id"] for item in conversations] == ["one", "two"]
    assert "cid" not in conversations[0]


def test_json_array_and_object(tmp_path):
    array_path = tmp_path / "array.json"
    array_path.write_text(
        json.dumps([_conversation("array")], ensure_ascii=False),
        encoding="utf-8",
    )
    assert ImportManager.load_file(array_path)[0]["conversation_id"] == "array"

    object_path = tmp_path / "object.json"
    object_path.write_text(
        json.dumps(_conversation("object"), ensure_ascii=False),
        encoding="utf-8",
    )
    assert ImportManager.load_file(object_path)[0]["conversation_id"] == "object"


def test_invalid_content_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    payload = _conversation("bad")
    payload["content"] = "not-a-list"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ConversationImportError):
        ImportManager.load_file(path)


def test_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert ImportManager.load_file(path) == []


def test_format_user_id():
    assert ImportManager.format_user_id("default:FriendMessage:123") == "私聊:123"
    assert ImportManager.format_user_id("default:GroupMessage:456") == "群聊:456"
    assert ImportManager.format_user_id("plain-id") == "plain-id"
