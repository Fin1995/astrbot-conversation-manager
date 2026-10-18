from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


SCHEMA = """
CREATE TABLE conversations (
    inner_conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    platform_id TEXT,
    user_id TEXT,
    content TEXT,
    title TEXT,
    persona_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    token_usage INTEGER
);
CREATE TABLE provider_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,
    provider_id TEXT,
    provider_model TEXT
);
"""


def _create_database(path: Path, include_schema: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        if include_schema:
            connection.executescript(SCHEMA)
            content = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "hello"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hi"}],
                },
            ]
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, platform_id, user_id, content, title,
                     persona_id, created_at, updated_at, token_usage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "conv-1",
                    "webchat",
                    "webchat:demo:1",
                    json.dumps(content, ensure_ascii=False),
                    "Demo conversation",
                    "default",
                    "2026-01-01 10:00:00.000000",
                    "2026-01-01 10:05:00.000000",
                    len(json.dumps(content, ensure_ascii=False)) // 2,
                ),
            )
            connection.execute(
                "INSERT INTO provider_stats (conversation_id, provider_id) VALUES (?, ?)",
                ("conv-1", "demo-provider"),
            )
        else:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
        connection.commit()
    finally:
        connection.close()
    return path


@pytest.fixture
def make_db(tmp_path):
    def factory(name: str = "data_v4.db", include_schema: bool = True) -> Path:
        return _create_database(tmp_path / name, include_schema=include_schema)

    return factory
