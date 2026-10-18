"""SQLite access for AstrBot conversation databases.

The tool edits the ``conversations`` table used by AstrBot v3/v4.  AstrBot
stores each conversation as one row whose ``content`` column is a JSON array
of messages.  The schema is validated before any write, and the first write
in a session creates a timestamped backup next to the database.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

REQUIRED_COLUMNS = frozenset(
    {
        "conversation_id",
        "user_id",
        "platform_id",
        "content",
        "title",
        "persona_id",
        "created_at",
        "updated_at",
        "token_usage",
    }
)


class InvalidDatabaseError(ValueError):
    """Raised when a file is not a usable AstrBot conversation database."""


class ConversationNotFoundError(ValueError):
    """Raised when a conversation id no longer exists."""


@dataclass(frozen=True)
class DatabaseInfo:
    path: Path
    columns: frozenset[str]
    size: int
    mtime: float
    legacy: bool


def validate_database(path: str | Path) -> DatabaseInfo:
    """Validate a SQLite file and return basic metadata.

    A valid database must contain the ``conversations`` table with every
    column used by this tool.  The check is read-only.
    """

    db_path = Path(path).expanduser().resolve()
    if not db_path.is_file():
        raise InvalidDatabaseError(f"数据库文件不存在: {db_path}")

    try:
        connection = sqlite3.connect(
            f"{db_path.as_uri()}?mode=ro",
            uri=True,
            timeout=5,
        )
        try:
            rows = connection.execute("PRAGMA table_info(conversations)").fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise InvalidDatabaseError(f"无法读取 SQLite 数据库: {exc}") from exc

    columns = frozenset(row[1] for row in rows)
    missing = REQUIRED_COLUMNS - columns
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise InvalidDatabaseError(
            "数据库中没有找到 AstrBot 的 conversations 表，"
            f"或缺少字段: {missing_text}"
        )

    stat = db_path.stat()
    return DatabaseInfo(
        path=db_path,
        columns=columns,
        size=stat.st_size,
        mtime=stat.st_mtime,
        legacy=db_path.name.lower().startswith("data_v3"),
    )


def timestamp_to_db(value) -> str:
    """Convert a timestamp or datetime string to AstrBot's text format."""

    if value is None:
        return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S.%f")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=CST).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )
        except (OSError, ValueError):
            pass
    return str(value)


def estimate_token_usage(messages: list) -> int:
    """Return the same rough estimate used by the original tool.

    AstrBot stores token usage for statistics.  There is no tokenizer in the
    dependency-free tool, so this value is an estimate and is recalculated
    whenever content is edited.
    """

    content_json = json.dumps(messages, ensure_ascii=False)
    return max(0, len(content_json) // 2)


class ConversationDB:
    """Small, dependency-free wrapper around an AstrBot SQLite database."""

    def __init__(self, db_path: str | Path, backup_dir: str | Path | None = None):
        self.info = validate_database(db_path)
        self.db_path = str(self.info.path)
        self.backup_dir = (
            Path(backup_dir).expanduser().resolve()
            if backup_dir is not None
            else self.info.path.parent / "conversation-manager-backups"
        )
        self._backup_path: Path | None = None
        self._backup_done = False

    # ------------------------------------------------------------------
    # Connection / backup helpers
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _now(self) -> str:
        return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S.%f")

    def ensure_backup(self) -> Path:
        """Create one consistent backup before the first write in a session."""

        if self._backup_done and self._backup_path is not None:
            return self._backup_path

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = self.info.path.suffix or ".db"
        backup_path = self.backup_dir / f"{self.info.path.stem}-{stamp}{suffix}"

        source = self._connect()
        destination = sqlite3.connect(str(backup_path))
        try:
            with destination:
                source.backup(destination)
        finally:
            destination.close()
            source.close()

        self._backup_path = backup_path
        self._backup_done = True
        return backup_path

    @property
    def backup_path(self) -> Path | None:
        return self._backup_path

    # ------------------------------------------------------------------
    # Content helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_content(raw) -> list:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []

    def _load_messages(self, connection: sqlite3.Connection, conversation_id: str) -> list:
        row = connection.execute(
            """
            SELECT content FROM conversations
            WHERE conversation_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")
        return self._parse_content(row[0])

    def _write_messages(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        messages: list,
    ) -> None:
        content_json = json.dumps(messages, ensure_ascii=False)
        cursor = connection.execute(
            """
            UPDATE conversations
            SET content = ?, token_usage = ?, updated_at = ?
            WHERE conversation_id = ?
            """,
            (
                content_json,
                estimate_token_usage(messages),
                self._now(),
                conversation_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ConversationNotFoundError(f"对话不存在: {conversation_id}")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def list_conversations(self, search: str = "") -> list[dict]:
        """List conversation summaries, optionally filtered by a search term."""

        connection = self._connect()
        try:
            if search:
                rows = connection.execute(
                    """
                    SELECT conversation_id, user_id, platform_id, title, persona_id,
                           created_at, updated_at, content, token_usage
                    FROM conversations
                    WHERE user_id LIKE ? OR title LIKE ? OR conversation_id LIKE ?
                    ORDER BY updated_at DESC
                    """,
                    (f"%{search}%", f"%{search}%", f"%{search}%"),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT conversation_id, user_id, platform_id, title, persona_id,
                           created_at, updated_at, content, token_usage
                    FROM conversations
                    ORDER BY updated_at DESC
                    """
                ).fetchall()

            result = []
            for row in rows:
                item = dict(row)
                messages = self._parse_content(item["content"])
                item["message_count"] = len(messages)
                item["_messages"] = messages
                result.append(item)
            return result
        finally:
            connection.close()

    def get_conversation(self, conversation_id: str) -> dict | None:
        """Return one conversation, including its parsed messages."""

        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT conversation_id, user_id, platform_id, title, persona_id,
                       created_at, updated_at, content, token_usage
                FROM conversations
                WHERE conversation_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None

            item = dict(row)
            messages = self._parse_content(item["content"])
            item["_messages"] = messages
            item["message_count"] = len(messages)
            return item
        finally:
            connection.close()

    def conversation_exists(self, conversation_id: str) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM conversations WHERE conversation_id = ? LIMIT 1",
                (conversation_id,),
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def insert_conversation(self, conv: dict) -> None:
        """Insert a new conversation row."""

        conversation_id = str(conv.get("conversation_id") or "").strip()
        user_id = str(conv.get("user_id") or "").strip()
        if not conversation_id:
            raise ValueError("conversation_id 不能为空")
        if not user_id:
            raise ValueError("user_id 不能为空")

        messages = conv.get("content", [])
        if not isinstance(messages, list):
            raise ValueError("content 必须是消息数组")

        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO conversations
                       (conversation_id, user_id, platform_id, content, title,
                        persona_id, created_at, updated_at, token_usage)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        user_id,
                        conv.get("platform_id") or "default",
                        json.dumps(messages, ensure_ascii=False),
                        conv.get("title"),
                        conv.get("persona_id"),
                        timestamp_to_db(conv.get("created_at")),
                        timestamp_to_db(conv.get("updated_at")),
                        estimate_token_usage(messages),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"无法插入对话: {exc}") from exc
        finally:
            connection.close()

    def update_content(self, conversation_id: str, messages: list) -> None:
        if not isinstance(messages, list):
            raise ValueError("messages 必须是数组")

        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                self._write_messages(connection, conversation_id, messages)
        finally:
            connection.close()

    def append_messages(self, conversation_id: str, new_messages: list) -> None:
        if not isinstance(new_messages, list):
            raise ValueError("new_messages 必须是数组")

        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                messages = self._load_messages(connection, conversation_id)
                messages.extend(new_messages)
                self._write_messages(connection, conversation_id, messages)
        finally:
            connection.close()

    def delete_conversation(self, conversation_id: str) -> None:
        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                )
                if cursor.rowcount == 0:
                    raise ConversationNotFoundError(f"对话不存在: {conversation_id}")
        finally:
            connection.close()

    def delete_message_at(self, conversation_id: str, index: int) -> None:
        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                messages = self._load_messages(connection, conversation_id)
                if not 0 <= index < len(messages):
                    raise IndexError(f"消息索引超出范围: {index}")
                messages.pop(index)
                self._write_messages(connection, conversation_id, messages)
        finally:
            connection.close()

    def update_message_at(
        self,
        conversation_id: str,
        index: int,
        new_message: dict,
    ) -> None:
        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                messages = self._load_messages(connection, conversation_id)
                if not 0 <= index < len(messages):
                    raise IndexError(f"消息索引超出范围: {index}")
                messages[index] = new_message
                self._write_messages(connection, conversation_id, messages)
        finally:
            connection.close()

    def insert_message_at(
        self,
        conversation_id: str,
        index: int,
        new_message: dict,
    ) -> None:
        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                messages = self._load_messages(connection, conversation_id)
                index = max(0, min(index, len(messages)))
                messages.insert(index, new_message)
                self._write_messages(connection, conversation_id, messages)
        finally:
            connection.close()

    def merge_conversation(
        self,
        conversation_id: str,
        new_messages: list,
        dedup: bool = True,
    ) -> int:
        """Merge messages into an existing conversation and return the added count."""

        if not isinstance(new_messages, list):
            raise ValueError("new_messages 必须是数组")

        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                existing = self._load_messages(connection, conversation_id)

                if dedup:
                    seen = {
                        json.dumps(message, ensure_ascii=False, sort_keys=True)
                        for message in existing
                    }
                    added = 0
                    for message in new_messages:
                        fingerprint = json.dumps(
                            message, ensure_ascii=False, sort_keys=True
                        )
                        if fingerprint in seen:
                            continue
                        existing.append(message)
                        seen.add(fingerprint)
                        added += 1
                else:
                    existing.extend(new_messages)
                    added = len(new_messages)

                self._write_messages(connection, conversation_id, existing)
                return added
        finally:
            connection.close()

    def update_conversation_id(self, old_id: str, new_id: str) -> None:
        """Rename a conversation id.

        AstrBot's provider statistics also carry the conversation id, so the
        rename is propagated to that table when it exists.
        """

        old_id = str(old_id).strip()
        new_id = str(new_id).strip()
        if not new_id:
            raise ValueError("新对话 ID 不能为空")
        if old_id == new_id:
            return

        self.ensure_backup()
        connection = self._connect()
        try:
            with connection:
                exists = connection.execute(
                    "SELECT 1 FROM conversations WHERE conversation_id = ? LIMIT 1",
                    (new_id,),
                ).fetchone()
                if exists is not None:
                    raise ValueError(f"目标 ID 已存在: {new_id}")

                cursor = connection.execute(
                    """
                    UPDATE conversations
                    SET conversation_id = ?, updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (new_id, self._now(), old_id),
                )
                if cursor.rowcount == 0:
                    raise ConversationNotFoundError(f"原对话不存在: {old_id}")

                table = connection.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type = 'table' AND name = 'provider_stats'
                    """
                ).fetchone()
                if table is not None:
                    columns = {
                        row[1]
                        for row in connection.execute(
                            "PRAGMA table_info(provider_stats)"
                        ).fetchall()
                    }
                    if "conversation_id" in columns:
                        connection.execute(
                            """
                            UPDATE provider_stats
                            SET conversation_id = ?
                            WHERE conversation_id = ?
                            """,
                            (new_id, old_id),
                        )
        finally:
            connection.close()
