from __future__ import annotations

import sqlite3

import pytest

from astrbot_conversation_manager.db import (
    ConversationDB,
    ConversationNotFoundError,
    InvalidDatabaseError,
    validate_database,
)


def _messages():
    return [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]


def test_validate_database(tmp_path, make_db):
    db_path = make_db("data_v4.db")
    info = validate_database(db_path)
    assert info.path == db_path.resolve()
    assert "conversation_id" in info.columns
    assert not info.legacy


def test_invalid_schema_is_rejected(tmp_path, make_db):
    db_path = make_db("data_v4.db", include_schema=False)
    with pytest.raises(InvalidDatabaseError):
        ConversationDB(db_path, backup_dir=tmp_path / "backups")


def test_list_and_get(tmp_path, make_db):
    db = ConversationDB(make_db("data_v4.db"), backup_dir=tmp_path / "backups")
    conversations = db.list_conversations()
    assert len(conversations) == 1
    assert conversations[0]["conversation_id"] == "conv-1"
    assert conversations[0]["message_count"] == 2

    detail = db.get_conversation("conv-1")
    assert detail is not None
    assert detail["_messages"] == _messages()


def test_update_creates_backup(tmp_path, make_db):
    db = ConversationDB(make_db("data_v4.db"), backup_dir=tmp_path / "backups")
    db.update_content("conv-1", _messages()[:1])

    assert db.backup_path is not None
    assert db.backup_path.is_file()

    connection = sqlite3.connect(db.backup_path)
    try:
        raw = connection.execute(
            "SELECT content FROM conversations WHERE conversation_id = 'conv-1'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert "hi" in raw
    assert db.get_conversation("conv-1")["message_count"] == 1


def test_insert_and_exists(tmp_path, make_db):
    db = ConversationDB(make_db("data_v4.db"), backup_dir=tmp_path / "backups")
    db.insert_conversation(
        {
            "conversation_id": "conv-2",
            "user_id": "webchat:demo:2",
            "platform_id": "webchat",
            "title": "Second",
            "content": _messages(),
            "created_at": "2026-01-02 10:00:00.000000",
            "updated_at": "2026-01-02 10:00:00.000000",
        }
    )
    assert db.conversation_exists("conv-2")
    assert len(db.list_conversations()) == 2


def test_merge_deduplicates(tmp_path, make_db):
    db = ConversationDB(make_db("data_v4.db"), backup_dir=tmp_path / "backups")
    added = db.merge_conversation(
        "conv-1",
        [
            _messages()[0],
            {"role": "user", "content": [{"type": "text", "text": "new"}]},
        ],
        dedup=True,
    )
    assert added == 1
    assert db.get_conversation("conv-1")["message_count"] == 3


def test_rename_updates_provider_stats(tmp_path, make_db):
    db = ConversationDB(make_db("data_v4.db"), backup_dir=tmp_path / "backups")
    db.update_conversation_id("conv-1", "conv-renamed")

    assert db.get_conversation("conv-renamed") is not None
    connection = sqlite3.connect(db.db_path)
    try:
        provider = connection.execute(
            "SELECT conversation_id FROM provider_stats"
        ).fetchone()[0]
    finally:
        connection.close()
    assert provider == "conv-renamed"


def test_delete_message_and_bounds(tmp_path, make_db):
    db = ConversationDB(make_db("data_v4.db"), backup_dir=tmp_path / "backups")
    db.delete_message_at("conv-1", 0)
    assert db.get_conversation("conv-1")["message_count"] == 1

    with pytest.raises(IndexError):
        db.delete_message_at("conv-1", 99)

    with pytest.raises(ConversationNotFoundError):
        db.update_content("missing", _messages())
