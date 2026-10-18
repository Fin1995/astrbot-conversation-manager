"""Create synthetic demo data for screenshots and manual testing.

The generated files contain no real conversations and are ignored by git.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo"
DB_PATH = DEMO_DIR / "data_v4.db"
EXPORT_PATH = DEMO_DIR / "conversations_export_demo.jsonl"


def message(role: str, text: str) -> dict:
    return {"role": role, "content": [{"type": "text", "text": text}]}


CONVERSATIONS = [
    {
        "conversation_id": "demo-travel-plan",
        "user_id": "webchat:demo:10001",
        "platform_id": "webchat",
        "title": "示例：周末旅行计划",
        "persona_id": "default",
        "created_at": "2026-01-02 09:10:00.000000",
        "updated_at": "2026-01-02 09:18:00.000000",
        "content": [
            message("user", "帮我规划一个周末去杭州的行程。"),
            message(
                "assistant",
                "可以。第一天上午到西湖边散步，下午去中国茶叶博物馆；"
                "第二天安排西溪湿地，傍晚返程。",
            ),
            message("user", "把第二天的行程安排得轻松一点。"),
            message(
                "assistant",
                "那就把西溪湿地放在上午，下午留出休息和返程时间。",
            ),
        ],
    },
    {
        "conversation_id": "demo-code-review",
        "user_id": "webchat:demo:10002",
        "platform_id": "webchat",
        "title": "示例：代码审查",
        "persona_id": "default",
        "created_at": "2026-01-03 14:20:00.000000",
        "updated_at": "2026-01-03 14:26:00.000000",
        "content": [
            message("user", "帮我检查这段 Python 代码的异常处理。"),
            message(
                "assistant",
                "建议先缩小 try 的范围，并在捕获异常时保留原始错误信息。",
            ),
            message("user", "如果我想记录日志呢？"),
            message(
                "assistant",
                "可以使用 logging.exception，它会把堆栈信息一起写入日志。",
            ),
        ],
    },
    {
        "conversation_id": "demo-reading-notes",
        "user_id": "webchat:demo:10003",
        "platform_id": "webchat",
        "title": "示例：读书笔记",
        "persona_id": "default",
        "created_at": "2026-01-04 20:05:00.000000",
        "updated_at": "2026-01-04 20:12:00.000000",
        "content": [
            message("user", "帮我整理一份《小王子》的主题笔记。"),
            message(
                "assistant",
                "可以围绕“看见本质”“建立关系”和“责任”三个主题整理。",
            ),
        ],
    },
]


def estimate_tokens(messages: list) -> int:
    return max(0, len(json.dumps(messages, ensure_ascii=False)) // 2)


def create_database() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute(
            """
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
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE provider_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                provider_id TEXT,
                provider_model TEXT
            )
            """
        )
        for conversation in CONVERSATIONS:
            connection.execute(
                """
                INSERT INTO conversations
                    (conversation_id, platform_id, user_id, content, title,
                     persona_id, created_at, updated_at, token_usage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation["conversation_id"],
                    conversation["platform_id"],
                    conversation["user_id"],
                    json.dumps(conversation["content"], ensure_ascii=False),
                    conversation["title"],
                    conversation["persona_id"],
                    conversation["created_at"],
                    conversation["updated_at"],
                    estimate_tokens(conversation["content"]),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def create_export() -> None:
    exported = []
    for conversation in CONVERSATIONS[:2]:
        item = {
            "cid": conversation["conversation_id"],
            "user_id": conversation["user_id"],
            "platform_id": conversation["platform_id"],
            "title": conversation["title"],
            "persona_id": conversation["persona_id"],
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
            "content": conversation["content"],
        }
        exported.append(item)

    with EXPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        for item in exported:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    create_database()
    create_export()
    print(f"database: {DB_PATH}")
    print(f"export:   {EXPORT_PATH}")
    print(f"created:  {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
