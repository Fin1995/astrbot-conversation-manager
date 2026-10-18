"""Parsing and normalization of AstrBot conversation export files."""

from __future__ import annotations

import json
from pathlib import Path

from .i18n import tr


class ConversationImportError(ValueError):
    """Raised when an export file cannot be parsed safely."""


class ImportManager:
    """Parse AstrBot JSON/JSONL conversation exports."""

    @staticmethod
    def load_file(filepath: str | Path) -> list[dict]:
        """Load a JSON array, a single JSON object, or standard JSONL.

        AstrBot exports use ``cid`` in some versions and ``conversation_id``
        in others.  Both are normalized to ``conversation_id``.
        """

        path = Path(filepath).expanduser()
        try:
            raw = path.read_text(encoding="utf-8-sig").strip()
        except OSError as exc:
            raise ConversationImportError(f"无法读取文件: {exc}") from exc

        if not raw:
            return []

        conversations: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                conversations = []
                break
            if isinstance(obj, dict):
                conversations.append(obj)
            elif isinstance(obj, list):
                conversations.extend(obj)
            else:
                conversations = []
                break

        if not conversations:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConversationImportError(
                    "无法解析文件：既不是标准 JSONL，也不是 JSON 对象/数组。"
                ) from exc

            if isinstance(data, list):
                conversations = data
            elif isinstance(data, dict):
                conversations = [data]
            else:
                raise ConversationImportError("JSON 顶层必须是对象或数组。")

        normalized: list[dict] = []
        for index, conversation in enumerate(conversations, start=1):
            if not isinstance(conversation, dict):
                raise ConversationImportError(f"第 {index} 个对话不是 JSON 对象。")

            item = dict(conversation)
            if "cid" in item and "conversation_id" not in item:
                item["conversation_id"] = item.pop("cid")

            conversation_id = item.get("conversation_id")
            if not isinstance(conversation_id, str) or not conversation_id.strip():
                raise ConversationImportError(
                    f"第 {index} 个对话缺少 conversation_id/cid。"
                )

            content = item.get("content", [])
            if not isinstance(content, list):
                raise ConversationImportError(
                    f"第 {index} 个对话的 content 不是数组。"
                )

            item["conversation_id"] = conversation_id.strip()
            item["content"] = content
            normalized.append(item)

        return normalized

    @staticmethod
    def format_user_id(user_id: str) -> str:
        """Format an AstrBot user id for display."""

        parts = str(user_id).split(":")
        if len(parts) >= 3:
            message_type = {
                "FriendMessage": "私聊",
                "GroupMessage": "群聊",
            }.get(parts[1], parts[1])
            return f"{tr(message_type)}:{parts[2]}"
        return str(user_id)
